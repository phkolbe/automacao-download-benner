"""Peça 13 — a máquina de estados da §6, coberta integralmente.

Extrator falso, para provocar sem custo os caminhos que contra o Benner real seriam
caros ou impossíveis: sessão caindo, ambiguidade, ZIP incompleto, seleção não resolvida.
"""

import zipfile
from pathlib import Path

import pytest

from benner_rpa.core.estados import Estado
from benner_rpa.core.ledger import Ledger
from benner_rpa.core.lote import (
    NumeroDivergente,
    Orquestrador,
    ProcessoAmbiguo,
    ProcessoNaoEncontrado,
    ResultadoExtracao,
    SelecaoIncompleta,
    resumir,
)
from benner_rpa.core.manifest import manifest_valido
from benner_rpa.core.planilha import LinhaProcesso

PROC = LinhaProcesso(2, "CCR", "Fulano", "0000000-22.2023.5.15.0002")
PROC2 = LinhaProcesso(3, "CCR", "Beltrano", "1000001-33.2026.5.02.0003")

SELECAO_OK = {
    "itens_por_pagina": 10, "link_restantes_presente": True,
    "link_restantes_acionado": True, "link_ausente_ao_baixar": True,
}


def _zip(destino: Path, entradas: int) -> Path:
    caminho = destino / "Lote_de_documentos_TRAB.000003.zip"
    with zipfile.ZipFile(caminho, "w") as z:
        for i in range(entradas):
            z.writestr(f"doc{i:03d}.pdf", b"conteudo" * 400)
    return caminho


def _pedidos(destino: Path) -> Path:
    caminho = destino / "Pedidos.xlsx"
    caminho.write_bytes(b"PK\x03\x04" + b"planilha" * 200)
    return caminho


PADRAO = object()   # distingue "não informado" de um None explícito


class ExtratorFalso:
    """Configurável para cada cenário. Conta chamadas para provar retentativa."""

    def __init__(self, *, docs=93, no_zip=PADRAO, pedidos=True, erro=None,
                 sessao_cai_em=(), numero_na_tela=None, erros_ate=0):
        self.docs = docs
        # `no_zip=None` significa "nenhum ZIP produzido"; omitir significa "tantos
        # quanto a popup listou". Sem o sentinela os dois colapsam no mesmo caso.
        self.no_zip = docs if no_zip is PADRAO else no_zip
        self.pedidos = pedidos
        self.erro = erro
        self.sessao_cai_em = set(sessao_cai_em)
        self.numero_na_tela = numero_na_tela
        self.erros_ate = erros_ate

        self.chamadas = 0
        self.reconexoes = 0
        self.fechado = False

    def sessao_viva(self) -> bool:
        return (self.chamadas + 1) not in self.sessao_cai_em

    def reconectar(self) -> None:
        self.reconexoes += 1

    def extrair(self, processo, destino: Path) -> ResultadoExtracao:
        self.chamadas += 1

        if self.erro and self.chamadas > self.erros_ate:
            raise self.erro
        if self.erro and self.chamadas <= self.erros_ate:
            raise self.erro

        return ResultadoExtracao(
            pasta_benner="TRAB.000003",
            numero_na_tela=self.numero_na_tela or processo.numero,
            docs_listados_popup=self.docs,
            documentos=[{"nome": f"doc{i}"} for i in range(self.docs)],
            caminho_zip=_zip(destino, self.no_zip) if self.no_zip is not None and self.docs else None,
            caminho_pedidos=_pedidos(destino) if self.pedidos else None,
            selecao=dict(SELECAO_OK),
        )

    def fechar(self) -> None:
        self.fechado = True


def _orq(tmp_path, extrator, **kw) -> Orquestrador:
    kw.setdefault("throttle_s", 0)
    o = Orquestrador(
        extrator=extrator,
        raiz_saida=tmp_path / "saida",
        ledger=Ledger(tmp_path / "saida" / "_logs" / "ledger.jsonl"),
        **kw,
    )
    o.dormir = lambda _s: None      # sem espera real nos testes
    return o


