"""Normalização de número de processo e de nome de pasta.

A planilha atual é 100% uniforme (333 números no formato CNJ, todos texto, sem
duplicidade — ver docs/GROUND-TRUTH.md). Nada aqui dispara nela. Existe porque a
próxima planilha pode não ter esse cuidado, e porque comparar número de tela com
número de planilha exige uma forma canônica dos dois lados.
"""

from __future__ import annotations

import re
import unicodedata

# CNJ: NNNNNNN-NN.NNNN.N.NN.NNNN — 20 dígitos.
_MASCARA_CNJ = re.compile(r"^(\d{7})(\d{2})(\d{4})(\d)(\d{2})(\d{4})$")

# O Windows proíbe estes em nome de arquivo/pasta, mais os de controle.
_PROIBIDOS_WINDOWS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Nomes reservados do Windows, com ou sem extensão.
_RESERVADOS_WINDOWS = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def normalizar_processo(valor: object) -> str:
    """Reduz um número de processo à sua forma canônica: só os dígitos.

    É esta forma que se compara — nunca a mascarada. `0000000-22.2023.5.15.0002`,
    `00000002220235150002` e `0000000-22.2023.5.15.0002 ` viram a mesma coisa.
    """
    if valor is None:
        return ""
    return re.sub(r"\D", "", str(valor))


def eh_cnj_valido(valor: object) -> bool:
    """True se o valor normalizado tem exatamente os 20 dígitos do padrão CNJ."""
    return bool(_MASCARA_CNJ.match(normalizar_processo(valor)))


def formatar_cnj(valor: object) -> str:
    """Devolve o número na máscara CNJ. Se não for CNJ válido, devolve como veio."""
    m = _MASCARA_CNJ.match(normalizar_processo(valor))
    if not m:
        return str(valor) if valor is not None else ""
    return "{}-{}.{}.{}.{}.{}".format(*m.groups())


def mesma_identidade(a: object, b: object) -> bool:
    """Compara dois números de processo pela forma canônica.

    É a função do G4: o número lido na tela contra o número da planilha. Nunca
    comparar as strings cruas — máscara, espaço e zero à esquerda divergem sem
    que a identidade divirja.
    """
    na, nb = normalizar_processo(a), normalizar_processo(b)
    return bool(na) and na == nb


def _remover_acentos(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)
    )


def normalizar_cabecalho(texto: object) -> str:
    """Forma canônica de um cabeçalho de coluna, para detecção tolerante.

    `Nº PROCESSO` → `n processo`. Precisa aguentar o ordinal `º`, acento e caixa —
    é o cabeçalho real da planilha (docs/GROUND-TRUTH.md).
    """
    # Os indicadores ordinais saem ANTES do NFKD: a decomposição de compatibilidade
    # transforma `º` (U+00BA) na letra `o`, e `Nº PROCESSO` viraria `no processo`.
    # O `°` (U+00B0, grau) não decompõe — por isso a remoção precisa cobrir os dois.
    s = str(texto or "").replace("º", "").replace("ª", "").replace("°", "")
    s = _remover_acentos(s).lower()
    # `numero` também vira `n`, para casar com o cabeçalho `Nº`.
    s = re.sub(r"\bnumero\b", "n", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return s.strip()


def sanitizar_nome_pasta(nome: str) -> str:
    """Torna `nome` utilizável como pasta no Windows, mudando o mínimo possível.

    Não normaliza acento e não mexe em maiúsculas: o nome da pasta tem que ser
    reconhecível por uma pessoa e, na planilha atual, sair idêntico ao da planilha.
    """
    limpo = _PROIBIDOS_WINDOWS.sub("_", nome)
    # O Windows não guarda ponto nem espaço no fim de um componente de caminho.
    limpo = limpo.rstrip(" .")
    if not limpo:
        return "_sem_nome"
    if limpo.split(".")[0].upper() in _RESERVADOS_WINDOWS:
        limpo = f"_{limpo}"
    return limpo[:200]


def nome_pasta_processo(numero_planilha: str) -> str:
    """Nome da pasta de saída: exatamente como está na planilha, só sanitizado.

    Decisão do plano §1: o nome vem da planilha, não do número normalizado, para
    que a pasta seja rastreável até a linha que a originou.
    """
    return sanitizar_nome_pasta(str(numero_planilha).strip())
