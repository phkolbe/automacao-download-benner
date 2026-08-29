"""G1, G2, G3 e G12 exercitados contra as fixtures, com Playwright de verdade.

Estes são os gates que só podem ser provados contra um DOM. As fixtures existem
exatamente para isto: rodar o código real de localização e clique, offline.
"""

from pathlib import Path

import pytest

from benner_rpa.core.lote import ProcessoAmbiguo, ProcessoNaoEncontrado, SelecaoIncompleta
from benner_rpa.steps import busca, documentos
from benner_rpa.steps.seletores import (
    MapaSeletores,
    SeletorNaoDeterminado,
    SeletorProibido,
)

pytestmark = pytest.mark.gate

FIXTURES = Path(__file__).resolve().parents[2] / "src" / "benner_rpa" / "fixtures"

sync_playwright = pytest.importorskip("playwright.sync_api").sync_playwright


@pytest.fixture(scope="module")
def navegador():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        yield b
        b.close()


@pytest.fixture
def mapa():
    return MapaSeletores.carregar()


def _pagina(navegador, nome: str):
    arquivo = FIXTURES / nome
    if not arquivo.exists():
        pytest.skip(f"fixture ausente: {nome}")
    pagina = navegador.new_page(viewport={"width": 1720, "height": 840})
    pagina.goto(arquivo.resolve().as_uri())
    pagina.wait_for_load_state("networkidle")
    return pagina


# ================================================================ G3

def test_g3_acha_o_grupo_pastas_entre_os_tres(navegador, mapa):
    """A fixture tem CAUSA RAIZ (PASTAS), PASTAS e PROCESSOS (PASTAS)."""
    page = _pagina(navegador, "02-busca-agrupada.html")
    try:
        heading = mapa.localizar(page, "resultado_busca.grupo_pastas")
        assert heading.count() == 1
        assert heading.first.inner_text().strip() == "PASTAS"
    finally:
        page.close()


def test_g3_match_parcial_pegaria_o_grupo_errado(navegador):
    """Prova por que o gate existe: 'contém PASTAS' acha três, e o primeiro é o errado."""
    page = _pagina(navegador, "02-busca-agrupada.html")
    try:
        parcial = page.locator("li.searcher-list-header").filter(has_text="PASTAS")
        assert parcial.count() == 3
        assert parcial.first.inner_text().strip() == "CAUSA RAIZ (PASTAS)"
    finally:
        page.close()


def test_g3_os_cabecalhos_nao_sao_heading_no_benner_real(navegador):
    """Foi isto que derrubou a primeira execução real.

    `role=heading` não acha nada: os cabeçalhos são `<li>` sem role. A fixture
    espelha isso — se ela voltasse a usar `<h2>`, o teste passaria contra uma
    ficção e o robô falharia em produção.
    """
    page = _pagina(navegador, "02-busca-agrupada.html")
    try:
        assert page.get_by_role("heading", name="PASTAS", exact=True).count() == 0
        assert page.locator("li.searcher-list-header").count() == 3
    finally:
        page.close()


def test_g3_itens_do_grupo_sao_irmaos_ate_o_proximo_cabecalho(navegador, mapa):
    """A lista é plana: o escopo do grupo é uma travessia de irmãos, não um container."""
    page = _pagina(navegador, "02-busca-agrupada.html")
    try:
        itens = busca.itens_do_grupo_pastas(page, mapa)

        assert len(itens) == 1, "o grupo PASTAS tem exatamente um item nesta fixture"
        texto = itens[0].locator("span.searcher-caption").inner_text()
        assert "1000000-11.2024.5.02.0001" in texto
        assert "Estações" not in texto      # esse é o item do CAUSA RAIZ
    finally:
        page.close()


def test_g3_a_armadilha_do_role_link(navegador):
    """Os itens são `<a>` SEM href — não são links, e `role=link` acha o botão errado.

    No Benner o botão "Partes e testemunhas" vem aninhado dentro do item (a lista é
    montada por JS, então o aninhamento sobrevive). Aqui a fixture é HTML estático e
    o parser desaninha, deixando o botão como IRMÃO do item.

    A diferença torna a fixture mais exigente que o original: o botão passa a
    aparecer no meio da travessia de irmãos, e a filtragem por classe tem que
    excluí-lo. Se a lógica passa aqui, passa lá.
    """
    page = _pagina(navegador, "02-busca-agrupada.html")
    try:
        itens = page.locator("a.searcher-list-group-item")
        assert itens.count() == 3
        for i in range(itens.count()):
            assert itens.nth(i).get_attribute("href") is None, "item nao pode ter href"

        # O único `role=link` da lista é o comando — nunca o que queremos abrir.
        links = page.locator(".list-group").get_by_role("link")
        assert links.count() == 2
        for i in range(links.count()):
            assert "Partes e testemunhas" in links.nth(i).inner_text()
    finally:
        page.close()