# ---------------------------------------------------------------- caminho feliz

def test_processo_completo_vira_concluido(tmp_path):
    o = _orq(tmp_path, ExtratorFalso())
    (r,) = o.executar([PROC])

    assert r.status is Estado.CONCLUIDO
    assert r.detalhe["docs_no_zip"] == 93
    assert r.detalhe["arquivo_zip"] == "Lote_de_documentos_TRAB.000003.zip"

    pasta = tmp_path / "saida" / PROC.nome_pasta
    assert manifest_valido(pasta)[0]
    assert (pasta / "Pedidos.xlsx").exists()


def test_nome_do_zip_do_servidor_e_preservado(tmp_path):
    """Carrega o identificador da pasta no Benner — renomear jogaria auditoria fora."""
    o = _orq(tmp_path, ExtratorFalso())
    o.executar([PROC])

    pasta = tmp_path / "saida" / PROC.nome_pasta
    assert (pasta / "Lote_de_documentos_TRAB.000003.zip").exists()
    assert not (pasta / "documentos.zip").exists()


def test_layout_da_pasta_e_plano_como_a_referencia(tmp_path):
    o = _orq(tmp_path, ExtratorFalso())
    o.executar([PROC])

    pasta = tmp_path / "saida" / PROC.nome_pasta
    assert not [p for p in pasta.iterdir() if p.is_dir()]
    assert {p.name for p in pasta.iterdir()} == {
        "Lote_de_documentos_TRAB.000003.zip", "Pedidos.xlsx", "_manifest.json",
    }


# ---------------------------------------------------------------- tempo

def test_manifest_registra_inicio_fim_e_duracao(tmp_path):
    """O manifest precisa dizer QUANDO começou e QUANTO levou."""
    import json

    relogio = iter([100.0, 145.5])          # início e fim, 45,5s de diferença
    o = _orq(tmp_path, ExtratorFalso())
    o.agora = lambda: next(relogio)
    o.executar([PROC])

    m = json.loads(
        (tmp_path / "saida" / PROC.nome_pasta / "_manifest.json").read_text(encoding="utf-8")
    )

    assert m["duracao_s"] == 45.5
    assert m["duracao"] == "46s"   # 45,5s arredonda para 46
    assert m["tentativas"] == 1
    assert m["iniciado_em"] and m["concluido_em"]
    assert m["iniciado_em"] <= m["concluido_em"]


def test_duracao_cobre_as_retentativas(tmp_path):
    """O tempo é o que o processo custou de VERDADE, não o da última passada.

    Um processo que falhou duas vezes e fechou na terceira custou o tempo das três.
    """
    import json

    relogio = iter([10.0, 130.0])           # início da 1a tentativa, fim da 3a
    ex = ExtratorFalso(pedidos=False, erros_ate=0)

    # falha nas duas primeiras, entrega na terceira
    original = ex.extrair
    def instavel(processo, destino):
        r = original(processo, destino)
        if ex.chamadas < 3:
            r.caminho_pedidos = None
        return r
    ex.extrair = instavel
    ex.pedidos = True

    o = _orq(tmp_path, ex, max_tentativas=3)
    o.agora = lambda: next(relogio)
    (r,) = o.executar([PROC])

    assert r.status is Estado.CONCLUIDO
    assert ex.chamadas == 3

    m = json.loads(
        (tmp_path / "saida" / PROC.nome_pasta / "_manifest.json").read_text(encoding="utf-8")
    )
    assert m["duracao_s"] == 120.0
    assert m["duracao"] == "2m 00s"
    assert m["tentativas"] == 3


