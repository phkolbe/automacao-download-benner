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


def test_imprimir_resultados_exercita_cada_nome():
    """O teste que faltava — e que teria pego DOIS erros seguidos.

    `test_o_modulo_importa` pega erro de sintaxe, mas não erro de NOME: um
    `humanizar_duracao` não importado só explode quando a linha executa. E essa linha
    vivia dentro de `cmd_lote`, que só roda com conexão ao Benner — nenhum teste
    chegava lá.

    Por isso a impressão foi extraída para uma função pura: aqui ela roda com
    resultados falsos e cada nome usado é de fato avaliado.
    """
    from benner_rpa.core.estados import Estado
    from benner_rpa.core.lote import ResultadoProcesso
    from benner_rpa.core.planilha import LinhaProcesso

    resultados = [
        ResultadoProcesso(
            LinhaProcesso(2, "A", "B", "0000000-22.2023.5.15.0002"),
            Estado.CONCLUIDO, duracao_s=252.0, tentativas=1,
        ),
        ResultadoProcesso(
            LinhaProcesso(3, "A", "C", "1000001-33.2026.5.02.0003"),
            Estado.PARCIAL, observacao="faltando: pedidos", duracao_s=0.0, tentativas=3,
        ),
    ]

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        cli.imprimir_resultados(resultados, parede_s=310.0)

    texto = buffer.getvalue()

    assert "ok 0000000-22.2023.5.15.0002  CONCLUIDO  [4m 12s]" in texto
    assert "!! 1000001-33.2026.5.02.0003  PARCIAL" in texto
    assert "faltando: pedidos" in texto
    assert "tempo total da execucao: 5m 10s" in texto
    assert "(2 processos)" in texto


def test_imprimir_resultados_com_lista_vazia():
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        cli.imprimir_resultados([], parede_s=0.0)

    assert "(0 processos)" in buffer.getvalue()


def _saida_de_mentira(tmp_path, monkeypatch):
    """Monta uma raiz de saída com os quatro casos que `verificar` precisa separar."""
    import yaml

    from benner_rpa.core.config import carregar_config

    saida = tmp_path / "saida"
    saida.mkdir()

    # 1. processo íntegro (nome de processo + manifest válido)
    from benner_rpa.core.manifest import Manifest, registrar_artefato

    bom = saida / "0000000-22.2023.5.15.0002"
    bom.mkdir()
    (bom / "Pedidos.xlsx").write_bytes(b"PK\x03\x04" + b"x" * 500)
    Manifest(
        processo_planilha="0000000-22.2023.5.15.0002",
        processo_normalizado="00000002220235150002",
        artefatos=[registrar_artefato(bom / "Pedidos.xlsx", "passo6")],
        completo=True,
    ).gravar(bom)

    # 2. nome de processo SEM manifest — isto é problema de verdade
    (saida / "1000001-33.2026.5.02.0003").mkdir()

    # 3. pasta de organização humana
    (saida / "testes").mkdir()
    (saida / "testes" / "0000001-44.2026.5.15.0004").mkdir()

    # 4. referência montada à mão (G9)
    (saida / "0000000-22.2023.5.15.0002 - exemplo").mkdir()

    cfg_real = carregar_config()
    dados = dict(cfg_real._bruto)
    dados["saida"] = {**dados["saida"], "raiz": str(saida)}
    alvo = tmp_path / "config.yaml"
    alvo.write_text(yaml.safe_dump(dados, allow_unicode=True), encoding="utf-8")
    return alvo


def test_verificar_ignora_pasta_de_organizacao_mas_diz_que_ignorou(tmp_path, monkeypatch):
    """`saida/testes/` é organização humana, não saída incompleta.

    Mas ignorar em silêncio é como saída de verdade deixa de ser conferida sem
    ninguém notar — então a pasta aparece na listagem.
    """
    alvo = _saida_de_mentira(tmp_path, monkeypatch)

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        codigo = cli.main(["--config", str(alvo), "verificar"])

    texto = buffer.getvalue()

    assert "ignorada (nome nao e de processo): testes" in texto
    assert "referencia (nao conferida, G9)" in texto
    assert codigo == 1        # ainda há uma pasta quebrada de verdade


def test_verificar_nao_deixa_escapar_processo_sem_manifest(tmp_path, monkeypatch):
    """A metade que importa: nome DE PROCESSO sem manifest continua sendo erro."""
    alvo = _saida_de_mentira(tmp_path, monkeypatch)

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        codigo = cli.main(["--config", str(alvo), "verificar"])

    texto = buffer.getvalue()

    assert "! 1000001-33.2026.5.02.0003" in texto
    assert "manifest ausente" in texto
    assert "pastas integras: 1   quebradas: 1" in texto
    assert codigo == 1


def test_comando_desconhecido_falha():
    with pytest.raises(SystemExit) as saida:
        cli.main(["comando-que-nao-existe"])
    assert saida.value.code != 0