def test_g3_travessia_ignora_o_botao_de_comando(navegador, mapa):
    """O botão fica entre o item e o próximo cabeçalho — não pode entrar no grupo."""
    page = _pagina(navegador, "02-busca-agrupada.html")
    try:
        itens = busca.itens_do_grupo_pastas(page, mapa)

        assert len(itens) == 1
        for item in itens:
            assert "Partes e testemunhas" not in item.inner_text()
    finally:
        page.close()


def test_g3_item_e_procurado_so_dentro_do_grupo_pastas(navegador, mapa):
    page = _pagina(navegador, "02-busca-agrupada.html")
    try:
        item = busca.item_do_processo(page, mapa, "1000000-11.2024.5.02.0001")
        texto = item.locator("span.searcher-caption").inner_text()

        assert "1000000-11.2024.5.02.0001" in texto
        # O item do grupo errado tem o sufixo; o do grupo PASTAS não.
        assert "Estações" not in texto
    finally:
        page.close()


def test_g3_busca_vazia_e_falha_tecnica_nao_processo_inexistente(navegador, mapa):
    """A distinção que já custou três falsos NAO_ENCONTRADO.

    Painel sem grupo nenhum significa que a busca não respondeu — falha técnica, que
    retenta. Só quando a busca RESPONDEU e nenhum grupo é `PASTAS` o processo pode
    ser declarado inexistente, porque aí é um veredicto sobre o dado.

    Sem isso, uma instabilidade momentânea apaga o processo do lote para sempre:
    `NAO_ENCONTRADO` é terminal.
    """
    from benner_rpa.steps.busca import LeituraDaTelaFalhou

    page = _pagina(navegador, "01-tela-inicial.html")   # sem resultados de busca
    try:
        assert page.locator("li.searcher-list-header").count() == 0

        with pytest.raises(LeituraDaTelaFalhou):
            busca.itens_do_grupo_pastas(page, mapa)
    finally:
        page.close()


def test_g3_grupos_presentes_sem_pastas_e_nao_encontrado(navegador, mapa):
    """O caso legítimo: a busca respondeu, mas não há grupo `PASTAS`."""
    page = _pagina(navegador, "02-busca-agrupada.html")
    try:
        page.evaluate(
            "() => { for (const li of document.querySelectorAll('li.searcher-list-header'))"
            "   if (li.textContent.trim() === 'PASTAS') li.textContent = 'OUTRO GRUPO'; }"
        )
        assert page.locator("li.searcher-list-header").count() == 3

        with pytest.raises(ProcessoNaoEncontrado, match="nenhum e exatamente"):
            busca.itens_do_grupo_pastas(page, mapa)
    finally:
        page.close()


def test_g3_numero_inexistente_e_nao_encontrado(navegador, mapa):
    page = _pagina(navegador, "02-busca-agrupada.html")
    try:
        with pytest.raises(ProcessoNaoEncontrado):
            busca.item_do_processo(page, mapa, "9999999-99.2099.9.99.9999")
    finally:
        page.close()


def test_g3_casa_pela_forma_normalizada(navegador, mapa):
    """O número sem máscara acha o mesmo item que o com máscara.

    Só na COMPARAÇÃO. Na digitação o Benner exige a máscara — ver
    `busca._como_digitar` no mapa.
    """
    page = _pagina(navegador, "02-busca-agrupada.html")
    try:
        com = busca.item_do_processo(page, mapa, "1000000-11.2024.5.02.0001")
        sem = busca.item_do_processo(page, mapa, "10000001120245020001")
        assert com.inner_text() == sem.inner_text()
    finally:
        page.close()


def test_g3_digitacao_exige_teclas_reais_e_mascara(mapa):
    """Registrado no mapa porque `fill()` produzia falso NAO_ENCONTRADO."""
    como = mapa.entrada("busca._como_digitar")

    assert como["metodo"] == "press_sequentially"
    assert "fill" in como["proibido"]
    assert "so digitos sem mascara" in como["proibido"]


# ================================================================ G1

