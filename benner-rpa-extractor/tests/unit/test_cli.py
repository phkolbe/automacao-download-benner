"""O CLI existe, importa e responde — o teste que faltava.

Em 29/08/2026 um erro de sintaxe no `cli.py` foi commitado e chegou ao GitHub com os
169 testes verdes: nenhum deles importava o módulo. Um arquivo que nada importa não é
coberto por nada, por mais testes que o projeto tenha.

Estes testes não tocam o Benner: só exercitam o que roda offline.
"""

import io
import contextlib

import pytest

from benner_rpa import cli


def test_o_modulo_importa():
    """Pega erro de sintaxe. Trivial, e teria evitado um commit quebrado."""
    assert callable(cli.main)
    assert set(cli.COMANDOS) == {"auditar", "verificar", "pre-voo", "lote"}


def test_help_nao_explode():
    with pytest.raises(SystemExit) as saida:
        cli.main(["--help"])
    assert saida.value.code == 0


@pytest.mark.parametrize("comando", ["auditar", "verificar", "pre-voo", "lote"])
def test_cada_subcomando_tem_help(comando):
    with pytest.raises(SystemExit) as saida:
        cli.main([comando, "--help"])
    assert saida.value.code == 0


def test_auditar_roda_sem_tocar_o_benner():
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        codigo = cli.main(["auditar"])

    texto = buffer.getvalue()
    assert codigo == 0
    assert "processos:" in texto
    assert "disco" in texto


def test_lote_sem_autorizacao_sai_com_10(tmp_path, monkeypatch):
    """G10 pela porta do CLI: sem autorização, exit 10 e nada acontece."""
    import yaml

    from benner_rpa.core.config import carregar_config

    cfg_real = carregar_config()
    dados = dict(cfg_real._bruto)
    dados["gates"] = {"acesso_real_autorizado": False}

    alvo = tmp_path / "config.yaml"
    alvo.write_text(yaml.safe_dump(dados, allow_unicode=True), encoding="utf-8")

    erro = io.StringIO()
    with contextlib.redirect_stderr(erro):
        codigo = cli.main(["--config", str(alvo), "lote", "--limite", "1"])

    assert codigo == 10
    assert "G10" in erro.getvalue()


def test_comando_desconhecido_falha():
    with pytest.raises(SystemExit) as saida:
        cli.main(["comando-que-nao-existe"])
    assert saida.value.code != 0
