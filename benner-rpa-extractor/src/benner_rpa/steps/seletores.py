"""Carrega `selectors/benner.json` e transforma entradas em localizadores Playwright.

O mapa é dado, não código. Este módulo é o único lugar que sabe traduzir uma entrada
do JSON em um `Locator` — o que faz com que os gates possam ser impostos aqui, uma vez,
em vez de em cada passo.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

RAIZ_PROJETO = Path(__file__).resolve().parents[3]
CAMINHO_PADRAO = RAIZ_PROJETO / "selectors" / "benner.json"


class SeletorProibido(RuntimeError):
    """G1/G12 — tentativa de localizar de um jeito que o mapa proíbe."""


class SeletorNaoDeterminado(RuntimeError):
    """G12 — a entrada está marcada TODO; nenhum seletor foi inventado."""


# Estratégias que localizam por posição. Nenhuma delas é aceitável (G1).
_PROIBIDAS = re.compile(r"(?i)\b(nth|first|last|eq\(|indice|index|coordenada|position)\b")

# Pseudo-seletores CSS que também são posição disfarçada.
_POSICIONAL_CSS = re.compile(
    r"(?i):(nth-child|nth-of-type|nth-last-child|nth-last-of-type|first-child|"
    r"last-child|first-of-type|last-of-type|only-child)\b"
)


class MapaSeletores:
    def __init__(self, dados: dict) -> None:
        self._d = dados

    @classmethod
    def carregar(cls, caminho: Path | None = None) -> MapaSeletores:
        alvo = Path(caminho) if caminho else CAMINHO_PADRAO
        return cls(json.loads(alvo.read_text(encoding="utf-8")))

    # ---------------------------------------------------------------- acesso

    def entrada(self, caminho: str) -> dict[str, Any]:
        """`popup_documentos.link_selecionar_restantes` → o dict daquela entrada."""
        no: Any = self._d
        for parte in caminho.split("."):
            if not isinstance(no, dict) or parte not in no:
                raise KeyError(f"entrada ausente no mapa: {caminho}")
            no = no[parte]

        if not isinstance(no, dict):
            raise KeyError(f"{caminho} nao e uma entrada de seletor")

        if no.get("estrategia") == "TODO":
            raise SeletorNaoDeterminado(
                f"G12: {caminho} esta marcado TODO — {no.get('motivo', 'sem motivo registrado')}"
            )
        return no

    def todos_os_todos(self) -> list[str]:
        """Todas as entradas TODO, para o relatório exigido pelo G12."""
        achados: list[str] = []

        def andar(no: Any, prefixo: str) -> None:
            if isinstance(no, dict):
                if no.get("estrategia") == "TODO":
                    achados.append(prefixo)
                    return
                for k, v in no.items():
                    if not k.startswith("_"):
                        andar(v, f"{prefixo}.{k}" if prefixo else k)

        andar(self._d, "")
        return sorted(achados)

    def itens_proibidos_do_menu(self) -> list[str]:
        return list(self._d["menu_acoes"]["itens_proibidos"])

    # ---------------------------------------------------------------- localizar

    def localizar(self, escopo, caminho: str, *, nome: str | None = None):
        """Devolve o `Locator` da entrada, aplicando o modo de match declarado.

        `escopo` é uma Page ou um Locator — é assim que `escopo` do JSON vira
        realidade: quem chama passa o container certo.
        """
        e = self.entrada(caminho)
        estrategia = e["estrategia"]

        if _PROIBIDAS.search(estrategia):
            raise SeletorProibido(f"G1: estrategia por posicao em {caminho}: {estrategia!r}")

        alvo_nome = nome if nome is not None else e.get("nome")
        exato = e.get("modo") == "exato"

        if estrategia.startswith("role="):
            papel = estrategia.split("=", 1)[1]
            if alvo_nome is None:
                return escopo.get_by_role(papel)
            return escopo.get_by_role(papel, name=alvo_nome, exact=exato)

        if estrategia == "placeholder":
            # Quando o campo não tem <label>, o placeholder É o nome acessível.
            # É o caso da tela de login do Benner.
            return escopo.get_by_placeholder(alvo_nome, exact=exato)

        if estrategia in ("css", "css_com_texto_exato", "irmaos_ate_proximo_cabecalho"):
            # Onde o app não expõe ARIA nenhum — o painel de busca é assim — a classe
            # semântica é o que sobra. `_PROIBIDAS` acima já barrou nth/eq/posição, que
            # é o que o G1 de fato proíbe.
            css = e["valor"]
            if _POSICIONAL_CSS.search(css):
                raise SeletorProibido(f"G1: seletor CSS posicional em {caminho}: {css!r}")

            base = escopo.locator(css)
            if estrategia == "css_com_texto_exato":
                import re as _re

                return base.filter(
                    has_text=_re.compile(rf"^\s*{_re.escape(alvo_nome)}\s*$")
                )
            return base

        if estrategia == "teclado":
            raise SeletorProibido(f"{caminho} e um atalho de teclado, nao um localizador")

        raise SeletorProibido(f"estrategia nao suportada em {caminho}: {estrategia!r}")


def acionar(locator, *, timeout_ms: int = 6000) -> str:
    """Clica; se algum elemento cobrir o alvo, dispara o próprio `onclick` dele.

    Este sistema empilha células, cabeçalhos e modais animados por cima dos controles,
    e o clique do Playwright faz teste de sobreposição — o que rende timeouts de 30s
    em elementos que estão perfeitamente visíveis e funcionais.

    `dispatch_event("click")` executa o handler que a própria aplicação registrou. É
    diferente de forjar estado (setar `checked`, chamar postback direto): aqui quem
    decide o que acontece continua sendo o Benner.

    O timeout é curto de propósito — falhar rápido e cair no despacho é melhor que
    esperar meio minuto.
    """
    try:
        locator.click(timeout=timeout_ms)
        return "click"
    except Exception:
        # ATENCAO: para <a href="javascript:...">, o evento sintetico NAO dispara a
        # acao padrao do navegador — o handler so roda se estiver em `onclick`. Nesses
        # casos o despacho e silenciosamente inocuo, e quem chama precisa VERIFICAR o
        # efeito em vez de confiar no retorno.
        locator.dispatch_event("click")
        return "dispatch"


def exigir_texto_exato(locator, esperado: str, contexto: str) -> None:
    """G1 — confere o texto ANTES de acionar.

    O gate manda verificar o texto antes de clicar em item de menu. Localizar por
    nome acessível exato já garante isso na maioria dos casos, mas a verificação
    explícita cobre o caso em que o mapa foi editado errado.
    """
    visto = (locator.inner_text() or "").strip()
    if visto != esperado.strip():
        raise SeletorProibido(
            f"G1: {contexto} — texto do elemento e {visto!r}, esperado {esperado!r}. "
            "Nada foi acionado."
        )
