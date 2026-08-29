"""Monta o par cego para o crítico: duas imagens, rótulos removidos.

Copia o print real e o render da fixture para `A.png` e `B.png` numa pasta de rodada,
alternando qual é qual conforme a paridade da rodada — o crítico não pode aprender que
"A é sempre a real". Grava o gabarito num arquivo separado que o crítico não recebe.

Uso:
    python scripts/blind_pair.py <print_real.png> <render_fixture.png> <pasta_rodada> <n_rodada>
"""

import json
import shutil
import sys
from pathlib import Path


def montar(real: Path, nosso: Path, destino: Path, rodada: int) -> dict:
    destino.mkdir(parents=True, exist_ok=True)

    # Paridade da rodada decide a atribuição — determinístico e auditável,
    # mas alternando a cada iteração do loop.
    real_eh_a = rodada % 2 == 0
    shutil.copy2(real if real_eh_a else nosso, destino / "A.png")
    shutil.copy2(nosso if real_eh_a else real, destino / "B.png")

    gabarito = {
        "rodada": rodada,
        "A": "real" if real_eh_a else "nosso",
        "B": "nosso" if real_eh_a else "real",
        "print_real": str(real),
        "render_nosso": str(nosso),
    }
    # Fora da pasta do par, para não vazar para quem lista o diretório do crítico.
    (destino.parent / f"gabarito-rodada-{rodada}.json").write_text(
        json.dumps(gabarito, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return gabarito


def main() -> int:
    if len(sys.argv) != 5:
        print(__doc__, file=sys.stderr)
        return 2

    real, nosso, destino = (Path(a) for a in sys.argv[1:4])
    rodada = int(sys.argv[4])

    for caminho in (real, nosso):
        if not caminho.exists():
            print(f"nao encontrado: {caminho}", file=sys.stderr)
            return 1

    montar(real, nosso, destino, rodada)
    # Só o caminho do par vai para stdout. O gabarito nunca.
    print(destino / "A.png")
    print(destino / "B.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