def test_duracao_vai_para_o_ledger(tmp_path):
    relogio = iter([0.0, 7.0])
    o = _orq(tmp_path, ExtratorFalso())
    o.agora = lambda: next(relogio)
    o.executar([PROC])

    final = [e for e in o.ledger.eventos() if e["status"] == "CONCLUIDO"][-1]
    assert final["duracao_s"] == 7.0
    assert final["duracao"] == "7s"
    assert final["iniciado_em"] and final["concluido_em"]


def test_humanizar_duracao():
    from benner_rpa.core.manifest import humanizar_duracao

    assert humanizar_duracao(0) == "0s"
    assert humanizar_duracao(45.4) == "45s"
    assert humanizar_duracao(90) == "1m 30s"
    assert humanizar_duracao(3725) == "1h 02m 05s"
    assert humanizar_duracao(-1) == "-"


# ---------------------------------------------------------------- G2

def test_zip_com_menos_entradas_que_a_popup_vira_erro(tmp_path):
    """A falha silenciosa: popup lista 93, ZIP traz 10."""
    o = _orq(tmp_path, ExtratorFalso(docs=93, no_zip=10))
    (r,) = o.executar([PROC])

    assert r.status is Estado.ERRO
    assert "G2" in r.observacao
    assert not (tmp_path / "saida" / PROC.nome_pasta).exists()


def test_selecao_incompleta_nao_degrada_para_parcial(tmp_path):
    o = _orq(tmp_path, ExtratorFalso(erro=SelecaoIncompleta("link ainda oferecido")))
    (r,) = o.executar([PROC])

    assert r.status is Estado.ERRO
    assert r.status is not Estado.PARCIAL


# ---------------------------------------------------------------- G4

def test_numero_divergente_vira_erro_sem_pasta(tmp_path):
    o = _orq(tmp_path, ExtratorFalso(erro=NumeroDivergente("tela=1001067 planilha=0012033")))
    (r,) = o.executar([PROC])

    assert r.status is Estado.ERRO
    assert not (tmp_path / "saida" / PROC.nome_pasta).exists()


# ---------------------------------------------------------------- terminais

def test_so_processos_sem_pasta_recomenda_98(tmp_path):
    """O caso que quem opera à mão já chamava de 98.

    O processo EXISTE no Benner, mas só como processo — sem pasta, não há acervo.
    É diferente de "não existe", e o robô precisa dizer qual código escrever.
    """
    from benner_rpa.core.lote import SoProcessosSemPasta

    ex = ExtratorFalso(erro=SoProcessosSemPasta("so PROCESSOS (PASTAS)"))
    (r,) = _orq(tmp_path, ex).executar([PROC])

    assert r.status is Estado.NAO_ENCONTRADO       # terminal, o robô não retenta
    assert r.detalhe["codigo_planilha"] == 98
    assert ex.chamadas == 1


def test_nao_encontrado_recomenda_99(tmp_path):
    ex = ExtratorFalso(erro=ProcessoNaoEncontrado("Nenhum registro encontrado"))
    (r,) = _orq(tmp_path, ex).executar([PROC])

    assert r.status is Estado.NAO_ENCONTRADO
    assert r.detalhe["codigo_planilha"] == 99


def test_98_e_um_nao_encontrado_mas_distinguivel(tmp_path):
    """Herda para cair no mesmo estado terminal, sem perder a distinção."""
    from benner_rpa.core.lote import SoProcessosSemPasta

    assert issubclass(SoProcessosSemPasta, ProcessoNaoEncontrado)
    assert SoProcessosSemPasta.codigo_planilha == 98
    assert ProcessoNaoEncontrado.codigo_planilha == 99



def test_nao_encontrado_e_terminal_e_nao_retenta(tmp_path):
    ex = ExtratorFalso(erro=ProcessoNaoEncontrado("sem item no grupo PASTAS"))
    o = _orq(tmp_path, ex)
    (r,) = o.executar([PROC])

    assert r.status is Estado.NAO_ENCONTRADO
    assert ex.chamadas == 1


