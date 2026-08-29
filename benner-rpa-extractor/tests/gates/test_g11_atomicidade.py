"""G11 — a pasta final só existe com manifest válido."""

import json
import zipfile

import pytest

from benner_rpa.core.estados import Estado, TransicaoInvalida, precisa_processar, transicionar
from benner_rpa.core.ledger import Ledger, reconciliar
from benner_rpa.core.manifest import (
    Manifest,
    limpar_tmp_orfas,
    manifest_valido,
    pasta_trabalho,
    promover,
    registrar_artefato,
)

pytestmark = pytest.mark.gate

PROCESSO = "0000000-22.2023.5.15.0002"
NORMALIZADO = "00000002220235150002"


def _pacote_completo(tmp_path, entradas=93):
    """Monta uma `.tmp` com ZIP + Pedidos + manifest válido, como o robô faria."""
    work = tmp_path / "_work"
    tmp = pasta_trabalho(work, PROCESSO)

    zip_path = tmp / "Lote_de_documentos_TRAB.000003.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        for i in range(entradas):
            z.writestr(f"doc{i:03d}.pdf", b"conteudo" * 300)

    pedidos = tmp / "Pedidos.xlsx"
    pedidos.write_bytes(b"PK\x03\x04" + b"fake xlsx" * 100)

    m = Manifest(
        processo_planilha=PROCESSO,
        processo_normalizado=NORMALIZADO,
        pasta_benner="TRAB.000003",
        numero_conferido_na_tela=PROCESSO,
        selecao={
            "itens_por_pagina": 10,
            "link_restantes_presente": True,
            "link_restantes_acionado": True,
            "link_ausente_ao_baixar": True,
        },
        artefatos=[
            registrar_artefato(zip_path, "passo5", validar_como_zip=True),
            registrar_artefato(pedidos, "passo6"),
        ],
        completo=True,
    )
    m.gravar(tmp)
    return work, tmp


def test_promocao_com_manifest_valido(tmp_path):
    work, tmp = _pacote_completo(tmp_path)
    destino = tmp_path / "saida" / PROCESSO

    final = promover(tmp, destino)

    assert final.exists()
    assert not tmp.exists()                    # a .tmp deixou de existir
    assert (final / "_manifest.json").exists()
    assert (final / "Lote_de_documentos_TRAB.000003.zip").exists()


def test_promocao_sem_manifest_e_negada(tmp_path):
    work = tmp_path / "_work"
    tmp = pasta_trabalho(work, PROCESSO)
    (tmp / "Lote_de_documentos_TRAB.000003.zip").write_bytes(b"PK\x03\x04" + b"x" * 5000)

    with pytest.raises(RuntimeError, match="G11"):
        promover(tmp, tmp_path / "saida" / PROCESSO)

    assert not (tmp_path / "saida" / PROCESSO).exists()


def test_promocao_com_artefato_faltando_e_negada(tmp_path):
    work, tmp = _pacote_completo(tmp_path)
    (tmp / "Pedidos.xlsx").unlink()           # manifest declara, disco não tem

    with pytest.raises(RuntimeError, match="G11"):
        promover(tmp, tmp_path / "saida" / PROCESSO)


def test_promocao_com_hash_divergente_e_negada(tmp_path):
    work, tmp = _pacote_completo(tmp_path)
    (tmp / "Pedidos.xlsx").write_bytes(b"PK\x03\x04" + b"OUTRO CONTEUDO" * 100)

    with pytest.raises(RuntimeError, match="G11"):
        promover(tmp, tmp_path / "saida" / PROCESSO)


def test_promocao_nao_sobrescreve_destino_existente(tmp_path):
    work, tmp = _pacote_completo(tmp_path)
    destino = tmp_path / "saida" / PROCESSO
    destino.mkdir(parents=True)
    (destino / "ja_estava_aqui.txt").write_text("nao me apague")

    with pytest.raises(FileExistsError):
        promover(tmp, destino)

    assert (destino / "ja_estava_aqui.txt").exists()


