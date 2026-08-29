"""Peça 13 — orquestração do lote.

O orquestrador não sabe o que é Playwright. Ele conversa com `Extrator`, um
protocolo de quatro métodos. Isso é o que permite cobrir a máquina de estados
inteira (§6) com um extrator falso, incluindo os caminhos que seriam caros ou
impossíveis de provocar contra o sistema real: sessão caindo no meio, processo
ambíguo, ZIP incompleto, seleção não resolvida.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from .disco import MEDIA_OBSERVADA_BYTES, estimar, exigir_espaco, media_medida
from .estados import Estado
from .ledger import Ledger, reconciliar
from .manifest import (
    Manifest,
    limpar_tmp_orfas,
    manifest_valido,
    pasta_trabalho,
    promover,
    registrar_artefato,
)
from .planilha import LinhaProcesso
from .segredos import limpar
from .zip_seguro import conferir_contagem, validar_zip


class SelecaoIncompleta(RuntimeError):
    """G2 — o link `Selecionar todos os restantes?` continuava sendo oferecido."""


class NumeroDivergente(RuntimeError):
    """G4 — o número na tela não é o número da planilha."""


class ProcessoAmbiguo(RuntimeError):
    """Dois ou mais itens no grupo PASTAS casam com o número."""


class ProcessoNaoEncontrado(RuntimeError):
    """Nenhum item no grupo PASTAS casa com o número."""


@dataclass
class ResultadoExtracao:
    """O que o extrator devolve para um processo."""
    pasta_benner: str
    numero_na_tela: str
    docs_listados_popup: int
    documentos: list[dict] = field(default_factory=list)
    caminho_zip: Path | None = None
    caminho_pedidos: Path | None = None
    selecao: dict = field(default_factory=dict)


class Extrator(Protocol):
    """O contrato que a camada Playwright precisa cumprir."""

    def sessao_viva(self) -> bool: ...
    def reconectar(self) -> None: ...
    def extrair(self, processo: LinhaProcesso, destino: Path) -> ResultadoExtracao: ...
    def fechar(self) -> None: ...


@dataclass
class ResultadoProcesso:
    processo: LinhaProcesso
    status: Estado
    observacao: str = ""
    pasta_destino: str = ""
    tentativas: int = 0
    detalhe: dict = field(default_factory=dict)


@dataclass
class Orquestrador:
    extrator: Extrator
    raiz_saida: Path
    ledger: Ledger
    throttle_s: float = 3.0
    max_tentativas: int = 3
    limite_por_execucao: int | None = 25
    margem_disco: float = 1.5

    # Ignora estado terminal no ledger e reprocessa assim mesmo.
    #
    # Existe porque estado terminal só é seguro se a classificação for confiável. Um
    # defeito no robô que produza `NAO_ENCONTRADO` para um processo que existe fica
    # gravado, e como o estado é terminal o processo nunca mais é tentado — some do
    # lote em silêncio. Aconteceu de verdade em 28/08/2026: `fill()` não disparava a
    # busca ao vivo do Benner e 333 processos teriam sido classificados assim.
    #
    # A decisão de reprocessar é humana, nunca do robô: é ele que erra a classificação.
    forcar: bool = False

    dormir = staticmethod(time.sleep)      # injetável nos testes

    # ---------------------------------------------------------------- lote

    def executar(self, processos: list[LinhaProcesso]) -> list[ResultadoProcesso]:
        """Roda o lote inteiro, serial, um processo por vez."""
        raiz = Path(self.raiz_saida)
        work = raiz / "_work"

        # H20 — antes de qualquer coisa, alinhar ledger e disco.
        limpar_tmp_orfas(work)
        reconciliar(self.ledger, raiz)

        pendentes = [p for p in processos if self._precisa_processar(p)]

        # H18 — barra o lote ANTES de começar, com a média medida se já houver.
        if pendentes:
            media = media_medida(raiz) or MEDIA_OBSERVADA_BYTES
            exigir_espaco(estimar(raiz, len(pendentes), media_bytes=media,
                                  margem=self.margem_disco))

        if self.limite_por_execucao is not None:
            pendentes = pendentes[: self.limite_por_execucao]

        resultados: list[ResultadoProcesso] = []
        for i, processo in enumerate(pendentes):
            if i:
                self.dormir(self.throttle_s)     # H4
            resultados.append(self._processar_com_retentativa(processo))

        return resultados

    def _precisa_processar(self, processo: LinhaProcesso) -> bool:
        """CONCLUIDO só é pulado depois de a pasta provar que está íntegra."""
        # A marca humana na planilha vence tudo, inclusive `--forcar`. Quem baixou à
        # mão sabe de coisas que o robô não tem como derivar — o caso 98 ("só aparece
        # em PROCESSOS (PASTAS)") é exatamente disso.
        if processo.resolvido_manualmente:
            return False

        # Marca fora do domínio combinado não é ignorável NEM processável: seria
        # adivinhar a intenção de quem escreveu. Sai no relatório para decisão humana.
        if processo.marca_desconhecida:
            self.ledger.registrar({
                "processo": processo.numero,
                "processo_normalizado": processo.normalizado,
                "status": Estado.BLOQUEADO.value,
                "motivo": f"coluna de controle humano com valor fora do dominio: "
                          f"{processo.benner_ok!r} (esperado 1, 98 ou 99)",
                "origem": "planilha",
            })
            return False

        ev = self.ledger.estado_atual().get(processo.normalizado)
        if ev is None:
            return True

        if self.forcar:
            self.ledger.registrar({
                "processo": processo.numero,
                "processo_normalizado": processo.normalizado,
                "status": Estado.PENDENTE.value,
                "motivo": f"reprocessamento forcado por humano; estado anterior era "
                          f"{ev.get('status')}",
                "origem": "--forcar",
            })
            return True

        status = ev.get("status")
        if status in (Estado.NAO_ENCONTRADO.value, Estado.AMBIGUO.value,
                      Estado.BLOQUEADO.value):
            return False

        if status == Estado.CONCLUIDO.value:
            ok, _ = manifest_valido(Path(self.raiz_saida) / processo.nome_pasta)
            return not ok

        return True

    # ---------------------------------------------------------------- processo

    def _processar_com_retentativa(self, processo: LinhaProcesso) -> ResultadoProcesso:
        ultimo: ResultadoProcesso | None = None

        for tentativa in range(1, self.max_tentativas + 1):
            # Só PARCIAL preserva o trabalho anterior. ERRO limpa: ali não se sabe o
            # que ficou meio escrito no disco.
            preservar = ultimo is not None and ultimo.status is Estado.PARCIAL
            r = self._processar_uma_vez(processo, tentativa, preservar=preservar)
            ultimo = r

            # Terminais e sucesso não retentam.
            if r.status in (Estado.CONCLUIDO, Estado.NAO_ENCONTRADO,
                            Estado.AMBIGUO, Estado.BLOQUEADO):
                return r

            if tentativa < self.max_tentativas:
                self.dormir(self.throttle_s)

        return ultimo

    def _processar_uma_vez(self, processo: LinhaProcesso, tentativa: int,
                           *, preservar: bool = False) -> ResultadoProcesso:
        raiz = Path(self.raiz_saida)
        destino = raiz / processo.nome_pasta

        self._registrar(processo, Estado.EM_ANDAMENTO, tentativa=tentativa)

        # §7.4 — sonda barata: sessão expirada aparece como "elemento não encontrado",
        # indistinguível de mudança de layout se não for checada aqui.
        try:
            if not self.extrator.sessao_viva():
                self.extrator.reconectar()
        except Exception as erro:
            return self._falhar(processo, Estado.ERRO, f"reconexao falhou: {limpar(erro)}",
                                tentativa)

        tmp = pasta_trabalho(raiz / "_work", processo.nome_pasta, limpar=not preservar)

        try:
            r = self.extrator.extrair(processo, tmp)
        except ProcessoNaoEncontrado as erro:
            return self._falhar(processo, Estado.NAO_ENCONTRADO, limpar(erro), tentativa)
        except ProcessoAmbiguo as erro:
            return self._falhar(processo, Estado.AMBIGUO, limpar(erro), tentativa)
        except (NumeroDivergente, SelecaoIncompleta) as erro:
            # G4 e G2 — falha dura, jamais degradada para PARCIAL.
            return self._falhar(processo, Estado.ERRO, limpar(erro), tentativa)
        except Exception as erro:
            # Qualquer outra coisa é falha TÉCNICA e retenta. Nunca vira terminal:
            # `NAO_ENCONTRADO` e `AMBIGUO` só saem das exceções que os nomeiam, porque
            # são veredictos sobre o DADO, não sobre a execução.
            return self._falhar(processo, Estado.ERRO, limpar(erro), tentativa)

        return self._concluir(processo, r, tmp, destino, tentativa)

    def _concluir(
        self, processo: LinhaProcesso, r: ResultadoExtracao,
        tmp: Path, destino: Path, tentativa: int,
    ) -> ResultadoProcesso:
        artefatos = []
        detalhe: dict = {"pasta_benner": r.pasta_benner,
                         "docs_listados_popup": r.docs_listados_popup}

        # ---- ZIP ----
        tem_docs = r.caminho_zip is not None
        if tem_docs:
            info = validar_zip(r.caminho_zip)
            if not info.valido:
                return self._falhar(processo, Estado.ERRO,
                                    f"zip invalido: {info.motivo}", tentativa)

            ok, motivo = conferir_contagem(info, r.docs_listados_popup)
            if not ok:
                # G2 — o pacote incompleto morre aqui, nunca vira CONCLUIDO.
                return self._falhar(processo, Estado.ERRO, motivo, tentativa)

            artefatos.append(registrar_artefato(r.caminho_zip, "passo5", validar_como_zip=True))
            detalhe["docs_no_zip"] = info.entradas
            detalhe["arquivo_zip"] = r.caminho_zip.name
        elif r.docs_listados_popup > 0:
            # Popup listou documentos mas nada foi baixado — não é "zero legítimo".
            return self._falhar(processo, Estado.ERRO,
                                f"popup listou {r.docs_listados_popup} documentos e nenhum "
                                "download ocorreu", tentativa)

        # ---- Pedidos ----
        tem_pedidos = r.caminho_pedidos is not None
        if tem_pedidos:
            artefatos.append(registrar_artefato(r.caminho_pedidos, "passo6"))

        # §6 — ZIP e XLSX falham independentemente. PARCIAL retenta só o que falta,
        # em vez de rebaixar 131 MB por causa de um XLSX de 3 KB.
        docs_esperados = r.docs_listados_popup > 0
        if (docs_esperados and not tem_docs) or not tem_pedidos:
            faltando = []
            if docs_esperados and not tem_docs:
                faltando.append("documentos")
            if not tem_pedidos:
                faltando.append("pedidos")

            # O motivo, quando existe, viaja junto: "faltando: pedidos" sozinho não
            # distingue timeout de seletor errado nem de processo sem pedidos.
            causa = r.selecao.get("pedidos_erro", "")
            observacao = f"faltando: {', '.join(faltando)}"
            if causa:
                observacao += f" — {causa}"

            return self._falhar(processo, Estado.PARCIAL, observacao, tentativa, detalhe)

        if not artefatos:
            return self._falhar(processo, Estado.ERRO, "nenhum artefato produzido", tentativa)

        # Reprocessamento de pasta que já existe: só é seguro apagar o que o próprio
        # robô produziu e que falhou a própria verificação. Ver `_liberar_destino`.
        try:
            self._liberar_destino(destino)
        except Exception as erro:
            return self._falhar(processo, Estado.ERRO, limpar(erro), tentativa, detalhe)

        # ---- manifest + promoção atômica (G11) ----
        Manifest(
            processo_planilha=processo.numero,
            processo_normalizado=processo.normalizado,
            pasta_benner=r.pasta_benner,
            numero_conferido_na_tela=r.numero_na_tela,
            selecao=r.selecao,
            artefatos=artefatos,
            documentos_listados_na_popup=r.documentos,
            completo=True,
        ).gravar(tmp)

        try:
            promover(tmp, destino)
        except Exception as erro:
            return self._falhar(processo, Estado.ERRO, f"promocao falhou: {limpar(erro)}",
                                tentativa, detalhe)

        detalhe["pedidos_exportados"] = "SIM" if tem_pedidos else "NAO"
        detalhe["docs_baixados"] = "SIM" if tem_docs else "NAO"
        detalhe["selecao"] = r.selecao

        self._registrar(processo, Estado.CONCLUIDO, tentativa=tentativa,
                        pasta_destino=destino.name, **detalhe)

        return ResultadoProcesso(processo, Estado.CONCLUIDO, pasta_destino=destino.name,
                                 tentativas=tentativa, detalhe=detalhe)

    # ---------------------------------------------------------------- apoio

    @staticmethod
    def _liberar_destino(destino: Path) -> None:
        """Remove uma pasta de destino anterior — mas só se ela for comprovadamente nossa.

        O critério de "nossa" é ter um `_manifest.json`. Uma pasta com o nome de um
        processo mas SEM manifest foi montada por uma pessoa (a pasta de referência é
        exatamente isso), e apagá-la seria destruir trabalho manual. Nesse caso a
        colisão é reportada, nunca resolvida em silêncio.

        Pasta nossa cujo manifest ainda valida também não é apagada: se ela valida, o
        processo não deveria estar sendo reprocessado.
        """
        import shutil

        if not destino.exists():
            return

        if not (destino / "_manifest.json").exists():
            raise FileExistsError(
                f"destino {destino.name} existe sem _manifest.json — nao foi produzido "
                "pelo robo. Colisao reportada, nada foi apagado."
            )

        ok, _ = manifest_valido(destino)
        if ok:
            # `--forcar` mexe no estado do LEDGER, não no disco. Uma pasta que passa
            # na própria verificação é trabalho bom; apagá-la porque alguém pediu
            # reprocessamento seria destruir o que se queria proteger.
            raise FileExistsError(
                f"destino {destino.name} ja existe e o manifest dele VALIDA. "
                "Nada foi apagado. Se a intencao e refazer mesmo assim, remova a "
                "pasta a mao primeiro — o robo nao apaga saida integra."
            )

        shutil.rmtree(destino)

    def _falhar(self, processo, status: Estado, observacao: str,
                tentativa: int, detalhe: dict | None = None) -> ResultadoProcesso:
        self._registrar(processo, status, tentativa=tentativa,
                        observacao=observacao, **(detalhe or {}))
        return ResultadoProcesso(processo, status, observacao=observacao,
                                 tentativas=tentativa, detalhe=detalhe or {})

    def _registrar(self, processo: LinhaProcesso, status: Estado, **extra) -> None:
        self.ledger.registrar({
            "processo": processo.numero,
            "processo_normalizado": processo.normalizado,
            "status": status.value,
            **extra,
        })


def resumir(resultados: list[ResultadoProcesso]) -> dict[str, int]:
    contagem: dict[str, int] = {}
    for r in resultados:
        contagem[r.status.value] = contagem.get(r.status.value, 0) + 1
    return contagem