def test_g1_menuitem_nao_existe_neste_menu(navegador):
    """No Benner os itens do menu Ações são `<a>` sem role — `menuitem` dá 0.

    A fixture reproduz isso. Se ela voltasse a usar `role="menuitem"`, o teste
    passaria contra uma ficção e o robô erraria em produção.
    """
    page = _pagina(navegador, "03-detalhamento-acoes.html")
    try:
        assert page.get_by_role("menuitem").count() == 0
        assert page.locator("div#top-CMD_ACOES").first.get_by_role("link").count() == 6
    finally:
        page.close()


def test_g1_cada_item_carrega_o_comando_de_servidor_no_id(navegador, mapa):
    """`__doPostBack('…','BTBAIXARLOTE')` — âncora independente do texto."""
    page = _pagina(navegador, "03-detalhamento-acoes.html")
    try:
        links = page.locator("div#top-CMD_ACOES").first.get_by_role("link")
        ids = [links.nth(i).get_attribute("id") for i in range(links.count())]

        assert ids[-1] == "top-BTBAIXARLOTE"
        assert ids[-2] == "top-BTINSERIRLOTE"
        # Diferem por poucos caracteres — por isso o match do id é por igualdade.
        assert "BTBAIXARLOTE" != "BTINSERIRLOTE"
        assert set(mapa.entrada("menu_acoes")["comandos_proibidos_ids"].values()) <= set(ids)
    finally:
        page.close()


def test_g1_os_seis_itens_estao_na_ordem_real(navegador):
    page = _pagina(navegador, "03-detalhamento-acoes.html")
    try:
        itens = page.locator("div#top-CMD_ACOES").first.get_by_role("link")
        textos = [itens.nth(i).inner_text().strip() for i in range(itens.count())]

        assert textos == [
            "Atualizar valores",
            "Atualizar identificador da pasta",
            "Bloqueio/Desbloqueio atualização de valores",
            "Nova mensagem",
            "Inserir documentos em lote",
            "Baixar documentos",
        ]
        assert textos[-1] == "Baixar documentos"
        assert textos[-2] == "Inserir documentos em lote"
    finally:
        page.close()


def test_g1_localiza_baixar_documentos_pelos_dois_sinais(navegador, mapa):
    """Id do comando E texto visível têm que concordar."""
    page = _pagina(navegador, "03-detalhamento-acoes.html")
    try:
        item = mapa.localizar(page, "menu_acoes.baixar_documentos")
        assert item.count() == 1
        assert item.first.get_attribute("id") == "top-BTBAIXARLOTE"
        assert item.first.inner_text().strip() == "Baixar documentos"
    finally:
        page.close()


def test_g1_clicar_recusa_se_os_dois_sinais_discordarem(navegador, mapa):
    """Se o mapa apontar para o id de ESCRITA, o clique é recusado.

    Simula um mapa editado errado: aponta para BTINSERIRLOTE mantendo o texto
    esperado 'Baixar documentos'. Os dois sinais discordam e nada é acionado.
    """
    from benner_rpa.steps import documentos as docs
    from benner_rpa.steps.seletores import MapaSeletores as M

    page = _pagina(navegador, "03-detalhamento-acoes.html")
    try:
        envenenado = M({"menu_acoes": {"baixar_documentos": {
            "estrategia": "css", "valor": "a#top-BTINSERIRLOTE",
            "nome": "Baixar documentos", "modo": "exato"}}})

        with pytest.raises(SeletorProibido, match="G1"):
            docs.clicar_baixar_documentos(page, envenenado)
    finally:
        page.close()


def test_g1_match_parcial_em_documentos_pegaria_item_de_escrita(navegador):
    """O motivo do gate: 'contém documentos' casa também 'Inserir documentos em lote'."""
    page = _pagina(navegador, "03-detalhamento-acoes.html")
    try:
        parcial = page.locator("div#top-CMD_ACOES").first.get_by_role(
            "link", name="documentos", exact=False)
        textos = [parcial.nth(i).inner_text().strip() for i in range(parcial.count())]

        assert "Inserir documentos em lote" in textos
        assert len(textos) > 1
    finally:
        page.close()


def test_g1_match_parcial_em_LOTE_pegaria_o_id_de_escrita(navegador):
    """O mesmo perigo do lado do id: BTINSERIRLOTE e BTBAIXARLOTE partilham 'LOTE'."""
    page = _pagina(navegador, "03-detalhamento-acoes.html")
    try:
        contendo = page.locator('div#top-CMD_ACOES a[id*="LOTE"]')
        assert contendo.count() == 2
    finally:
        page.close()


