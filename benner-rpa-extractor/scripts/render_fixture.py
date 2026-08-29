"""Renderiza uma fixture HTML e screenshota no viewport EXATO do print real.

Mesmo tamanho dos dois lados é pré-requisito do teste cego: se as imagens tiverem
dimensões diferentes, o crítico acerta pela moldura e não pelo conteúdo.

Uso:
    python scripts/render_fixture.py <fixture.html> <print_real.png> <saida.png>
"""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright
from PIL import Image


def render(fixture: Path, referencia: Path, saida: Path) -> tuple[int, int]:
    largura, altura = Image.open(referencia).size

    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        pagina = navegador.new_page(viewport={"width": largura, "height": altura})
        pagina.goto(fixture.resolve().as_uri())
        pagina.wait_for_load_state("networkidle")
        saida.parent.mkdir(parents=True, exist_ok=True)
        pagina.screenshot(path=str(saida))
        navegador.close()

    return largura, altura


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__, file=sys.stderr)
        return 2

    fixture, referencia, saida = (Path(a) for a in sys.argv[1:4])
    for caminho in (fixture, referencia):
        if not caminho.exists():
            print(f"nao encontrado: {caminho}", file=sys.stderr)
            return 1

    largura, altura = render(fixture, referencia, saida)
    print(f"{saida}  {largura}x{altura}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
