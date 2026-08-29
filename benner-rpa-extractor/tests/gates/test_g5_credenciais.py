"""G5 — credenciais ausentes de log, exceção, ledger, relatório, screenshot e trace.

Os valores abaixo são INVENTADOS. Nunca usar a credencial real como dado de teste:
num repositório Git ela fica no histórico para sempre, e foi exatamente o que quase
aconteceu aqui em 29/08/2026 — no arquivo de teste do gate que proíbe isso.
"""

import json

import pytest

from benner_rpa.core import segredos
from benner_rpa.core.ledger import Ledger

pytestmark = pytest.mark.gate

SENHA = "SenhaFalsaDeTeste@2026"
USUARIO = "usuario.falso.teste"


@pytest.fixture(autouse=True)
def registrar():
    segredos.esquecer_segredos()
    segredos.registrar_segredo(SENHA)
    segredos.registrar_segredo(USUARIO)
    yield
    segredos.esquecer_segredos()


def test_senha_redigida_em_texto_livre():
    saida = segredos.limpar(f"login falhou para {USUARIO} com senha {SENHA}")
    assert SENHA not in saida
    assert USUARIO not in saida
    assert segredos.REDIGIDO in saida


def test_senha_redigida_dentro_de_url():
    url = f"https://{USUARIO}:{SENHA}@ccr.bennercloud.com.br/JURIDICO_EXT/Login"
    assert not segredos.contem_segredo(segredos.limpar(url))


def test_senha_redigida_em_repr_de_excecao():
    try:
        raise RuntimeError(f"timeout autenticando {USUARIO}/{SENHA}")
    except RuntimeError as erro:
        assert not segredos.contem_segredo(segredos.limpar(erro))


def test_chave_sensivel_redigida_mesmo_sem_registro_previo():
    """Senha nova, ainda não registrada, num dump de config."""
    segredos.esquecer_segredos()
    saida = segredos.limpar('{"BENNER_PASSWORD": "SenhaQueNinguemRegistrou1"}')
    assert "SenhaQueNinguemRegistrou1" not in saida


def test_estrutura_aninhada_preserva_forma_e_redige():
    entrada = {
        "user": USUARIO,
        "tentativas": [{"erro": f"401 para {SENHA}"}],
        "bytes": 131059962,
    }
    saida = segredos.limpar_estrutura(entrada)

    assert saida["bytes"] == 131059962           # não-strings intactos
    assert isinstance(saida["tentativas"], list)  # forma preservada
    assert not segredos.contem_segredo(json.dumps(saida, ensure_ascii=False))


def test_ledger_nunca_grava_credencial(tmp_path):
    """A varredura que o gate exige: tudo que saiu no arquivo, byte a byte."""
    ledger = Ledger(tmp_path / "ledger.jsonl")
    ledger.registrar({
        "processo": "0000000-22.2023.5.15.0002",
        "status": "ERRO",
        "observacao": f"sessao caiu; re-login com {USUARIO}/{SENHA} falhou",
    })

    bruto = (tmp_path / "ledger.jsonl").read_text(encoding="utf-8")
    assert SENHA not in bruto
    assert USUARIO not in bruto
    assert segredos.REDIGIDO in bruto


def test_senha_contida_no_usuario_nao_vaza_por_ordem_de_redacao():
    """Segredo curto contido no longo: o longo tem que ser redigido primeiro."""
    segredos.esquecer_segredos()
    segredos.registrar_segredo("abc")
    segredos.registrar_segredo("abc12345")

    assert not segredos.contem_segredo(segredos.limpar("valor=abc12345"))