def test_g1_localizar_por_indice_falha_por_design(mapa):
    """Teste obrigatório do gate."""
    from benner_rpa.steps.seletores import MapaSeletores as M

    proibido = M({"x": {"y": {"estrategia": "nth=5", "nome": "Baixar documentos"}}})
    with pytest.raises(SeletorProibido, match="G1"):
        proibido.localizar(None, "x.y")


def test_g1_verificacao_de_texto_bloqueia_elemento_errado(navegador):
    """Se o mapa apontar para o item errado, a verificação para antes do clique."""
    from benner_rpa.steps.seletores import exigir_texto_exato

    page = _pagina(navegador, "03-detalhamento-acoes.html")
    try:
        errado = page.get_by_role("link", name="Inserir documentos em lote", exact=True)
        with pytest.raises(SeletorProibido, match="G1"):
            exigir_texto_exato(errado.first, "Baixar documentos", "teste")
    finally:
        page.close()


def test_g1_itens_proibidos_estao_todos_no_mapa(mapa):
    proibidos = mapa.itens_proibidos_do_menu()

    assert len(proibidos) == 5
    assert "Inserir documentos em lote" in proibidos
    assert "Baixar documentos" not in proibidos


def test_g1_zona_proibida_mapeada_para_poder_ser_bloqueada(mapa):
    """Editar/excluir do painel DOCUMENTOS existem no mapa marcados BLOQUEAR."""
    for chave in ("documentos_editar_linha", "documentos_excluir_linha"):
        e = mapa.entrada(f"zona_proibida.{chave}")
        assert e["acao"] == "BLOQUEAR"


# ================================================================ G4

def test_g4_numero_confere(navegador, mapa):
    page = _pagina(navegador, "03-detalhamento-acoes.html")
    try:
        assert busca.conferir_numero(page, mapa, "1000000-11.2024.5.02.0001")
    finally:
        page.close()


def test_g4_numero_divergente_aborta(navegador, mapa):
    from benner_rpa.core.lote import NumeroDivergente

    page = _pagina(navegador, "03-detalhamento-acoes.html")
    try:
        with pytest.raises(NumeroDivergente, match="G4"):
            busca.conferir_numero(page, mapa, "0000000-22.2023.5.15.0002")
    finally:
        page.close()


# ================================================================ G2

def test_g2_detecta_o_link_na_fixture_05(navegador, mapa):
    page = _pagina(navegador, "05-popup-selecionar-restantes.html")
    try:
        assert documentos.selecao_incompleta(page, mapa)
    finally:
        page.close()


def test_g2_TESTE_NEGATIVO_download_com_o_link_presente_FALHA(navegador, mapa):
    """O teste obrigatório do gate: precisa FALHAR, não avisar.

    Fixture com o link presente + tentativa de download. Se isto passar, o robô
    produziria um ZIP com 10 documentos de 93 e marcaria CONCLUIDO.
    """
    page = _pagina(navegador, "05-popup-selecionar-restantes.html")
    try:

        with pytest.raises(SelecaoIncompleta, match="G2"):
            documentos.baixar(page, page, mapa, Path("."), timeout_ms=1000)
    finally:
        page.close()


def test_g2_fixture_04_nao_oferece_o_link(navegador, mapa):
    """Página única: o checkbox basta, caminho legítimo."""
    page = _pagina(navegador, "04-popup-pagina-unica.html")
    try:
        assert not documentos.selecao_incompleta(page, mapa)
    finally:
        page.close()


def test_g2_a_guarda_deixa_passar_quando_o_link_nao_existe(navegador, mapa):
    """Prova que a guarda DISCRIMINA, em vez de bloquear tudo.

    Sem este teste, `baixar` poderia levantar SelecaoIncompleta sempre e o teste
    negativo passaria por acidente. Na fixture 04 não há link, então a execução
    tem que ir ALÉM da guarda — e aí falhar por não haver download de verdade,
    que é outro erro, com outra mensagem.
    """
    page = _pagina(navegador, "04-popup-pagina-unica.html")
    try:

        with pytest.raises(Exception) as excecao:
            documentos.baixar(page, page, mapa, Path("."), timeout_ms=1500)

        assert not isinstance(excecao.value, SelecaoIncompleta), (
            "a guarda do G2 bloqueou uma popup que NAO oferece o link — "
            "ela nao esta discriminando"
        )
    finally:
        page.close()


