"""Peça 11 — exportação de Pedidos.

O passo que mais custou a entender, e o motivo é instrutivo: **o clique em
"Exportar para Excel" não baixa nada**. Ele dispara um postback que gera o arquivo no
servidor e mostra uma notificação (toastr) no canto inferior direito:

    ✓ Pedidos.xlsx
      Pedidos.xlsx exportação para excel

O download só acontece ao clicar nessa notificação. Esperar `expect_download` logo
após o clique no item de menu espera para sempre.

O segundo tropeço foi de ordem: o plano mandava clicar `Ver todos` antes de exportar
(§3.5), mas `Ver todos` abre um MODAL em tela cheia que **cobre exatamente o menu
`⋮` que se ia usar**. Exportar primeiro e contar depois resolve os dois.
"""

from __future__ import annotations

from pathlib import Path

from .seletores import MapaSeletores, acionar, exigir_texto_exato


def _primeiro_visivel(locator):
    for i in range(locator.count()):
        alvo = locator.nth(i)
        if alvo.is_visible():
            return alvo
    return None


def _abrir_menu(page, mapa: MapaSeletores):
    """Abre o `⋮` da grade e devolve o item de exportar, já visível.

    Verifica o EFEITO em vez de assumir que o clique abriu o menu — a falha de um
    menu que não abriu aparece um passo depois, disfarçada de seletor errado.
    """
    item = mapa.localizar(page, "pedidos.exportar_excel").first

    for _ in range(3):
        if item.count() and item.is_visible():
            return item

        gatilho = _primeiro_visivel(mapa.localizar(page, "pedidos.menu_tabela"))
        if gatilho is None:
            raise RuntimeError("menu da tabela de PEDIDOS nao encontrado ou invisivel")
        acionar(gatilho)
        page.wait_for_timeout(1500)

    raise RuntimeError(
        "o menu da tabela de PEDIDOS nao abriu apos 3 tentativas — "
        "'Exportar para Excel' nunca ficou visivel"
    )


def _baixar_pelo_toast(page, mapa: MapaSeletores, destino: Path, *, timeout_ms: int) -> Path:
    """Espera a notificação de exportação e clica nela para obter o arquivo."""
    toast = mapa.localizar(page, "pedidos.toast_exportacao").first
    toast.wait_for(state="visible", timeout=timeout_ms)

    with page.expect_download(timeout=timeout_ms) as dl:
        acionar(toast)

    download = dl.value
    alvo = Path(destino) / download.suggested_filename
    download.save_as(str(alvo))
    return alvo


def contar_todos_os_pedidos(page, mapa: MapaSeletores) -> int:
    """Total real de pedidos, lido do modal `Ver todos`.

    Serve só para conferência: comparado com as linhas do XLSX, responde se o export
    cobre tudo ou apenas a página visível (§3.5). É feito DEPOIS do export porque o
    modal cobre o menu.

    Devolve -1 para desconhecido — nunca 0, que afirmaria "não há pedidos".
    """
    try:
        botao = _primeiro_visivel(mapa.localizar(page, "pedidos.ver_todos"))
        if botao is None:
            return -1

        acionar(botao)
        page.wait_for_load_state("networkidle")

        seletor = mapa.entrada("pedidos.frame_ver_todos")["valor"]
        page.wait_for_selector(seletor, state="attached", timeout=15000)
        frame = page.frame_locator(seletor)

        tabela = mapa.localizar(frame, "pedidos.tabela_ver_todos").first
        tabela.wait_for(state="visible", timeout=15000)
        return tabela.locator("tbody tr").count()
    except Exception:
        return -1


def exportar(page, mapa: MapaSeletores, destino: Path, *, timeout_ms: int) -> dict:
    linhas_na_pagina = -1
    try:
        linhas_na_pagina = mapa.localizar(page, "pedidos.tabela").first.locator(
            "tbody tr").count()
    except Exception:
        pass

    e = mapa.entrada("pedidos.exportar_excel")
    item = _abrir_menu(page, mapa)

    # Dois sinais, como no menu Ações: o comando no href e o texto visível. O mesmo
    # menu oferece "Colunas", "Consulta dinâmica" e "Edição em lote".
    exigir_texto_exato(item, e["nome"], "pedidos.exportar_excel")
    acionar(item)

    caminho = _baixar_pelo_toast(page, mapa, destino, timeout_ms=timeout_ms)

    # Conferência da §3.5, agora que o menu já foi usado e o modal pode abrir.
    total = contar_todos_os_pedidos(page, mapa)

    return {
        "caminho": caminho,
        "via_ver_todos": False,
        "linhas_na_pagina": linhas_na_pagina,
        "linhas_na_tela": total,
        "aviso": "",
    }
