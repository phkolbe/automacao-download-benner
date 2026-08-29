"""`relatorio_lote.md` — o que aconteceu no lote, em texto que uma pessoa lê.

Regra de composição: o que exige ação humana vem primeiro. `AMBIGUO` e
`NAO_ENCONTRADO` nunca serão resolvidos pelo robô, então são a primeira coisa na
página; contagens agregadas vêm depois.
"""

from __future__ import annotations

from pathlib import Path

from .disco import humanizar
from .estados import Estado
from .lote import ResultadoProcesso
from .manifest import agora_iso
from .segredos import limpar

ORDEM = [
    Estado.CONCLUIDO, Estado.PARCIAL, Estado.ERRO,
    Estado.AMBIGUO, Estado.NAO_ENCONTRADO, Estado.BLOQUEADO, Estado.PENDENTE,
]

# Estados que ninguém além de uma pessoa resolve.
EXIGEM_PESSOA = (Estado.AMBIGUO, Estado.NAO_ENCONTRADO, Estado.BLOQUEADO)


def _tabela(cabecalho: list[str], linhas: list[list[str]]) -> list[str]:
    if not linhas:
        return []
    out = ["| " + " | ".join(cabecalho) + " |",
           "| " + " | ".join(":--" for _ in cabecalho) + " |"]
    out += ["| " + " | ".join(str(c) for c in linha) + " |" for linha in linhas]
    return out + [""]


def compor(
    resultados: list[ResultadoProcesso],
    *,
    total_na_planilha: int,
    raiz_saida: Path,
    pendencias: list[str] | None = None,
) -> str:
    por_estado: dict[Estado, list[ResultadoProcesso]] = {}
    for r in resultados:
        por_estado.setdefault(r.status, []).append(r)

    concluidos = por_estado.get(Estado.CONCLUIDO, [])
    bytes_baixados = sum(
        int(r.detalhe.get("bytes_zip", 0)) for r in concluidos
    )

    L: list[str] = [
        "# Relatório do lote",
        "",
        f"Gerado em {agora_iso()}  ·  saída em `{raiz_saida}`",
        "",
    ]

    # ---- o que exige uma pessoa, primeiro ----
    precisa = [r for r in resultados if r.status in EXIGEM_PESSOA]
    if precisa:
        L += ["## Exige decisão humana", "",
              "Estes o robô não resolve — por desenho, não por falta de tentativa.", ""]
        L += _tabela(
            ["Processo", "Estado", "Motivo"],
            [[r.processo.numero, r.status.value, limpar(r.observacao) or "—"] for r in precisa],
        )

    # ---- resumo ----
    L += ["## Resumo", ""]
    L += _tabela(
        ["Estado", "Processos"],
        [[e.value, len(por_estado[e])] for e in ORDEM if e in por_estado],
    )
    L += [
        f"- Processados nesta execução: **{len(resultados)}** de {total_na_planilha} na planilha",
        f"- Volume baixado: **{humanizar(bytes_baixados)}**" if bytes_baixados else
        "- Volume baixado: não medido nesta execução",
        "",
    ]

    if concluidos:
        medias = [int(r.detalhe.get("bytes_zip", 0)) for r in concluidos if r.detalhe.get("bytes_zip")]
        if medias:
            media = sum(medias) // len(medias)
            restantes = total_na_planilha - len(concluidos)
            L += [
                f"- Média medida por processo: **{humanizar(media)}** "
                f"(amostra de {len(medias)})",
                f"- Projeção para os {restantes} restantes: "
                f"**{humanizar(media * restantes)}**",
                "",
                "> A projeção substitui a estimativa de 44 GB, que vinha de uma amostra "
                "de um único processo.",
                "",
            ]

    # ---- seleção completa: a evidência do G2 ----
    com_link = [r for r in concluidos
                if r.detalhe.get("selecao", {}).get("link_restantes_acionado")]
    if concluidos:
        L += ["## Seleção completa (G2)", "",
              f"- Processos em que o link `Selecionar todos os restantes?` **apareceu e foi "
              f"acionado**: **{len(com_link)}** de {len(concluidos)}",
              f"- Processos que couberam numa página só: {len(concluidos) - len(com_link)}",
              "",
              "Em todos os concluídos, `entradas_no_zip == docs_listados_popup`. "
              "Um pacote que não bate não vira `CONCLUIDO` — vira `ERRO`.",
              ""]

    # ---- falhas retentáveis ----
    falhas = por_estado.get(Estado.ERRO, []) + por_estado.get(Estado.PARCIAL, [])
    if falhas:
        L += ["## Falhas retentáveis", "",
              "Uma nova execução retenta estas automaticamente.", ""]
        L += _tabela(
            ["Processo", "Estado", "Tentativas", "Observação"],
            [[r.processo.numero, r.status.value, r.tentativas, limpar(r.observacao) or "—"]
             for r in falhas],
        )

    # ---- concluídos ----
    if concluidos:
        L += ["## Concluídos", ""]
        L += _tabela(
            ["Processo", "Pasta Benner", "Docs na popup", "Entradas no ZIP", "Pedidos"],
            [[r.processo.numero,
              r.detalhe.get("pasta_benner", "—"),
              r.detalhe.get("docs_listados_popup", "—"),
              r.detalhe.get("docs_no_zip", "—"),
              r.detalhe.get("pedidos_exportados", "—")] for r in concluidos],
        )

    if pendencias:
        L += ["## Pendências registradas", ""]
        L += [f"- {p}" for p in pendencias] + [""]

    return "\n".join(L)


def gravar(conteudo: str, destino: Path) -> Path:
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(limpar(conteudo), encoding="utf-8")
    return destino
