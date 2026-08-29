"""Ledger append-only em JSONL (§8.3) e reconciliação com o disco.

Append-only porque o ledger é a trilha de auditoria: uma linha escrita nunca é
editada nem apagada. O estado atual de um processo é a ÚLTIMA linha dele — o que
torna a reconstrução barata e a história completa.

Toda escrita passa por `limpar_estrutura` (G5): nenhuma credencial entra aqui.
"""

from __future__ import annotations

import json
from pathlib import Path

from .estados import Estado
from .manifest import agora_iso, manifest_valido
from .segredos import limpar_estrutura


class Ledger:
    def __init__(self, caminho: Path) -> None:
        self.caminho = Path(caminho)
        self.caminho.parent.mkdir(parents=True, exist_ok=True)

    def registrar(self, evento: dict) -> dict:
        """Anexa um evento. Devolve o que foi de fato gravado (já redigido)."""
        linha = {"ts": agora_iso(), **evento}
        limpa = limpar_estrutura(linha)
        with self.caminho.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(limpa, ensure_ascii=False) + "\n")
        return limpa

    def eventos(self) -> list[dict]:
        """Lê tudo, ignorando linhas corrompidas por interrupção no meio da escrita."""
        if not self.caminho.exists():
            return []

        out = []
        for linha in self.caminho.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if not linha:
                continue
            try:
                out.append(json.loads(linha))
            except json.JSONDecodeError:
                continue  # linha truncada por queda — o append-only tolera
        return out

    def estado_atual(self) -> dict[str, dict]:
        """Último evento de cada processo, indexado pelo número normalizado."""
        atual: dict[str, dict] = {}
        for ev in self.eventos():
            chave = ev.get("processo_normalizado") or ev.get("processo")
            if chave:
                atual[chave] = ev
        return atual


def reconciliar(ledger: Ledger, raiz_saida: Path) -> list[dict]:
    """Confronta o que o ledger afirma com o que o disco mostra.

    Duas correções, ambas de segurança:
      - `EM_ANDAMENTO` sobrevivente é queda de sessão → volta a `PENDENTE`.
      - `CONCLUIDO` cujo manifest não valida → volta a `EM_ANDAMENTO` para refazer.

    Devolve as correções aplicadas, e as grava no próprio ledger — a reconciliação
    também é auditável.
    """
    raiz = Path(raiz_saida)
    correcoes: list[dict] = []

    for chave, ev in ledger.estado_atual().items():
        estado = ev.get("status")
        pasta_nome = ev.get("pasta_destino")

        if estado == Estado.EM_ANDAMENTO.value:
            correcoes.append({
                "processo": ev.get("processo"),
                "processo_normalizado": chave,
                "status": Estado.PENDENTE.value,
                "motivo": "EM_ANDAMENTO orfao — sessao interrompida",
                "origem": "reconciliacao",
            })
            continue

        if estado == Estado.CONCLUIDO.value and pasta_nome:
            pasta = raiz / pasta_nome
            ok, motivo = manifest_valido(pasta)
            if not ok:
                correcoes.append({
                    "processo": ev.get("processo"),
                    "processo_normalizado": chave,
                    "status": Estado.EM_ANDAMENTO.value,
                    "motivo": f"CONCLUIDO sem lastro no disco: {motivo}",
                    "origem": "reconciliacao",
                })

    for c in correcoes:
        ledger.registrar(c)

    return correcoes
