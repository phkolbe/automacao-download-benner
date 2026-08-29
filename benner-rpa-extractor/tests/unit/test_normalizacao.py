"""Normalização de número de processo e nome de pasta."""

import pytest

from benner_rpa.core.normalizacao import (
    eh_cnj_valido,
    formatar_cnj,
    mesma_identidade,
    nome_pasta_processo,
    normalizar_cabecalho,
    normalizar_processo,
    sanitizar_nome_pasta,
)

REAL = "0000000-22.2023.5.15.0002"
REAL_DIGITOS = "00000002220235150002"


@pytest.mark.parametrize("entrada", [
    REAL,
    REAL_DIGITOS,
    f"  {REAL}  ",
    "0000000-22.2023.5.15.0002\n",
    "0000000 22 2023 5 15 0002",
])
def test_formas_equivalentes_normalizam_igual(entrada):
    assert normalizar_processo(entrada) == REAL_DIGITOS


def test_normalizar_tolera_nulo_e_numero():
    assert normalizar_processo(None) == ""
    assert normalizar_processo(12033) == "12033"


def test_identidade_ignora_mascara_e_espaco():
    assert mesma_identidade(REAL, REAL_DIGITOS)
    assert mesma_identidade(f" {REAL} ", REAL)


def test_identidade_recusa_numero_diferente():
    assert not mesma_identidade(REAL, "1000000-11.2024.5.02.0001")


def test_identidade_recusa_vazio():
    """Vazio contra vazio não é identidade — é ausência de dado dos dois lados."""
    assert not mesma_identidade("", "")
    assert not mesma_identidade(None, REAL)


def test_identidade_recusa_prefixo():
    """Um número que é prefixo do outro não é o mesmo processo."""
    assert not mesma_identidade(REAL_DIGITOS, REAL_DIGITOS[:-1])


def test_cnj_valido():
    assert eh_cnj_valido(REAL)
    assert eh_cnj_valido(REAL_DIGITOS)
    assert not eh_cnj_valido("123")
    assert not eh_cnj_valido(REAL_DIGITOS + "9")
    assert not eh_cnj_valido("")


def test_formatar_aplica_a_mascara():
    assert formatar_cnj(REAL_DIGITOS) == REAL
    assert formatar_cnj(REAL) == REAL


def test_formatar_devolve_como_veio_se_nao_for_cnj():
    assert formatar_cnj("abc") == "abc"


@pytest.mark.parametrize("cabecalho", [
    "Nº PROCESSO", "N° PROCESSO", "nº processo", "  Nº  Processo ", "NUMERO PROCESSO",
])
def test_cabecalho_normaliza_para_a_mesma_forma(cabecalho):
    assert normalizar_cabecalho(cabecalho) == "n processo"


def test_cabecalho_distingue_colunas_diferentes():
    assert normalizar_cabecalho("RECLAMADA") != normalizar_cabecalho("Nº PROCESSO")


@pytest.mark.parametrize("proibido", list('<>:"/\\|?*'))
def test_sanitizacao_troca_caractere_proibido_no_windows(proibido):
    assert proibido not in sanitizar_nome_pasta(f"proc{proibido}123")


def test_sanitizacao_remove_ponto_e_espaco_finais():
    """O Windows não guarda componente de caminho terminado em ponto ou espaço."""
    assert sanitizar_nome_pasta("processo. ") == "processo"


def test_sanitizacao_escapa_nome_reservado():
    for reservado in ("CON", "PRN", "NUL", "COM1", "LPT9", "con.txt"):
        assert sanitizar_nome_pasta(reservado).startswith("_")


def test_sanitizacao_nunca_devolve_vazio():
    assert sanitizar_nome_pasta("...") == "_sem_nome"
    assert sanitizar_nome_pasta("") == "_sem_nome"


def test_sanitizacao_preserva_acento_e_caixa():
    """O nome tem que continuar reconhecível por uma pessoa."""
    assert sanitizar_nome_pasta("Ação Trabalhista") == "Ação Trabalhista"


def test_nome_da_pasta_e_o_da_planilha():
    """Decisão do plano: a pasta usa o número como está na planilha, não o normalizado."""
    assert nome_pasta_processo(REAL) == REAL
    assert nome_pasta_processo(f"  {REAL}  ") == REAL


def test_nome_da_pasta_nao_vira_o_normalizado():
    assert nome_pasta_processo(REAL) != REAL_DIGITOS
