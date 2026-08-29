"""`relatorio_lote.md` — composição e, sobretudo, o que ele nunca pode conter."""

from pathlib import Path

import pytest

from benner_rpa.core import segredos
from benner_rpa.core.estados import Estado
from benner_rpa.core.lote import ResultadoProcesso
from benner_rpa.core.planilha import LinhaProcesso
from benner_rpa.core.relatorio import compor, gravar

PROC = LinhaProcesso(2, "CCR", "Fulano", "0000000-22.2023.5.15.0002")
PROC2 = LinhaProcesso(3, "CCR", "Beltrano", "1000001-33.2026.5.02.0003")
PROC3 = LinhaProcesso(4, "CCR", "Cicrano", "1000000-11.2024.5.02.0001")


def _concluido(p, **d):
    base = {
        "pasta_benner": "TRAB.000003", "docs_listados_popup": 93, "docs_no_zip": 93,
        "pedidos_exportados": "SIM", "bytes_zip": 131_059_962,
        "selecao": {"link_restantes_acionado": True},
    }
    return ResultadoProcesso(p, Estado.CONCLUIDO, detalhe={**base, **d}, tentativas=1)


def test_o_que_exige_pessoa_vem_antes_do_resumo():
    md = compor(
        [_concluido(PROC),
         ResultadoProcesso(PROC2, Estado.AMBIGUO, observacao="2 itens no grupo PASTAS")],
        total_na_planilha=333, raiz_saida=Path("saida"),
    )

    assert md.index("Exige decisão humana") < md.index("## Resumo")
    assert "2 itens no grupo PASTAS" in md


def test_secao_de_decisao_some_quando_nao_ha_nada_a_decidir():
    md = compor([_concluido(PROC)], total_na_planilha=333, raiz_saida=Path("saida"))
    assert "Exige decisão humana" not in md


def test_projecao_usa_a_media_medida_e_nao_os_44gb():
    md = compor([_concluido(PROC), _concluido(PROC2)],
                total_na_planilha=333, raiz_saida=Path("saida"))

    assert "Média medida por processo" in md
    assert "amostra de 2" in md
    assert "Projeção para os 331 restantes" in md


def test_evidencia_do_g2_aparece_contada():
    md = compor(
        [_concluido(PROC),
         _concluido(PROC2, selecao={"link_restantes_acionado": False})],
        total_na_planilha=333, raiz_saida=Path("saida"),
    )

    assert "Seleção completa (G2)" in md
    assert "**1** de 2" in md


def test_falhas_retentaveis_separadas_das_terminais():
    md = compor(
        [ResultadoProcesso(PROC, Estado.ERRO, observacao="timeout", tentativas=3),
         ResultadoProcesso(PROC2, Estado.PARCIAL, observacao="faltando: pedidos", tentativas=2),
         ResultadoProcesso(PROC3, Estado.NAO_ENCONTRADO, observacao="sem item")],
        total_na_planilha=333, raiz_saida=Path("saida"),
    )

    decisao = md.index("Exige decisão humana")
    retentavel = md.index("Falhas retentáveis")

    assert md.index("sem item") < retentavel        # terminal está na seção de cima
    assert decisao < retentavel
    assert "faltando: pedidos" in md


def test_relatorio_nunca_vaza_credencial(tmp_path):
    segredos.esquecer_segredos()
    segredos.registrar_segredo("SenhaFalsaDeTeste@2026")
    try:
        md = compor(
            [ResultadoProcesso(PROC, Estado.ERRO,
                               observacao="login falhou com senha SenhaFalsaDeTeste@2026")],
            total_na_planilha=333, raiz_saida=Path("saida"),
        )
        destino = gravar(md, tmp_path / "relatorio_lote.md")

        assert "SenhaFalsaDeTeste@2026" not in destino.read_text(encoding="utf-8")
        assert segredos.REDIGIDO in destino.read_text(encoding="utf-8")
    finally:
        segredos.esquecer_segredos()


def test_lote_vazio_nao_quebra():
    md = compor([], total_na_planilha=333, raiz_saida=Path("saida"))
    assert "# Relatório do lote" in md


def test_pendencias_sao_registradas():
    md = compor([_concluido(PROC)], total_na_planilha=333, raiz_saida=Path("saida"),
                pendencias=["Exportar para Excel respeita a paginação? — medir no piloto"])

    assert "Pendências registradas" in md
    assert "paginação" in md
