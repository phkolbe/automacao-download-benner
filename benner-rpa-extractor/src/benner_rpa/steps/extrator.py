"""O `Extrator` concreto — implementa o protocolo que `core/lote.py` consome.

Todo o Playwright do projeto está abaixo desta linha. O orquestrador não sabe que
ele existe, o que é o que permite testar a máquina de estados sem browser.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..core.config import Config, Credenciais
from ..core.lote import ResultadoExtracao
from ..core.planilha import LinhaProcesso
from ..core.segredos import limpar
from . import busca, documentos, pedidos
from .seletores import MapaSeletores


@dataclass
class ExtratorBenner:
    """Sessão única, um processo por vez (§1).

    `base_url` existe para os testes offline: apontando para uma fixture `file://`,
    o mesmo código roda contra a reprodução sem tocar o Benner.
    """

    cfg: Config
    credenciais: Credenciais | None = None
    mapa: MapaSeletores = field(default_factory=MapaSeletores.carregar)
    headless: bool = True
    base_url: str | None = None

    _pw: object | None = field(default=None, repr=False)
    _browser: object | None = field(default=None, repr=False)
    _context: object | None = field(default=None, repr=False)
    _page: object | None = field(default=None, repr=False)

    # ---------------------------------------------------------------- sessão

    def abrir(self) -> None:
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self.headless)

        # O Metronic é responsivo e colapsa a barra de comandos em telas estreitas —
        # e o Benner duplica o id do controle `Ações` entre a versão da barra e a
        # aninhada. No padrão do Playwright (1280px) a variante da barra existe no
        # DOM mas fica INVISÍVEL, e o clique dá timeout sem dizer por quê.
        # 1860x950 é a largura em que os screenshots de referência foram tirados.
        self._context = self._browser.new_context(
            accept_downloads=True,
            viewport={"width": 1860, "height": 950},
        )
        self._context.set_default_timeout(self.cfg.benner["timeout_pagina_ms"])
        self._page = self._context.new_page()

        if self.base_url is None:
            self._login()

    def _login(self) -> None:
        # G10 — nenhuma conexão real sem autorização humana explícita.
        self.cfg.exigir_autorizacao_de_acesso("login no Benner")

        if self.credenciais is None:
            raise RuntimeError("login exige credenciais")

        page = self._page
        page.goto(self.credenciais.url)

        # Seletores vindos do DOM real da tela (mapeada em 28/08/2026), não de
        # convenção. As três suposições convencionais estavam erradas: os campos não
        # têm <label>, o botão é um <a>, e o texto é "Acessar" e não "Entrar".
        self.mapa.localizar(page, "login.campo_usuario").first.fill(self.credenciais.usuario)
        self.mapa.localizar(page, "login.campo_senha").first.fill(self.credenciais.senha)
        self.mapa.localizar(page, "login.botao_entrar").first.click()

        page.wait_for_load_state("networkidle")

        # A sonda é o que distingue "login deu certo" de "voltou para /Login em
        # silêncio" — WebForms responde 200 nos dois casos.
        if not self.sessao_viva():
            raise RuntimeError(
                f"login nao autenticou: a pagina apos 'Acessar' e {limpar(page.url)} "
                "e o menu 'Pastas' nao esta presente. Credenciais ou fluxo mudaram."
            )

    def sessao_viva(self) -> bool:
        """Sonda barata antes de cada processo (§7.4).

        Sessão expirada aparece como "elemento não encontrado", indistinguível de
        mudança de layout se não for checada explicitamente.
        """
        if self._page is None:
            return False
        try:
            sonda = self.mapa.localizar(self._page, "login.sonda_sessao")
            return sonda.count() > 0
        except Exception:
            return False

    def reconectar(self) -> None:
        self.fechar()
        self.abrir()

    def fechar(self) -> None:
        for recurso, metodo in ((self._context, "close"), (self._browser, "close"),
                                (self._pw, "stop")):
            if recurso is not None:
                try:
                    getattr(recurso, metodo)()
                except Exception:
                    pass
        self._pw = self._browser = self._context = self._page = None

    def __enter__(self):
        self.abrir()
        return self

    def __exit__(self, *_exc):
        self.fechar()

    # ---------------------------------------------------------------- extração

    def _documentos_ou_reaproveitar(self, page, destino: Path, timeout_ms: int) -> dict:
        from ..core.zip_seguro import validar_zip

        existentes = sorted(Path(destino).glob("*.zip"))
        for caminho in existentes:
            info = validar_zip(caminho)
            if info.valido and info.entradas:
                return {
                    "selecao": {"reaproveitado_de_tentativa_anterior": True},
                    "documentos": [{"nome": n} for n in info.nomes],
                    "docs_listados_popup": info.entradas,
                    "caminho_zip": caminho,
                }

        return documentos.extrair_documentos(
            page, self.mapa, destino, timeout_ms=timeout_ms
        )

    def extrair(self, processo: LinhaProcesso, destino: Path) -> ResultadoExtracao:
        page = self._page
        timeout_download = self.cfg.benner["timeout_download_ms"]

        # Estado limpo antes de CADA processo. O Benner preserva o último contexto, e
        # a popup de download é um `<iframe baixardocs.aspx>` que fica sobreposto
        # interceptando cliques. Sem esta volta ao painel, o processo N herda o modal
        # aberto do processo N-1 — falha em cascata num lote de 333.
        page.goto(self.base_url or self.mapa.entrada("login.url_painel")["valor"],
                  wait_until="networkidle")

        identificacao = busca.buscar_e_abrir(page, self.mapa, processo.numero)
        url_detalhe = page.url

        # Retentativa de PARCIAL: se um ZIP válido já está na pasta de trabalho, o
        # download não se repete. É o que torna PARCIAL barato de fato — e não só no
        # nome. A validade é conferida, nunca presumida pela existência do arquivo.
        docs = self._documentos_ou_reaproveitar(page, destino, timeout_download)

        # A popup de documentos é um `<iframe baixardocs.aspx>` que PERMANECE na página
        # depois do download, sobreposto ao painel de PEDIDOS. O clique em
        # "Exportar para Excel" pousava no iframe — nem `force=True` resolvia, porque o
        # clique chegava mesmo, só que no elemento errado. O postback nunca disparava, e
        # a espera pelo download morria em timeout sem nenhuma pista.
        #
        # Recarregar o detalhamento devolve a página limpa. É o mesmo remédio do
        # vazamento entre processos, aplicado agora DENTRO do processo.
        page.goto(url_detalhe, wait_until="networkidle")
        page.wait_for_timeout(1500)

        try:
            ped = pedidos.exportar(
                page, self.mapa, destino,
                timeout_ms=self.cfg.benner.get("timeout_export_ms", 90000),
            )
        except Exception as erro:
            # PARCIAL cuida disto: retenta só o XLSX, sem rebaixar o ZIP já baixado.
            # Mas o MOTIVO tem que sobreviver — "faltando: pedidos" sem causa não
            # diz se foi timeout, seletor errado ou processo sem pedidos.
            ped = {
                "caminho": None, "via_ver_todos": False, "linhas_na_tela": -1,
                "erro": limpar(erro).splitlines()[0][:200],
            }

        selecao = dict(docs["selecao"])
        selecao["pedidos_via_ver_todos"] = ped["via_ver_todos"]
        selecao["pedidos_linhas_na_tela"] = ped["linhas_na_tela"]
        if ped.get("erro"):
            selecao["pedidos_erro"] = ped["erro"]

        return ResultadoExtracao(
            pasta_benner=identificacao["pasta_benner"],
            numero_na_tela=identificacao["numero_na_tela"],
            docs_listados_popup=docs["docs_listados_popup"],
            documentos=docs["documentos"],
            caminho_zip=docs["caminho_zip"],
            caminho_pedidos=ped["caminho"],
            selecao=selecao,
        )
