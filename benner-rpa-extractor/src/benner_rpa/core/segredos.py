"""G5 — credenciais nunca aparecem em log, ledger, relatório, screenshot ou trace.

A defesa não é "lembrar de não logar a senha": é passar tudo que sai do processo por
`limpar()`. Um segredo que nunca foi registrado aqui não pode ser redigido, então
`registrar_segredo()` é chamado no mesmo lugar em que as credenciais são carregadas.
"""

from __future__ import annotations

import re

REDIGIDO = "***REDIGIDO***"

# Segredos conhecidos em runtime. Ordenado por comprimento decrescente na hora de
# aplicar, para que uma senha que contenha o usuário como substring seja redigida
# por inteiro antes de o usuário ser redigido dentro dela.
_segredos: set[str] = set()

# Chaves cujo VALOR é sempre suspeito, mesmo que o valor não esteja registrado —
# pega o caso de uma senha nova aparecendo num dump de config antes do registro.
# O `["']?` antes do separador cobre a chave entre aspas do JSON (`"password": x`),
# e o prefixo opcional cobre `BENNER_PASSWORD`, `db-password` etc.
_CHAVES_SENSIVEIS = re.compile(
    r"(?i)([\w.-]*(?:senha|password|passwd|pwd|secret|token|api[_-]?key|authorization)"
    r"[\w.-]*)[\"']?\s*[:=]\s*(\"[^\"]*\"|'[^']*'|[^\s,;}\]]+)"
)


def registrar_segredo(valor: str | None) -> None:
    """Registra um valor a ser redigido de toda saída. Idempotente."""
    if valor and len(valor.strip()) >= 3:
        _segredos.add(valor.strip())


def esquecer_segredos() -> None:
    """Só para testes — limpa o registro."""
    _segredos.clear()


def segredos_registrados() -> int:
    return len(_segredos)


def limpar(texto: object) -> str:
    """Devolve `texto` como str com todo segredo conhecido substituído.

    Aceita qualquer objeto (exceção, path, dict) porque os pontos de saída chamam
    isto em cima de coisas heterogêneas.
    """
    s = texto if isinstance(texto, str) else str(texto)

    # Mais longos primeiro: evita que redigir o usuário quebre a detecção da senha.
    for segredo in sorted(_segredos, key=len, reverse=True):
        if segredo in s:
            s = s.replace(segredo, REDIGIDO)

    return _CHAVES_SENSIVEIS.sub(lambda m: f"{m.group(1)}={REDIGIDO}", s)


def limpar_estrutura(dados: object) -> object:
    """Aplica `limpar` recursivamente em dict/list/str, preservando a forma."""
    if isinstance(dados, dict):
        return {k: limpar_estrutura(v) for k, v in dados.items()}
    if isinstance(dados, (list, tuple)):
        tipo = type(dados)
        return tipo(limpar_estrutura(v) for v in dados)
    if isinstance(dados, str):
        return limpar(dados)
    return dados


def contem_segredo(texto: object) -> bool:
    """True se algum segredo registrado aparece cru em `texto`. Base do teste do G5."""
    s = texto if isinstance(texto, str) else str(texto)
    return any(segredo in s for segredo in _segredos)