def test_ambiguo_e_terminal_e_nunca_resolvido_pelo_robo(tmp_path):
    ex = ExtratorFalso(erro=ProcessoAmbiguo("2 itens no grupo PASTAS"))
    o = _orq(tmp_path, ex)
    (r,) = o.executar([PROC])

    assert r.status is Estado.AMBIGUO
    assert ex.chamadas == 1


def test_terminal_nao_e_reprocessado_na_reexecucao(tmp_path):
    ex = ExtratorFalso(erro=ProcessoNaoEncontrado("nao existe"))
    o = _orq(tmp_path, ex)
    o.executar([PROC])

    o2 = _orq(tmp_path, ex)
    assert o2.executar([PROC]) == []
    assert ex.chamadas == 1


# ---------------------------------------------------------------- PARCIAL

def test_falta_de_pedidos_vira_parcial(tmp_path):
    o = _orq(tmp_path, ExtratorFalso(pedidos=False), max_tentativas=1)
    (r,) = o.executar([PROC])

    assert r.status is Estado.PARCIAL
    assert "pedidos" in r.observacao


def test_parcial_retenta(tmp_path):
    ex = ExtratorFalso(pedidos=False)
    o = _orq(tmp_path, ex, max_tentativas=3)
    (r,) = o.executar([PROC])

    assert r.status is Estado.PARCIAL
    assert ex.chamadas == 3


# ---------------------------------------------------------------- zero legítimo

def test_processo_sem_documentos_conclui_com_docs_baixados_nao(tmp_path):
    """Popup vazia é CONCLUIDO. Diferente de popup que não carregou."""
    o = _orq(tmp_path, ExtratorFalso(docs=0, no_zip=None))
    (r,) = o.executar([PROC])

    assert r.status is Estado.CONCLUIDO
    assert r.detalhe["docs_baixados"] == "NAO"
    assert r.detalhe["pedidos_exportados"] == "SIM"


def test_popup_lista_mas_nada_baixa_vira_erro(tmp_path):
    """Distingue "zero legítimo" de "popup não carregou"."""
    o = _orq(tmp_path, ExtratorFalso(docs=47, no_zip=None), max_tentativas=1)
    (r,) = o.executar([PROC])

    assert r.status is Estado.ERRO
    assert "nenhum download" in r.observacao


# ---------------------------------------------------------------- sessão

def test_sessao_caida_reconecta_e_retoma_o_mesmo_processo(tmp_path):
    ex = ExtratorFalso(sessao_cai_em={1})
    o = _orq(tmp_path, ex)
    (r,) = o.executar([PROC])

    assert ex.reconexoes == 1
    assert r.status is Estado.CONCLUIDO


# ---------------------------------------------------------------- reexecução

def test_reexecucao_pula_concluido_sem_tocar_o_benner(tmp_path):
    ex = ExtratorFalso()
    _orq(tmp_path, ex).executar([PROC])
    assert ex.chamadas == 1

    ex2 = ExtratorFalso()
    assert _orq(tmp_path, ex2).executar([PROC]) == []
    assert ex2.chamadas == 0


def test_remover_arquivo_faz_reprocessar_so_aquele_processo(tmp_path):
    ex = ExtratorFalso()
    _orq(tmp_path, ex).executar([PROC, PROC2])
    assert ex.chamadas == 2

    (tmp_path / "saida" / PROC.nome_pasta / "Pedidos.xlsx").unlink()

    ex2 = ExtratorFalso()
    resultados = _orq(tmp_path, ex2).executar([PROC, PROC2])

    assert len(resultados) == 1
    assert resultados[0].processo.numero == PROC.numero
    assert ex2.chamadas == 1