def test_interrupcao_deixa_tmp_e_o_destino_nao_nasce(tmp_path):
    """Simula queda entre baixar e promover."""
    work, tmp = _pacote_completo(tmp_path)
    destino = tmp_path / "saida" / PROCESSO

    assert tmp.exists()
    assert not destino.exists()

    limpas = limpar_tmp_orfas(work)

    assert limpas == [f"{PROCESSO}.tmp"]
    assert not tmp.exists()
    assert not destino.exists()


def test_remover_arquivo_da_pasta_concluida_invalida_o_manifest(tmp_path):
    """Critério do piloto: apagar um arquivo faz o processo ser refeito."""
    work, tmp = _pacote_completo(tmp_path)
    final = promover(tmp, tmp_path / "saida" / PROCESSO)

    assert manifest_valido(final)[0]

    (final / "Pedidos.xlsx").unlink()

    ok, motivo = manifest_valido(final)
    assert not ok
    assert "Pedidos.xlsx" in motivo


def test_reconciliacao_devolve_em_andamento_para_pendente(tmp_path):
    ledger = Ledger(tmp_path / "ledger.jsonl")
    ledger.registrar({
        "processo": PROCESSO, "processo_normalizado": NORMALIZADO,
        "status": Estado.EM_ANDAMENTO.value,
    })

    correcoes = reconciliar(ledger, tmp_path / "saida")

    assert len(correcoes) == 1
    assert correcoes[0]["status"] == Estado.PENDENTE.value
    assert ledger.estado_atual()[NORMALIZADO]["status"] == Estado.PENDENTE.value


def test_reconciliacao_rebaixa_concluido_sem_lastro(tmp_path):
    """CONCLUIDO no ledger, pasta inexistente no disco."""
    ledger = Ledger(tmp_path / "ledger.jsonl")
    ledger.registrar({
        "processo": PROCESSO, "processo_normalizado": NORMALIZADO,
        "status": Estado.CONCLUIDO.value, "pasta_destino": PROCESSO,
    })

    correcoes = reconciliar(ledger, tmp_path / "saida")

    assert correcoes[0]["status"] == Estado.EM_ANDAMENTO.value
    assert "sem lastro" in correcoes[0]["motivo"]


def test_disco_com_manifest_valido_vence_o_ledger(tmp_path):
    """O disco é a verdade sobre o que está feito.

    Cenário real de 29/08/2026: uma execução foi interrompida logo após a promoção.
    O `EM_ANDAMENTO` órfão virou `PENDENTE` na reconciliação, mas a pasta estava
    íntegra. Sem esta regra o processo entra em ciclo — baixa de novo, a promoção é
    recusada porque o destino já vale, vira ERRO, repete.
    """
    work, tmp = _pacote_completo(tmp_path)
    saida = tmp_path / "saida"
    promover(tmp, saida / PROCESSO)

    ledger = Ledger(tmp_path / "ledger.jsonl")
    ledger.registrar({
        "processo": PROCESSO, "processo_normalizado": NORMALIZADO,
        "status": Estado.PENDENTE.value, "pasta_destino": PROCESSO,
    })

    correcoes = reconciliar(ledger, saida)

    assert len(correcoes) == 1
    assert correcoes[0]["status"] == Estado.CONCLUIDO.value
    assert "manifest valido" in correcoes[0]["motivo"]
    assert ledger.estado_atual()[NORMALIZADO]["status"] == Estado.CONCLUIDO.value


