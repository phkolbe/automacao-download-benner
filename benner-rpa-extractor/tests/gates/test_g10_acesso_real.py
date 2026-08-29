"""G10 — nenhum acesso ao Benner real sem autorização humana explícita.

O gate é estrutural: `exigir_autorizacao_de_acesso()` levanta a menos que a
autorização esteja ligada em `config.yaml`. O padrão do arquivo versionado é
desligado, e um teste guarda isso — para que ligar a autorização seja sempre um
ato deliberado e visível no diff.
"""

from pathlib import Path

import pytest
import yaml

from benner_rpa.core.config import (
    AcessoRealNaoAutorizado,
    Config,
    ConfiguracaoInvalida,
    Credenciais,
    carregar_config,
)

pytestmark = pytest.mark.gate

CONFIG = Path(__file__).resolve().parents[2] / "config.yaml"


def _cfg_padrao() -> Config:
    """Config com os gates no padrão — testa o MECANISMO, não o arquivo ao vivo."""
    return Config(benner={}, saida={}, planilha={}, lote={}, gates={})


def test_config_versionado_vem_com_acesso_desligado():
    """Guarda de commit: a autorização não pode ficar ligada no repositório.

    Este teste falha DE PROPÓSITO enquanto uma execução real está autorizada. Não é
    defeito — é o gate tornando barulhenta uma porta que ficou aberta. Desligar
    `acesso_real_autorizado` ao terminar faz ele voltar ao verde.
    """
    dados = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    ligado = dados["gates"]["acesso_real_autorizado"]

    assert ligado is False, (
        "G10: acesso_real_autorizado esta LIGADO em config.yaml.\n"
        "Se uma execucao real esta em andamento, isto e esperado.\n"
        "Ao terminar, voltar para false — nao commitar ligado."
    )


def test_acesso_negado_por_padrao():
    cfg = _cfg_padrao()
    assert not cfg.acesso_real_autorizado

    with pytest.raises(AcessoRealNaoAutorizado, match="G10"):
        cfg.exigir_autorizacao_de_acesso("login no Benner")


def test_mensagem_diz_como_autorizar():
    cfg = _cfg_padrao()
    try:
        cfg.exigir_autorizacao_de_acesso("baixar documentos")
    except AcessoRealNaoAutorizado as erro:
        texto = str(erro)
        assert "acesso_real_autorizado" in texto
        assert "autorizacao humana" in texto
        # A mensagem sai em console Windows (cp1252) — nada fora de ASCII, ou vira mojibake.
        texto.encode("ascii")
    else:
        pytest.fail("deveria ter levantado")


def test_autorizacao_explicita_libera():
    cfg = Config(benner={}, saida={}, planilha={}, lote={},
                 gates={"acesso_real_autorizado": True})
    cfg.exigir_autorizacao_de_acesso("piloto de um processo")   # não levanta


def test_config_carrega_sem_pedir_credencial():
    """Todo o desenvolvimento offline roda sem tocar no .env."""
    cfg = carregar_config(CONFIG)
    assert cfg.raiz_saida.name == "saida"
    assert cfg.planilha["aba"] == "Partes e Processos"


def test_credenciais_nao_expoem_a_senha_no_repr():
    c = Credenciais(url="https://x", usuario="fulano", senha="SenhaSecreta123")

    assert "SenhaSecreta123" not in repr(c)
    assert "SenhaSecreta123" not in str(c)


def test_env_incompleto_falha_com_mensagem_clara(tmp_path, monkeypatch):
    for var in ("BENNER_URL", "BENNER_USER", "BENNER_PASSWORD"):
        monkeypatch.delenv(var, raising=False)

    env = tmp_path / ".env"
    env.write_text("BENNER_URL=https://x\n", encoding="utf-8")

    from benner_rpa.core.config import carregar_credenciais

    with pytest.raises(ConfiguracaoInvalida, match="BENNER_USER"):
        carregar_credenciais(env)


def test_env_esta_no_gitignore():
    """G5 — o .env não pode ser versionado por descuido."""
    gitignore = Path(__file__).resolve().parents[2] / ".gitignore"
    assert ".env" in gitignore.read_text(encoding="utf-8").splitlines()