def test_terminal_errado_fica_preso_sem_forcar(tmp_path):
    """O que aconteceu de verdade em 28/08/2026.

    Um defeito no robô classificou como NAO_ENCONTRADO um processo que existe.
    Estado terminal, gravado no ledger: a execução seguinte pula o processo e nem
    toca no Benner. Sem `--forcar`, ele sairia do lote para sempre.
    """
    ex = ExtratorFalso(erro=ProcessoNaoEncontrado("defeito: fill() nao dispara a busca"))
    _orq(tmp_path, ex).executar([PROC])

    ex2 = ExtratorFalso()      # robô consertado
    assert _orq(tmp_path, ex2).executar([PROC]) == []
    assert ex2.chamadas == 0, "o processo foi pulado — e o Benner nem foi consultado"


def test_forcar_reprocessa_terminal_errado(tmp_path):
    ex = ExtratorFalso(erro=ProcessoNaoEncontrado("defeito"))
    _orq(tmp_path, ex).executar([PROC])

    ex2 = ExtratorFalso()
    (r,) = _orq(tmp_path, ex2, forcar=True).executar([PROC])

    assert r.status is Estado.CONCLUIDO
    assert ex2.chamadas == 1


def test_forcar_registra_o_motivo_no_ledger(tmp_path):
    """A decisão de reprocessar é humana — o ledger tem que dizer isso."""
    ex = ExtratorFalso(erro=ProcessoNaoEncontrado("defeito"))
    o = _orq(tmp_path, ex)
    o.executar([PROC])

    o2 = _orq(tmp_path, ExtratorFalso(), forcar=True)
    o2.executar([PROC])

    forcados = [e for e in o2.ledger.eventos() if e.get("origem") == "--forcar"]
    assert len(forcados) == 1
    assert "NAO_ENCONTRADO" in forcados[0]["motivo"]


def test_forcar_nao_toca_saida_integra_nem_baixa_de_novo(tmp_path):
    """`--forcar` age sobre o LEDGER, não sobre o disco.

    Uma pasta que passa na própria verificação é trabalho bom. `--forcar` existe para
    escapar de uma classificação ERRADA no ledger — se o disco tem pacote válido, não
    há nada de errado para escapar.

    Antes o robô baixava tudo de novo e só então a promoção era recusada: 131 MB
    gastos para nada. Agora a checagem do disco vem antes e o processo é pulado sem
    tocar a rede.
    """
    _orq(tmp_path, ExtratorFalso()).executar([PROC])
    destino = tmp_path / "saida" / PROC.nome_pasta
    antes = {p.name for p in destino.iterdir()}

    ex = ExtratorFalso()
    assert _orq(tmp_path, ex, forcar=True, max_tentativas=1).executar([PROC]) == []

    assert ex.chamadas == 0, "nao pode nem tentar baixar — a saida ja esta integra"
    assert {p.name for p in destino.iterdir()} == antes


def test_forcar_ainda_escapa_de_terminal_errado(tmp_path):
    """A razão de `--forcar` existir continua valendo: sem lastro no disco, ele age."""
    ex = ExtratorFalso(erro=ProcessoNaoEncontrado("classificacao errada"))
    _orq(tmp_path, ex).executar([PROC])

    ex2 = ExtratorFalso()
    (r,) = _orq(tmp_path, ex2, forcar=True).executar([PROC])

    assert r.status is Estado.CONCLUIDO
    assert ex2.chamadas == 1


def test_lote_vazio_e_distinguivel_de_lote_bem_sucedido(tmp_path):
    """`all([])` é True — um lote vazio não pode ser lido como sucesso.

    O orquestrador devolve `[]`; quem chama precisa tratar isso como caso próprio.
    """
    ex = ExtratorFalso(erro=ProcessoNaoEncontrado("nao existe"))
    _orq(tmp_path, ex).executar([PROC])

    vazio = _orq(tmp_path, ExtratorFalso()).executar([PROC])

    assert vazio == []
    assert all(r.status is Estado.CONCLUIDO for r in vazio) is True   # a armadilha
    assert not vazio                                                  # a defesa


