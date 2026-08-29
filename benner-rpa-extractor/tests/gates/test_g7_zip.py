"""G7 — ZIP nunca extraído. Nenhum arquivo criado no disco durante a validação."""

import zipfile

import pytest

from benner_rpa.core.zip_seguro import ASSINATURA_ZIP, conferir_contagem, validar_zip

pytestmark = pytest.mark.gate


def _zip_com(tmp_path, entradas: dict[str, bytes], nome="pacote.zip"):
    caminho = tmp_path / nome
    with zipfile.ZipFile(caminho, "w") as z:
        for n, conteudo in entradas.items():
            z.writestr(n, conteudo)
    return caminho


def test_zip_valido_reporta_entradas(tmp_path):
    z = _zip_com(tmp_path, {f"doc{i}.pdf": b"x" * 2000 for i in range(93)})
    r = validar_zip(z)

    assert r.valido
    assert r.entradas == 93          # o número da pasta de referência
    assert len(r.nomes) == 93


def test_validacao_nao_cria_nenhum_arquivo_no_disco(tmp_path):
    """O teste que o gate exige por escrito."""
    pasta = tmp_path / "isolada"
    pasta.mkdir()
    z = _zip_com(pasta, {f"doc{i}.pdf": b"y" * 3000 for i in range(12)})

    antes = {p.name for p in pasta.rglob("*")}
    r = validar_zip(z)
    depois = {p.name for p in pasta.rglob("*")}

    assert r.valido
    assert antes == depois, f"validacao criou arquivos: {depois - antes}"


def test_html_renomeado_para_zip_e_rejeitado(tmp_path):
    """Página de erro do servidor com nome .zip — o caso que motiva os bytes mágicos."""
    falso = tmp_path / "Lote_de_documentos_TRAB.000003.zip"
    falso.write_bytes(b"<html><body>Sessao expirada</body></html>" * 40)

    r = validar_zip(falso)
    assert not r.valido
    assert "magicos" in r.motivo


def test_zip_pequeno_demais_e_rejeitado(tmp_path):
    minusculo = tmp_path / "p.zip"
    minusculo.write_bytes(ASSINATURA_ZIP + b"\x00" * 50)

    assert not validar_zip(minusculo).valido


def test_zip_truncado_e_rejeitado(tmp_path):
    z = _zip_com(tmp_path, {f"d{i}.pdf": b"z" * 5000 for i in range(10)})
    dados = z.read_bytes()
    z.write_bytes(dados[: len(dados) // 2])   # corta o índice central

    assert not validar_zip(z).valido


def test_arquivo_inexistente_e_vazio(tmp_path):
    assert not validar_zip(tmp_path / "nao-existe.zip").valido

    vazio = tmp_path / "vazio.zip"
    vazio.write_bytes(b"")
    assert not validar_zip(vazio).valido


def test_contagem_confere_com_a_popup(tmp_path):
    z = _zip_com(tmp_path, {f"d{i}.pdf": b"a" * 2000 for i in range(93)})
    ok, motivo = conferir_contagem(validar_zip(z), 93)
    assert ok, motivo


def test_zip_com_10_de_93_reprova_G2(tmp_path):
    """A falha silenciosa: link "Selecionar todos os restantes?" não acionado."""
    z = _zip_com(tmp_path, {f"d{i}.pdf": b"a" * 2000 for i in range(10)})
    ok, motivo = conferir_contagem(validar_zip(z), 93)

    assert not ok
    assert "10" in motivo and "93" in motivo
    assert "G2" in motivo


def test_pasta_de_referencia_real_valida():
    """Contra o artefato humano de verdade — 93 entradas, 131 MB."""
    from pathlib import Path

    # A pasta é achada por padrão, não fixada: seu nome carrega um processo real.
    raiz = Path(r"C:\MyWorkspace\claude-code\automacaoDeCastro\saida")
    pastas = sorted(raiz.glob("* - exemplo")) if raiz.exists() else []
    zips = sorted(pastas[0].glob("*.zip")) if pastas else []

    if not zips:
        pytest.skip("pasta de referencia indisponivel neste ambiente")

    r = validar_zip(zips[0])
    assert r.valido
    assert r.entradas > 0
    assert r.bytes > 1_000_000
    assert r.motivo == ""