def test_g2_O_ERRO_QUE_CUSTOU_10_de_93(navegador, mapa):
    """O link é `<a>` SEM href — `role=link` acha ZERO.

    Em 29/08/2026 este seletor era `role=link` com o nome acessível. Achava nada,
    `selecao_incompleta()` devolvia False, e o robô baixou 10 documentos de 93
    marcando CONCLUIDO. É a falha silenciosa que o G2 inteiro existe para impedir,
    e ela passou porque o seletor procurava um papel que o elemento não tem.
    """
    page = _pagina(navegador, "05-popup-selecionar-restantes.html")
    try:
        # O que NÃO funciona — e a fixture prova que não funciona.
        assert page.get_by_role("link", name="Selecionar todos os restantes?").count() == 0

        link = documentos.link_restantes(page, mapa)
        assert link.count() == 1
        assert link.first.evaluate("e => e.tagName.toLowerCase()") == "a"
        assert link.first.get_attribute("href") is None
        assert "selectAll" in (link.first.get_attribute("onclick") or "")
    finally:
        page.close()


def test_g2_pagina_cheia_sem_banner_e_bloqueada(navegador, mapa):
    """A última brecha da igualdade vacuosa, fechada.

    Se o seletor do link quebrar de novo, o total cai para a contagem da página. Num
    processo com EXATAMENTE 10 documentos isso é indistinguível de "primeira página
    de várias", e a igualdade voltaria a comparar o mesmo erro consigo mesmo.

    A fixture 05 tem as linhas marcadas. Aqui o link e o banner são removidos e as
    linhas clonadas até 10 — reproduzindo justamente o estado em que o robô não tem
    como saber se viu tudo.
    """
    from benner_rpa.steps.documentos import TAMANHO_DA_PAGINA, resolver_selecao_total

    assert TAMANHO_DA_PAGINA == 10

    page = _pagina(navegador, "05-popup-selecionar-restantes.html")
    try:
        page.evaluate(
            """() => {
              document.querySelectorAll('div.alert, .multi-select-message')
                      .forEach(e => e.remove());
              const tb = document.querySelector('table.simple-grid tbody');
              while (tb.rows.length < 10) tb.appendChild(tb.rows[0].cloneNode(true));
            }"""
        )
        assert page.locator('input[id$="CheckBoxSelectedEntity"]').count() == 10
        assert not documentos.selecao_incompleta(page, mapa)      # link removido
        assert documentos.total_selecionado(page, mapa) == -1      # banner removido

        with pytest.raises(SelecaoIncompleta, match="tamanho da pagina"):
            resolver_selecao_total(page, page, mapa)
    finally:
        page.close()


def test_g2_pagina_incompleta_sem_banner_e_aceita(navegador, mapa):
    """Menos que o tamanho da página é prova de que não há continuação."""
    from benner_rpa.steps.documentos import resolver_selecao_total

    page = _pagina(navegador, "05-popup-selecionar-restantes.html")
    try:
        page.evaluate(
            "() => document.querySelectorAll('div.alert, .multi-select-message')"
            "        .forEach(e => e.remove())"
        )
        ev = resolver_selecao_total(page, page, mapa)

        assert ev["documentos_na_pagina"] == 6          # 6 < 10
        assert ev["total_veio_do_banner"] is False
        assert ev["total_selecionado"] == 6
    finally:
        page.close()


def test_g2_a_igualdade_do_gate_nao_pode_ser_vacua(mapa):
    """O segundo defeito, e o mais grave: o gate confirmou o pacote incompleto.

    `entradas_no_zip == docs_listados_popup` deu 10 == 10 e passou — porque os dois
    lados vinham da mesma leitura errada (a página 1). Um gate que compara um número
    errado consigo mesmo não é gate. O total tem de vir do banner.
    """
    banner = mapa.entrada("popup_documentos.banner_selecao")

    assert banner["valor"] == "div.multi-select-message"
    assert "total" in banner["nota"].lower()
    assert "vacu" in banner["porque_critico"].lower() or            "erram junto" in banner["porque_critico"].lower()


# ================================================================ G8