def test_pasta_humana_sem_manifest_nunca_e_apagada(tmp_path):
    """A pasta de referência é exatamente isto: nome de processo, sem manifest.

    Reprocessar não pode destruí-la. A colisão é reportada, e o conteúdo fica.
    """
    destino = tmp_path / "saida" / PROC.nome_pasta
    destino.mkdir(parents=True)
    (destino / "Lote_de_documentos_TRAB.000003.zip").write_bytes(b"trabalho humano")
    (destino / "Pedidos.xlsx").write_bytes(b"montado a mao")

    o = _orq(tmp_path, ExtratorFalso(), max_tentativas=1)
    (r,) = o.executar([PROC])

    assert r.status is Estado.ERRO
    assert "sem _manifest.json" in r.observacao
    assert (destino / "Lote_de_documentos_TRAB.000003.zip").read_bytes() == b"trabalho humano"
    assert (destino / "Pedidos.xlsx").exists()


def test_pasta_nossa_com_manifest_valido_nao_e_apagada(tmp_path):
    """Se o manifest valida, o processo nem deveria estar sendo reprocessado."""
    _orq(tmp_path, ExtratorFalso()).executar([PROC])
    destino = tmp_path / "saida" / PROC.nome_pasta
    antes = {p.name for p in destino.iterdir()}

    from benner_rpa.core.lote import Orquestrador

    with pytest.raises(FileExistsError, match="VALIDA"):
        Orquestrador._liberar_destino(destino)

    assert {p.name for p in destino.iterdir()} == antes


def test_interrupcao_deixa_processo_pendente_sem_tmp_orfa(tmp_path):
    ex = ExtratorFalso(erro=RuntimeError("queda"), )
    o = _orq(tmp_path, ex, max_tentativas=1)
    o.executar([PROC])

    # A execução seguinte limpa a .tmp e reprocessa.
    ex2 = ExtratorFalso()
    (r,) = _orq(tmp_path, ex2).executar([PROC])

    assert r.status is Estado.CONCLUIDO
    work = tmp_path / "saida" / "_work"
    assert not [p for p in work.iterdir() if p.name.endswith(".tmp")]


# ---------------------------------------------------------------- lote

def test_lote_nao_interrompe_por_processo_nao_encontrado(tmp_path):
    class Misto(ExtratorFalso):
        def extrair(self, processo, destino):
            if processo.numero == PROC.numero:
                self.chamadas += 1
                raise ProcessoNaoEncontrado("nao existe")
            return super().extrair(processo, destino)

    resultados = _orq(tmp_path, Misto()).executar([PROC, PROC2])

    assert resumir(resultados) == {"NAO_ENCONTRADO": 1, "CONCLUIDO": 1}


def test_limite_por_execucao_corta_o_lote(tmp_path):
    processos = [
        LinhaProcesso(i, "CCR", f"P{i}", f"000{i:04d}-71.2023.5.15.0002")
        for i in range(2, 12)
    ]
    resultados = _orq(tmp_path, ExtratorFalso(), limite_por_execucao=3).executar(processos)

    assert len(resultados) == 3


def test_throttle_entre_processos(tmp_path):
    esperas = []
    o = _orq(tmp_path, ExtratorFalso(), throttle_s=3)
    o.dormir = esperas.append

    o.executar([PROC, PROC2])

    assert esperas == [3]      # entre os dois, não antes do primeiro


def test_ledger_guarda_a_trilha_completa(tmp_path):
    o = _orq(tmp_path, ExtratorFalso())
    o.executar([PROC])

    eventos = o.ledger.eventos()
    assert [e["status"] for e in eventos] == ["EM_ANDAMENTO", "CONCLUIDO"]
    assert eventos[-1]["docs_no_zip"] == 93
    assert eventos[-1]["selecao"]["link_restantes_acionado"] is True
