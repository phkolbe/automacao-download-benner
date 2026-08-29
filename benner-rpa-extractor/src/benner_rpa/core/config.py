"""Carregamento de `config.yaml` + `.env`.

Único ponto do sistema que lê credencial. Registra os segredos em `segredos` no
mesmo ato de carregá-los (G5), para que nada possa vazar antes do registro.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

from .segredos import registrar_segredo

RAIZ_PROJETO = Path(__file__).resolve().parents[3]

_INTERPOLACAO = re.compile(r"\$\{(\w+)\}")


class ConfiguracaoInvalida(RuntimeError):
    pass


class AcessoRealNaoAutorizado(RuntimeError):
    """G10 — tentativa de tocar o Benner real sem autorização humana explícita."""


@dataclass(frozen=True)
class Credenciais:
    url: str
    usuario: str
    senha: str = field(repr=False)

    def __str__(self) -> str:      # nunca imprime a senha, nem por acidente
        return f"Credenciais(url={self.url}, usuario={self.usuario}, senha=***)"


@dataclass
class Config:
    benner: dict
    saida: dict
    planilha: dict
    lote: dict
    gates: dict
    _bruto: dict = field(default_factory=dict, repr=False)

    # ---- caminhos ----
    @property
    def raiz_saida(self) -> Path:
        return Path(self.saida["raiz"])

    @property
    def raiz_work(self) -> Path:
        return self.raiz_saida / "_work"

    @property
    def raiz_logs(self) -> Path:
        return self.raiz_saida / "_logs"

    @property
    def caminho_ledger(self) -> Path:
        return self.raiz_logs / "ledger.jsonl"

    @property
    def caminho_controle(self) -> Path:
        return self.raiz_saida / "planilha_controle.xlsx"

    @property
    def pasta_referencia(self) -> Path | None:
        """A pasta montada à mão, achada por padrão de nome (G9).

        Localizada em vez de fixada: gravar o número de um processo real num arquivo
        versionado publicaria dado pessoal de terceiro.
        """
        padrao = self.saida.get("padrao_pasta_referencia", "* - exemplo")
        achadas = sorted(self.raiz_saida.glob(padrao)) if self.raiz_saida.exists() else []
        return achadas[0] if achadas else None

    @property
    def caminho_planilha(self) -> Path:
        return Path(self.planilha["caminho"])

    # ---- gates ----
    @property
    def acesso_real_autorizado(self) -> bool:
        return bool(self.gates.get("acesso_real_autorizado", False))

    def exigir_autorizacao_de_acesso(self, o_que: str) -> None:
        """G10 — chamado por todo código que abriria uma conexão com o Benner."""
        if not self.acesso_real_autorizado:
            raise AcessoRealNaoAutorizado(
                f"G10: {o_que} exige acesso real ao Benner.\n"
                "Nenhum acesso e permitido sem autorizacao humana explicita.\n"
                "Para autorizar: config.yaml -> gates.acesso_real_autorizado: true"
            )


def _interpolar(valor, ambiente: dict) -> object:
    """Resolve `${VAR}` recursivamente contra o ambiente."""
    if isinstance(valor, str):
        def troca(m):
            nome = m.group(1)
            if nome not in ambiente:
                raise ConfiguracaoInvalida(f"variavel de ambiente ausente: {nome}")
            return ambiente[nome]
        return _INTERPOLACAO.sub(troca, valor)
    if isinstance(valor, dict):
        return {k: _interpolar(v, ambiente) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_interpolar(v, ambiente) for v in valor]
    return valor


def carregar_credenciais(caminho_env: Path | None = None) -> Credenciais:
    """Lê o `.env` e registra os segredos. Chamar antes de qualquer log."""
    env = Path(caminho_env) if caminho_env else RAIZ_PROJETO / ".env"
    load_dotenv(env, override=False)

    url = os.getenv("BENNER_URL", "").strip()
    usuario = os.getenv("BENNER_USER", "").strip()
    senha = os.getenv("BENNER_PASSWORD", "").strip()

    faltando = [n for n, v in
                [("BENNER_URL", url), ("BENNER_USER", usuario), ("BENNER_PASSWORD", senha)]
                if not v]
    if faltando:
        raise ConfiguracaoInvalida(
            f"credenciais ausentes no .env: {', '.join(faltando)} (esperado em {env})"
        )

    # G5 — a partir daqui qualquer saída que os contenha é redigida.
    registrar_segredo(usuario)
    registrar_segredo(senha)

    return Credenciais(url=url, usuario=usuario, senha=senha)


def carregar_config(caminho: Path | None = None, *, com_credenciais: bool = False) -> Config:
    """Carrega `config.yaml`.

    `com_credenciais=False` é o padrão: quase tudo (normalização, ledger, manifest,
    testes) não precisa de credencial, e não pedir é a forma mais barata de não vazar.
    """
    alvo = Path(caminho) if caminho else RAIZ_PROJETO / "config.yaml"
    if not alvo.exists():
        raise ConfiguracaoInvalida(f"config.yaml nao encontrado em {alvo}")

    bruto = yaml.safe_load(alvo.read_text(encoding="utf-8")) or {}

    ambiente = dict(os.environ)
    if com_credenciais:
        cred = carregar_credenciais()
        ambiente.setdefault("BENNER_URL", cred.url)
    else:
        # Sem credenciais, `${BENNER_URL}` resolve para vazio em vez de explodir:
        # o código offline nunca usa a URL.
        ambiente.setdefault("BENNER_URL", "")

    dados = _interpolar(bruto, ambiente)

    for chave in ("benner", "saida", "planilha", "lote"):
        if chave not in dados:
            raise ConfiguracaoInvalida(f"secao ausente em config.yaml: {chave}")

    return Config(
        benner=dados["benner"],
        saida=dados["saida"],
        planilha=dados["planilha"],
        lote=dados["lote"],
        gates=dados.get("gates", {}),
        _bruto=dados,
    )
