"""Máquina de estados do processo (§6 do plano).

As transições são declaradas, não espalhadas por `if`s: um estado só muda por
`transicionar()`, que recusa transição não prevista. É o que impede o robô de
marcar CONCLUIDO a partir de um estado que não o autoriza.
"""

from __future__ import annotations

from enum import Enum


class Estado(str, Enum):
    PENDENTE = "PENDENTE"
    EM_ANDAMENTO = "EM_ANDAMENTO"
    CONCLUIDO = "CONCLUIDO"
    PARCIAL = "PARCIAL"
    NAO_ENCONTRADO = "NAO_ENCONTRADO"
    AMBIGUO = "AMBIGUO"
    ERRO = "ERRO"
    BLOQUEADO = "BLOQUEADO"

    def __str__(self) -> str:
        return self.value


TRANSICOES: dict[Estado, frozenset[Estado]] = {
    Estado.PENDENTE: frozenset({Estado.EM_ANDAMENTO, Estado.BLOQUEADO}),
    Estado.EM_ANDAMENTO: frozenset({
        Estado.CONCLUIDO, Estado.PARCIAL, Estado.NAO_ENCONTRADO,
        Estado.AMBIGUO, Estado.ERRO, Estado.PENDENTE, Estado.BLOQUEADO,
    }),
    # Retenta apenas o artefato que falta — não rebaixa 131 MB por um XLSX de 3 KB.
    Estado.PARCIAL: frozenset({Estado.EM_ANDAMENTO, Estado.BLOQUEADO}),
    Estado.ERRO: frozenset({Estado.EM_ANDAMENTO, Estado.BLOQUEADO}),
    # Volta a EM_ANDAMENTO só quando a verificação de disco reprova o manifest.
    Estado.CONCLUIDO: frozenset({Estado.EM_ANDAMENTO}),
    # Terminais: o robô nunca resolve ambiguidade nem inventa um processo que não achou.
    Estado.NAO_ENCONTRADO: frozenset(),
    Estado.AMBIGUO: frozenset(),
    Estado.BLOQUEADO: frozenset(),
}

# Estados em que a reexecução não deve gastar acesso ao Benner.
TERMINAIS = frozenset({Estado.NAO_ENCONTRADO, Estado.AMBIGUO, Estado.BLOQUEADO})

REPROCESSAVEIS = frozenset({Estado.PENDENTE, Estado.PARCIAL, Estado.ERRO})


class TransicaoInvalida(RuntimeError):
    """Transição não prevista em TRANSICOES."""


def pode_transicionar(de: Estado, para: Estado) -> bool:
    return para in TRANSICOES.get(de, frozenset())


def transicionar(de: Estado, para: Estado) -> Estado:
    if not pode_transicionar(de, para):
        raise TransicaoInvalida(f"{de} -> {para} nao e uma transicao valida")
    return para


def precisa_processar(estado: Estado) -> bool:
    """CONCLUIDO fica de fora: quem decide reprocessá-lo é a verificação de disco."""
    return estado in REPROCESSAVEIS