def test_g2_popup_real_e_um_iframe_nao_um_dialog(mapa):
    """A suposição mais cara do projeto, agora travada por teste.

    O robô esperou 15s por um `role=dialog` que nunca existiu: todo o conteúdo da
    popup vive dentro de `<iframe src="baixardocs.aspx">`.
    """
    frame = mapa.entrada("popup_documentos.frame")

    assert frame["estrategia"] == "frame"
    assert "baixardocs" in frame["valor"]

    botao = mapa.entrada("popup_documentos.botao_baixar")
    assert botao["valor"] == "a#top-CMD_BAIXARDOCUMENTOS"
    assert "role=button" in botao["proibido"], "e um <a>, nao um <button>"


def test_g2_link_ancorado_no_comando_de_servidor(mapa):
    """Como tudo neste sistema: o comando é a única âncora estável."""
    link = mapa.entrada("popup_documentos.link_selecionar_restantes")

    assert link["estrategia"] == "css"
    assert "selectAll" in link["valor"]
    assert "role=link" in link["proibido"]
    assert link["sem_fallback"] is True
    assert "_falha_real" in link, "a falha de 10 de 93 tem que ficar registrada"


def test_g8_os_dois_banners_sao_distinguidos_por_conteudo(navegador, mapa):
    """Mesma faixa de alerta, conteúdos diferentes — nunca por posição."""
    p04 = _pagina(navegador, "04-popup-pagina-unica.html")
    p05 = _pagina(navegador, "05-popup-selecionar-restantes.html")
    try:
        # A popup real NÃO usa role="alert" — as fixtures espelham isso. A faixa é
        # identificada pela classe, e os dois banners se distinguem pelo CONTEÚDO.
        t04 = p04.locator("div.alert").first.inner_text()
        t05 = p05.locator("div.alert").first.inner_text()

        assert "Download de documentos em lote executado" in t04
        assert "Selecionar todos os restantes?" not in t04

        assert "selecionados" in t05
        assert "Selecionar todos os restantes?" in t05
    finally:
        p04.close()
        p05.close()


def test_g8_banner_de_sucesso_existe_antes_de_qualquer_clique(navegador):
    """Prova do §7.3: o banner da fixture 04 é sobra de execução anterior."""
    page = _pagina(navegador, "04-popup-pagina-unica.html")
    try:
        assert "Download de documentos em lote executado" in             page.locator("div.alert").first.inner_text()
    finally:
        page.close()


# ================================================================ G12

def test_g12_entradas_todo_levantam_em_vez_de_inventar(mapa):
    """A paginação da popup continua TODO: o screenshot 05 corta a base do modal."""
    with pytest.raises(SeletorNaoDeterminado, match="G12"):
        mapa.entrada("popup_documentos.paginacao")


def test_g12_a_lupa_nao_e_mais_um_seletor_inventado(mapa):
    """Regressão do pior tipo de erro que este gate existe para impedir.

    Até 28/08/2026 esta entrada era `role=button` com nome "Pesquisa (ctrl + espaço)",
    lido do TOOLTIP do screenshot 01. Esse texto não existe no DOM: o elemento é um
    `<i class="fa fa-search">` sem title, sem aria-label e sem role. O fallback nunca
    poderia ter funcionado — e só não apareceu antes porque o atalho vinha dando certo.
    """
    lupa = mapa.entrada("busca.icone_lupa")

    # Os campos OPERATIVOS não podem mais carregar o nome inventado. A nota
    # `_correcao` cita o texto antigo de propósito — é o registro do erro.
    assert lupa["estrategia"] == "css"
    assert lupa["valor"] == "i.fa.fa-search"
    assert "nome" not in lupa, "nome acessivel inventado; este elemento nao tem nenhum"
    assert "_correcao" in lupa, "a correcao tem que ficar registrada no mapa"


def test_g12_todos_os_todos_sao_reportaveis(mapa):
    todos = mapa.todos_os_todos()

    assert "popup_documentos.paginacao" in todos
    # A tela de login saiu de TODO em 28/08/2026, lendo o DOM real.
    assert not any(t.startswith("login.") for t in todos)


def test_g12_login_veio_do_dom_real_e_nao_de_convencao(mapa):
    """As três suposições convencionais estavam erradas — o mapa registra isso."""
    entrar = mapa.entrada("login.botao_entrar")

    assert entrar["estrategia"] == "role=link"      # e nao role=button
    assert entrar["nome"] == "Acessar"              # e nao "Entrar"
    assert "role=button" in entrar["proibido"]

    # Os campos nao tem <label>; o nome acessivel vem do placeholder.
    assert mapa.entrada("login.campo_usuario")["estrategia"] == "placeholder"
