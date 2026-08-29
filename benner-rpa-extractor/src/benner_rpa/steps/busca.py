"""Peça 8 — busca e identificação do resultado correto (§4).

A árvore de decisão inteira vive aqui, e o ponto delicado é um só: a busca devolve
TRÊS grupos contendo a palavra PASTAS. O alvo é o de título exatamente `PASTAS`;
um match parcial abre `CAUSA RAIZ (PASTAS)` e baixa os documentos de outro processo
em silêncio.
"""

from __future__ import annotations

from ..core.lote import NumeroDivergente, ProcessoAmbiguo, ProcessoNaoEncontrado
from ..core.normalizacao import mesma_identidade, normalizar_processo
from .seletores import MapaSeletores, acionar


def _campo_visivel(page, mapa: MapaSeletores, timeout_ms: int) -> bool:
    """O input já existe no DOM antes do atalho, com 0x0 — esperar por PRESENÇA
    devolveria imediatamente e a digitação iria para o nada."""
    try:
        mapa.localizar(page, "busca.campo").first.wait_for(
            state="visible", timeout=timeout_ms)
        return True
    except Exception:
        return False


def abrir_busca(page, mapa: MapaSeletores) -> None:
    """Ctrl+Espaço, com retentativa; clique na lupa é o plano B (§3.1)."""
    como = mapa.entrada("busca._como_abrir")
    atalho = mapa.entrada("busca.atalho")["valor"]

    for _ in range(como["tentativas_atalho"]):
        page.keyboard.press(atalho)
        if _campo_visivel(page, mapa, como["espera_por_tentativa_ms"]):
            return

    # Plano B: a lupa. Vários `i.fa-search` existem no DOM — a maioria dentro do
    # próprio modal, invisíveis. Só o visível serve.
    icones = mapa.localizar(page, "busca.icone_lupa")
    for i in range(icones.count()):
        alvo = icones.nth(i)
        if alvo.is_visible():
            acionar(alvo)
            if _campo_visivel(page, mapa, como["espera_por_tentativa_ms"]):
                return
            break

    raise LeituraDaTelaFalhou(
        f"o painel de busca nao abriu apos {como['tentativas_atalho']} tentativas de "
        f"{atalho} nem pelo clique na lupa"
    )


def digitar_numero(page, mapa: MapaSeletores, numero: str) -> None:
    """Teclas REAIS, número COM máscara.

    Duas coisas medidas contra o Benner real em 28/08/2026, e as duas contra-intuitivas:

    - `fill()` seta o valor por JS e não dispara nada. O campo fica preenchido, a lista
      vazia, e o robô conclui `NAO_ENCONTRADO` para um processo que existe. Falso
      negativo silencioso — e `NAO_ENCONTRADO` é terminal, então o processo seria
      pulado para sempre.
    - O Benner não normaliza: digitar os 20 dígitos sem máscara devolve
      "nada encontrado". O número vai como está na planilha.
    """
    como = mapa.entrada("busca._como_digitar")
    campo = mapa.localizar(page, "busca.campo").first
    grupos = mapa.localizar(page, "resultado_busca.cabecalho_de_grupo")

    # A busca é assíncrona e às vezes não responde na primeira. Redigitar é barato;
    # desistir custa um processo classificado como inexistente — e esse estado é
    # terminal.
    for tentativa in range(3):
        # Nada de `.click()` aqui. O painel é um modal Bootstrap com animação de
        # entrada, e durante ela o `.modal-header` fica por cima do campo: o clique é
        # interceptado e só dá timeout depois de 30s. `focus()` não faz teste de
        # sobreposição — e foco é tudo de que `press_sequentially` precisa.
        campo.focus()
        campo.fill("")
        campo.press_sequentially(numero, delay=como["delay_ms"])
        page.wait_for_timeout(como["espera_apos_ms"])

        if grupos.count() > 0:
            return

    # Sai sem grupo nenhum; quem decide o que isso significa é `_cabecalho_pastas`.


def _cabecalho_pastas(page, mapa: MapaSeletores):
    """O `<li>` de texto exatamente `PASTAS`. G3.

    Distingue duas situações que parecem iguais e têm consequências opostas:

    - a busca respondeu, veio com grupos, e nenhum é `PASTAS` → o processo realmente
      não está no Benner. `NAO_ENCONTRADO`, terminal.
    - a busca não respondeu nada, nenhum grupo sequer → falha TÉCNICA. `ERRO`, que
      retenta.

    Sem essa distinção, uma instabilidade momentânea da busca apaga o processo do
    lote para sempre. Aconteceu duas vezes em 29/08/2026 com o `0012033`, que
    comprovadamente existe.
    """
    cab = mapa.localizar(page, "resultado_busca.grupo_pastas")

    if cab.count() > 1:
        raise ProcessoAmbiguo(
            f"{cab.count()} cabecalhos com titulo exatamente 'PASTAS' — impossivel decidir"
        )

    if cab.count() == 1:
        return cab.first

    # Nenhum grupo `PASTAS`. Antes de condenar o processo, exigir prova de que a
    # busca de fato respondeu.
    quaisquer = mapa.localizar(page, "resultado_busca.cabecalho_de_grupo")
    if quaisquer.count() == 0:
        raise LeituraDaTelaFalhou(
            "a busca nao devolveu grupo nenhum — painel vazio ou consulta nao "
            "completou. Isto e falha tecnica, nao ausencia do processo."
        )

    titulos = [quaisquer.nth(i).inner_text().strip() for i in range(quaisquer.count())]
    raise ProcessoNaoEncontrado(
        f"a busca devolveu {len(titulos)} grupos ({', '.join(titulos)}) e nenhum e "
        "exatamente 'PASTAS'"
    )


