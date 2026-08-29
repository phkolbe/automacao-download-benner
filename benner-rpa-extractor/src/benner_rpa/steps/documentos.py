"""Peças 9 e 10 — seleção total e download do pacote.

O coração do G2. A regra que governa este arquivo inteiro:

    Enquanto o banner oferecer "Selecionar todos os restantes?", a seleção está
    incompleta e é PROIBIDO baixar.

O critério de prosseguir é a AUSÊNCIA do link — não a presença de um texto de
confirmação, cujo texto exato é desconhecido. Assim a regra não quebra quando o
Benner disser algo diferente do que esperamos.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..core.lote import SelecaoIncompleta
from .seletores import MapaSeletores, SeletorProibido, acionar, exigir_texto_exato


def abrir_menu_acoes(page, mapa: MapaSeletores) -> None:
    """Aciona o gatilho `Ações` que estiver VISÍVEL.

    O Benner repete o id `top-CMD_ACOES` entre a versão da barra de comandos e uma
    aninhada — HTML inválido, mas real. Qual das duas está visível depende da largura
    da janela, porque o Metronic colapsa a barra. Escolher pela posição no DOM
    (`.first`) acerta numa largura e dá timeout invisível na outra.

    Aqui a escolha é por VISIBILIDADE, que é o que de fato importa para clicar, e
    não é posição: qualquer uma das variantes serve, desde que dê para acioná-la.
    """
    candidatos = mapa.localizar(page, "detalhamento.botao_acoes")

    total = candidatos.count()
    for i in range(total):
        alvo = candidatos.nth(i)
        if alvo.is_visible():
            acionar(alvo)
            return

    raise SeletorProibido(
        f"nenhum gatilho 'Acoes' visivel ({total} no DOM). A barra de comandos pode "
        "ter colapsado — conferir a largura do viewport."
    )


def clicar_baixar_documentos(page, mapa: MapaSeletores):
    """G1 — dois sinais independentes têm que concordar antes do clique.

    Cada item do menu é `<a id="top-<COMANDO>" href="javascript:__doPostBack(…)">`.
    Isso dá duas âncoras que erram de formas diferentes:

      1. o id do comando de servidor — `BTBAIXARLOTE`
      2. o texto visível — `Baixar documentos`

    Se as duas concordam, é o item certo. O vizinho perigoso é `BTINSERIRLOTE`
    ("Inserir documentos em lote"), que difere por poucos caracteres e fica
    imediatamente acima — por isso o id casa por igualdade, nunca por substring.
    """
    e = mapa.entrada("menu_acoes.baixar_documentos")
    item = mapa.localizar(page, "menu_acoes.baixar_documentos").first
    item.wait_for(state="visible", timeout=10000)

    # Sinal 1: o id do comando.
    id_visto = item.get_attribute("id") or ""
    # removeprefix, não lstrip: `lstrip("a#")` come QUALQUER 'a' ou '#' inicial e
    # mutilaria um id que comece com 'a'.
    id_esperado = e["valor"].removeprefix("a#")
    if id_visto != id_esperado:
        raise SeletorProibido(
            f"G1: id do comando e {id_visto!r}, esperado {id_esperado!r}. Nada acionado."
        )

    # Sinal 2: o texto visível.
    exigir_texto_exato(item, e["nome"], "menu_acoes.baixar_documentos")

    acionar(item)


def abrir_popup(page, mapa: MapaSeletores):
    """Devolve o FrameLocator da popup — que é um iframe, não um dialog.

    Esta foi a suposição mais cara do projeto: o robô esperou 15s por um
    `role=dialog` que nunca existiu, porque todo o conteúdo da popup vive dentro de
    `<iframe src="baixardocs.aspx">`.
    """
    seletor = mapa.entrada("popup_documentos.frame")["valor"]
    page.wait_for_selector(seletor, state="attached", timeout=20000)

    frame = page.frame_locator(seletor)
    # Espera o conteúdo do frame carregar, não só o elemento existir.
    frame.locator(mapa.entrada("popup_documentos.tabela")["valor"]).first.wait_for(
        state="visible", timeout=20000)
    return frame


# Medido no Benner: a popup lista 10 documentos por pagina.
TAMANHO_DA_PAGINA = 10

_TOTAL_SELECIONADO = re.compile(r"(\d+)\s+itens?\s+selecionad", re.IGNORECASE)
_TOTAL_DA_PAGINA = re.compile(r"Os\s+(\d+)\s+itens?\s+desta", re.IGNORECASE)


def total_selecionado(frame, mapa: MapaSeletores) -> int:
    """Quantos documentos estão de fato selecionados, lido do banner.

    Este número é a razão de ser do G2. A tela continua mostrando 10 linhas depois de
    selecionar tudo — a paginação não muda, só a seleção. Contar linhas dá 10 quando
    o correto é 93, e aí a igualdade `entradas_no_zip == docs_listados_popup` compara
    dois números errados do mesmo jeito e CONFIRMA um pacote incompleto.

    Devolve -1 quando não há banner (caso de página única, em que a contagem de
    linhas é legítima) — nunca 0, que afirmaria "nenhum documento".
    """
    banner = mapa.localizar(frame, "popup_documentos.banner_selecao")
    if banner.count() == 0:
        return -1

    texto = " ".join(
        (banner.nth(i).inner_text() or "") for i in range(banner.count())
    ).strip()

    m = _TOTAL_SELECIONADO.search(texto)
    if m:
        return int(m.group(1))

    m = _TOTAL_DA_PAGINA.search(texto)
    if m:
        # "Os N itens desta página estão selecionados" — é o total da PÁGINA, e só
        # vale como total se não houver link oferecendo o restante.
        return int(m.group(1)) if not selecao_incompleta(frame, mapa) else -1

    return -1


def link_restantes(frame, mapa: MapaSeletores):
    return mapa.localizar(frame, "popup_documentos.link_selecionar_restantes")


def selecao_incompleta(frame, mapa: MapaSeletores) -> bool:
    """G2 — o único predicado que autoriza o download.

    True enquanto o link estiver sendo oferecido. A detecção é pela PRESENÇA DO LINK
    e não pelo banner — o que se mostrou providencial: a popup não usa `role=alert`,
    então uma regra baseada no banner teria quebrado aqui.
    """
    link = link_restantes(frame, mapa)
    return link.count() > 0 and link.first.is_visible()


def resolver_selecao_total(page, frame, mapa: MapaSeletores) -> dict:
    """A sequência do §3.7: marcar a página, resolver o restante, confirmar."""
    evidencia = {
        "link_restantes_presente": False,
        "link_restantes_acionado": False,
        "link_ausente_ao_baixar": False,
        "documentos_na_pagina": 0,
    }

    checkbox = mapa.localizar(frame, "popup_documentos.checkbox_cabecalho").first
    checkbox.wait_for(state="visible", timeout=15000)

    linhas = mapa.localizar(frame, "popup_documentos.checkbox_linha")
    total = linhas.count()
    evidencia["documentos_na_pagina"] = total

    def marcadas() -> int:
        return sum(1 for i in range(linhas.count()) if linhas.nth(i).is_checked())

    # `.check()` não serve aqui. O checkbox do cabeçalho carrega
    # `onclick="Benner.Grid.selectAllRows(...)"`, que re-renderiza a grade; o Playwright
    # clica, relê o `checked` do próprio cabeçalho, vê que não mudou e desiste com
    # "clicking the checkbox did not change its state".
    #
    # O estado do cabeçalho nunca foi o que importa. O que importa é AS LINHAS estarem
    # marcadas — então é isso que se verifica.
    # `<th class="multi-select-column">` cobre o input e intercepta o ponteiro.
    # `acionar` cai para o onclick do próprio elemento nesse caso.
    for _ in range(3):
        if total and marcadas() == total:
            break
        acionar(checkbox)
        page.wait_for_timeout(1500)     # a grade re-renderiza e o banner aparece

    marcadas_agora = marcadas()
    evidencia["marcadas_na_pagina"] = marcadas_agora

    if total and marcadas_agora != total:
        raise SelecaoIncompleta(
            f"G2: apos marcar o cabecalho, {marcadas_agora} de {total} linhas da pagina "
            "estao selecionadas. Download BLOQUEADO."
        )

    if selecao_incompleta(frame, mapa):
        evidencia["link_restantes_presente"] = True

        alvo = link_restantes(frame, mapa).first
        exigir_texto_exato(
            alvo,
            mapa.entrada("popup_documentos.link_selecionar_restantes")["nome"],
            "popup_documentos.link_selecionar_restantes",
        )
        acionar(alvo)
        evidencia["link_restantes_acionado"] = True

        # Espera o link sumir. Esperar por um texto de confirmação seria apostar
        # num texto que não conhecemos.
        for _ in range(30):
            page.wait_for_timeout(500)
            if not selecao_incompleta(frame, mapa):
                break

    if selecao_incompleta(frame, mapa):
        raise SelecaoIncompleta(
            "G2: o link 'Selecionar todos os restantes?' continua sendo oferecido "
            "depois de acionado. Download BLOQUEADO — o pacote sairia incompleto."
        )

    evidencia["link_ausente_ao_baixar"] = True

    total = total_selecionado(frame, mapa)
    na_pagina = evidencia["documentos_na_pagina"]
    evidencia["total_selecionado"] = total if total >= 0 else na_pagina
    evidencia["total_veio_do_banner"] = total >= 0

    if evidencia["link_restantes_presente"] and total < 0:
        raise SelecaoIncompleta(
            "G2: o link foi acionado mas o banner nao informou o total selecionado. "
            "Sem o total, a conferencia entradas_no_zip == docs_listados nao tem valor. "
            "Download BLOQUEADO."
        )

    # Resíduo do mesmo defeito, e o único ponto onde o gate ainda pode mentir.
    #
    # Se o seletor do link quebrar de novo, `selecao_incompleta` devolve False, o total
    # cai para a contagem da página, o ZIP vem com esse tanto, e a igualdade
    # `entradas_no_zip == docs_listados` passa comparando o mesmo erro consigo mesmo —
    # exatamente o que produziu 10 de 93 em 29/08/2026.
    #
    # A página tem 10 itens. Um processo que tenha EXATAMENTE 10 documentos é
    # indistinguível de um que tenha 10 na primeira página e mais adiante. Nesse caso
    # o total precisa vir do banner; sem ele, não há como afirmar que o pacote está
    # completo, e afirmar assim mesmo é o que o G2 proíbe.
    if not evidencia["total_veio_do_banner"] and na_pagina >= TAMANHO_DA_PAGINA:
        raise SelecaoIncompleta(
            f"G2: {na_pagina} documentos na pagina (o tamanho da pagina e "
            f"{TAMANHO_DA_PAGINA}) e nenhum banner informando o total. Impossivel "
            "distinguir 'este processo tem exatamente esse tanto' de 'esta e a "
            "primeira pagina de varias'. Download BLOQUEADO."
        )

    return evidencia


def listar_documentos(frame, mapa: MapaSeletores) -> list[dict]:
    """As linhas da popup, para o manifest e para a conferência com o ZIP."""
    tabela = mapa.localizar(frame, "popup_documentos.tabela").first
    linhas = tabela.locator("tbody tr")

    docs: list[dict] = []
    for i in range(linhas.count()):
        celulas = linhas.nth(i).locator("td")
        if celulas.count() < 4:
            continue
        t = [(celulas.nth(j).inner_text() or "").strip() for j in range(celulas.count())]
        docs.append({"nome": t[1], "tipo": t[2], "data": t[3]})   # t[0] é o checkbox

    return docs


def baixar(page, frame, mapa: MapaSeletores, destino: Path, *, timeout_ms: int) -> Path:
    """G2 + G8 — só baixa com o link ausente, e o sucesso é o evento de download."""
    if selecao_incompleta(frame, mapa):
        raise SelecaoIncompleta(
            "G2: tentativa de baixar com o link 'Selecionar todos os restantes?' presente"
        )

    e = mapa.entrada("popup_documentos.botao_baixar")
    botao = mapa.localizar(frame, "popup_documentos.botao_baixar").first
    botao.wait_for(state="visible", timeout=15000)

    # Mesmo nome visível do item de menu que abriu a popup — a conferência garante
    # que estamos no elemento de dentro do frame, não no que reabriria o menu.
    exigir_texto_exato(botao, e["nome"], "popup_documentos.botao_baixar")

    # G8 — o sinal é o evento de download, nunca o banner.
    with page.expect_download(timeout=timeout_ms) as dl:
        acionar(botao)

    download = dl.value
    alvo = Path(destino) / download.suggested_filename
    download.save_as(str(alvo))
    return alvo


def extrair_documentos(page, mapa: MapaSeletores, destino: Path, *, timeout_ms: int) -> dict:
    """Do menu Ações até o ZIP no disco."""
    abrir_menu_acoes(page, mapa)
    clicar_baixar_documentos(page, mapa)
    frame = abrir_popup(page, mapa)

    selecao = resolver_selecao_total(page, frame, mapa)
    documentos = listar_documentos(frame, mapa)

    caminho = baixar(page, frame, mapa, destino, timeout_ms=timeout_ms) if documentos else None

    # O total vem da SELEÇÃO, não das linhas visíveis. `documentos` continua sendo a
    # listagem da página corrente — serve de amostra no manifest, não de contagem.
    return {
        "selecao": selecao,
        "documentos": documentos,
        "docs_listados_popup": selecao["total_selecionado"],
        "documentos_na_pagina": len(documentos),
        "caminho_zip": caminho,
    }
