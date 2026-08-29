"""Pré-voo de disco (H18).

O ZIP de referência tem 131 MB para um processo. 333 processos ≈ 44 GB — ordem de
grandeza, não previsão. A defesa é medir a média real antes do lote e barrar a
execução se o espaço livre não cobrir a estimativa com margem.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

# Só para referência humana no relatório; a estimativa usada é sempre a medida.
MEDIA_OBSERVADA_BYTES = 131_059_962


class EspacoInsuficiente(RuntimeError):
    pass


@dataclass
class Estimativa:
    pendentes: int
    media_bytes: int
    margem: float
    livre_bytes: int

    @property
    def necessario_bytes(self) -> int:
        return int(self.pendentes * self.media_bytes * self.margem)

    @property
    def suficiente(self) -> bool:
        return self.livre_bytes >= self.necessario_bytes

    def resumo(self) -> str:
        return (
            f"{self.pendentes} pendentes × {humanizar(self.media_bytes)} × {self.margem} "
            f"= {humanizar(self.necessario_bytes)} necessários; "
            f"{humanizar(self.livre_bytes)} livres"
        )


def humanizar(n: int) -> str:
    for unidade in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unidade == "TB":
            return f"{n:.1f} {unidade}" if unidade != "B" else f"{n} B"
        n /= 1024
    return f"{n:.1f} TB"


def espaco_livre(caminho: Path) -> int:
    """Bytes livres no volume que contém `caminho` (ou o ancestral existente)."""
    alvo = Path(caminho)
    while not alvo.exists() and alvo != alvo.parent:
        alvo = alvo.parent
    return shutil.disk_usage(alvo).free


def estimar(
    raiz_saida: Path, pendentes: int, *, media_bytes: int, margem: float = 1.5
) -> Estimativa:
    return Estimativa(
        pendentes=pendentes,
        media_bytes=media_bytes,
        margem=margem,
        livre_bytes=espaco_livre(raiz_saida),
    )


def exigir_espaco(estimativa: Estimativa) -> None:
    """Barra o lote ANTES de começar, não no meio (H18)."""
    if not estimativa.suficiente:
        raise EspacoInsuficiente(f"H18: espaço insuficiente. {estimativa.resumo()}")


def media_medida(raiz_saida: Path) -> int | None:
    """Média real dos ZIPs que O ROBÔ baixou. `None` enquanto não houver amostra.

    É o que substitui a extrapolação de 44 GB por um número medido, assim que o
    pré-voo ou os primeiros processos do lote produzirem amostra.

    Só conta pasta com `_manifest.json` — o que exclui a pasta de referência, que é
    trabalho humano. Ela é uma amostra de um processo real, mas chamá-la de "medida"
    seria apresentar como resultado nosso um número que não medimos.
    """
    raiz = Path(raiz_saida)
    if not raiz.exists():
        return None

    tamanhos = [
        z.stat().st_size
        for pasta in raiz.iterdir()
        if pasta.is_dir()
        and not pasta.name.startswith("_")
        and (pasta / "_manifest.json").exists()
        for z in pasta.glob("*.zip")
    ]
    return sum(tamanhos) // len(tamanhos) if tamanhos else None