def test_orquestrador_pula_pasta_integra_mesmo_com_ledger_atrasado(tmp_path):
    """A mesma regra pelo lado do orquestrador: não refaz o que está pronto."""
    from benner_rpa.core.lote import Orquestrador

    work, tmp = _pacote_completo(tmp_path)
    saida = tmp_path / "saida"
    promover(tmp, saida / PROCESSO)

    ledger = Ledger(tmp_path / "ledger.jsonl")
    ledger.registrar({
        "processo": PROCESSO, "processo_normalizado": NORMALIZADO,
        "status": Estado.PENDENTE.value,
    })

    from benner_rpa.core.planilha import LinhaProcesso

    class NaoDeveSerChamado:
        def sessao_viva(self): return True
        def reconectar(self): pass
        def fechar(self): pass
        def extrair(self, processo, destino):
            raise AssertionError("o processo ja estava pronto no disco")

    o = Orquestrador(extrator=NaoDeveSerChamado(), raiz_saida=saida, ledger=ledger,
                     throttle_s=0)
    o.dormir = lambda _s: None

    assert o.executar([LinhaProcesso(2, "A", "B", PROCESSO)]) == []


def test_reconciliacao_preserva_concluido_com_lastro(tmp_path):
    work, tmp = _pacote_completo(tmp_path)
    saida = tmp_path / "saida"
    promover(tmp, saida / PROCESSO)

    ledger = Ledger(tmp_path / "ledger.jsonl")
    ledger.registrar({
        "processo": PROCESSO, "processo_normalizado": NORMALIZADO,
        "status": Estado.CONCLUIDO.value, "pasta_destino": PROCESSO,
    })

    assert reconciliar(ledger, saida) == []


def test_ledger_e_append_only(tmp_path):
    ledger = Ledger(tmp_path / "ledger.jsonl")
    for status in [Estado.EM_ANDAMENTO, Estado.PARCIAL, Estado.CONCLUIDO]:
        ledger.registrar({"processo_normalizado": NORMALIZADO, "status": status.value})

    linhas = (tmp_path / "ledger.jsonl").read_text(encoding="utf-8").strip().splitlines()

    assert len(linhas) == 3                                    # nada foi sobrescrito
    assert ledger.estado_atual()[NORMALIZADO]["status"] == "CONCLUIDO"  # vale a última


def test_ledger_tolera_linha_truncada(tmp_path):
    caminho = tmp_path / "ledger.jsonl"
    ledger = Ledger(caminho)
    ledger.registrar({"processo_normalizado": NORMALIZADO, "status": "EM_ANDAMENTO"})

    with caminho.open("a", encoding="utf-8") as fh:
        fh.write('{"processo_normalizado": "003", "sta')   # queda no meio da escrita

    assert len(ledger.eventos()) == 1


# ---------------------------------------------------------------- máquina de estados

def test_terminais_nao_transicionam():
    for terminal in (Estado.NAO_ENCONTRADO, Estado.AMBIGUO):
        with pytest.raises(TransicaoInvalida):
            transicionar(terminal, Estado.EM_ANDAMENTO)


def test_pendente_nao_pula_direto_para_concluido():
    with pytest.raises(TransicaoInvalida):
        transicionar(Estado.PENDENTE, Estado.CONCLUIDO)


def test_concluido_so_volta_para_em_andamento():
    assert transicionar(Estado.CONCLUIDO, Estado.EM_ANDAMENTO) == Estado.EM_ANDAMENTO
    with pytest.raises(TransicaoInvalida):
        transicionar(Estado.CONCLUIDO, Estado.PENDENTE)


def test_parcial_retenta():
    assert precisa_processar(Estado.PARCIAL)
    assert precisa_processar(Estado.ERRO)
    assert precisa_processar(Estado.PENDENTE)
    assert not precisa_processar(Estado.CONCLUIDO)
    assert not precisa_processar(Estado.AMBIGUO)


def test_manifest_serializa_a_evidencia_da_selecao(tmp_path):
    """O manifest tem que provar que o G2 foi cumprido, não só afirmar CONCLUIDO."""
    work, tmp = _pacote_completo(tmp_path)
    dados = json.loads((tmp / "_manifest.json").read_text(encoding="utf-8"))

    assert dados["selecao"]["link_restantes_acionado"] is True
    assert dados["selecao"]["link_ausente_ao_baixar"] is True
    assert dados["artefatos"][0]["zip"]["entradas"] == 93