def grupo_pastas(page, mapa: MapaSeletores):
    """Compatibilidade: devolve o cabeçalho do grupo `PASTAS`.

    O resultado do Benner é uma LISTA PLANA — cabeçalhos e itens são irmãos dentro
    de um único `div.list-group`. Não existe container por grupo, então não há
    "seção" para devolver.
    """
    return _cabecalho_pastas(page, mapa)


def itens_do_grupo_pastas(page, mapa: MapaSeletores) -> list:
    """Os irmãos entre o cabeçalho `PASTAS` e o cabeçalho seguinte.

    É esta travessia que implementa o escopo do G3 numa lista plana: pegar os itens
    de qualquer outro jeito misturaria os três grupos.
    """
    cabecalho = _cabecalho_pastas(page, mapa)
    marca_item = mapa.entrada("resultado_busca.itens_do_grupo")["valor"]
    marca_cab = mapa.entrada("resultado_busca.cabecalho_de_grupo")["valor"]

    # `following-sibling::*` na ordem do documento; paramos no próximo cabeçalho.
    irmaos = cabecalho.locator("xpath=following-sibling::*")
    classe_item = marca_item.split(".", 1)[1]
    classe_cab = marca_cab.split(".", 1)[1]

    itens = []
    for i in range(irmaos.count()):
        irmao = irmaos.nth(i)
        classes = (irmao.get_attribute("class") or "")
        if classe_cab in classes:
            break                       # começou o próximo grupo
        if classe_item in classes:
            itens.append(irmao)

    return itens


def item_do_processo(page_ou_secao, mapa: MapaSeletores, numero: str):
    """O único item do grupo PASTAS que casa com o número normalizado.

    O texto vem do `span.searcher-caption`, não do `<a>` inteiro: o `<a>` também
    contém o botão "Partes e testemunhas", que é o único elemento com `href` ali
    dentro e abriria um modal se fosse clicado.
    """
    page = getattr(page_ou_secao, "page", page_ou_secao)
    alvo = normalizar_processo(numero)
    seletor_texto = mapa.entrada("resultado_busca.texto_do_item")["valor"]

    casam = []
    for item in itens_do_grupo_pastas(page, mapa):
        legenda = item.locator(seletor_texto)
        texto = (legenda.first.inner_text() if legenda.count() else item.inner_text() or "").strip()
        if alvo and alvo in normalizar_processo(texto):
            casam.append((texto, item))

    if not casam:
        raise ProcessoNaoEncontrado(
            f"nenhum item do grupo PASTAS contem o numero {numero}"
        )

    if len(casam) > 1:
        textos = " | ".join(t for t, _ in casam)
        raise ProcessoAmbiguo(
            f"{len(casam)} itens no grupo PASTAS casam com {numero}: {textos}"
        )

    return casam[0][1]


class LeituraDaTelaFalhou(RuntimeError):
    """Falha TÉCNICA ao ler um campo — nunca 'o processo não existe'.

    A distinção não é cosmética. `ProcessoNaoEncontrado` é terminal: o processo sai
    do lote e nunca mais é tentado. Usar esse estado para "não consegui ler o DOM"
    transforma um defeito do robô em veredito permanente sobre o dado — foi o que
    aconteceu em 28/08/2026, duas vezes seguidas.

    `ProcessoNaoEncontrado` significa uma coisa só: não há item correspondente no
    grupo PASTAS. Todo o resto é ERRO, que retenta.
    """


def _valor_do_campo(page, mapa: MapaSeletores, caminho: str) -> str:
    """Lê o valor de um campo do detalhamento pelo seu `data-field`.

    O layout não relaciona rótulo e valor por vizinhança: o rótulo visível fica num
    `<label>` e o valor num `<span data-field>` irmão daquele label, ambos dentro de
    `div.row.static-info`. Tentar chegar ao valor a partir do texto do rótulo foi o
    que falhou na execução real — e `data-field` é melhor de qualquer forma, porque é
    o identificador interno do campo e não muda com idioma nem com layout.
    """
    alvo = mapa.localizar(page, caminho)

    if alvo.count() == 0:
        e = mapa.entrada(caminho)
        raise LeituraDaTelaFalhou(
            f"campo {caminho} ({e['valor']}) nao existe na tela — layout mudou?"
        )

    return (alvo.first.inner_text() or "").strip()


def conferir_numero(page, mapa: MapaSeletores, esperado: str) -> str:
    """G4 — o número na tela contra o da planilha. Divergência é ERRO, sem download."""
    na_tela = _valor_do_campo(page, mapa, "detalhamento.numero_do_processo")

    if not mesma_identidade(na_tela, esperado):
        raise NumeroDivergente(
            f"G4: numero na tela {na_tela!r} != planilha {esperado!r}. Download abortado."
        )
    return na_tela


def ler_identificador_da_pasta(page, mapa: MapaSeletores) -> str:
    """`TRAB.000003` — cruza com o nome do ZIP entregue pelo servidor (§1.3)."""
    try:
        return _valor_do_campo(page, mapa, "detalhamento.identificador_da_pasta")
    except Exception:
        return ""       # conferência cruzada é bônus, não requisito


def buscar_e_abrir(page, mapa: MapaSeletores, numero: str) -> dict:
    """A árvore da §4 inteira. Devolve o que foi conferido na tela."""
    abrir_busca(page, mapa)
    digitar_numero(page, mapa, numero)

    acionar(item_do_processo(page, mapa, numero))
    page.wait_for_load_state("networkidle")

    return {
        "numero_na_tela": conferir_numero(page, mapa, numero),
        "pasta_benner": ler_identificador_da_pasta(page, mapa),
    }
