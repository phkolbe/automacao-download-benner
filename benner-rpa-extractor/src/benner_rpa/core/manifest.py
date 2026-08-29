"""G11 — atomicidade: a pasta final só existe se o manifest for válido.

O desenho: baixa em `_work/<processo>.tmp/`, gera o manifest, valida, e só então
renomeia para o destino. Interrupção em qualquer ponto deixa um `.tmp` (que o
reconciliador limpa) e o processo volta a PENDENTE.

É isso que torna barato pular o que já foi baixado: a existência da pasta final é,
por construção, prova de que o pacote está completo.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .zip_seguro import validar_zip

NOME_MANIFEST = "_manifest.json"
SUFIXO_TMP = ".tmp"

_TAMANHO_BLOCO = 1024 * 1024


def sha256_arquivo(caminho: Path) -> str:
    """Hash em blocos — o ZIP tem 131 MB, ler tudo na memória é desnecessário."""
    h = hashlib.sha256()
    with Path(caminho).open("rb") as fh:
        for bloco in iter(lambda: fh.read(_TAMANHO_BLOCO), b""):
            h.update(bloco)
    return h.hexdigest()


def agora_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


@dataclass
class Artefato:
    nome: str
    bytes: int
    sha256: str
    origem: str
    zip: dict | None = None


@dataclass
class Manifest:
    processo_planilha: str
    processo_normalizado: str
    pasta_benner: str = ""
    numero_conferido_na_tela: str = ""
    concluido_em: str = field(default_factory=agora_iso)
    selecao: dict = field(default_factory=dict)
    artefatos: list[Artefato] = field(default_factory=list)
    documentos_listados_na_popup: list[dict] = field(default_factory=list)
    completo: bool = False

    def como_dict(self) -> dict:
        d = asdict(self)
        d["artefatos"] = [
            {k: v for k, v in a.items() if v is not None} for a in d["artefatos"]
        ]
        return d

    def gravar(self, pasta: Path) -> Path:
        destino = Path(pasta) / NOME_MANIFEST
        destino.write_text(
            json.dumps(self.como_dict(), indent=1, ensure_ascii=False), encoding="utf-8"
        )
        return destino


def registrar_artefato(caminho: Path, origem: str, *, validar_como_zip: bool = False) -> Artefato:
    caminho = Path(caminho)
    art = Artefato(
        nome=caminho.name,
        bytes=caminho.stat().st_size,
        sha256=sha256_arquivo(caminho),
        origem=origem,
    )
    if validar_como_zip:
        art.zip = validar_zip(caminho).como_dict()
    return art


def carregar_manifest(pasta: Path) -> dict | None:
    caminho = Path(pasta) / NOME_MANIFEST
    if not caminho.exists():
        return None
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def manifest_valido(pasta: Path) -> tuple[bool, str]:
    """A pasta bate com o manifest que ela mesma declara?

    Confere existência, tamanho e hash de cada artefato. É o que roda na reexecução
    para decidir se pula o processo — e o que impede um `CONCLUIDO` mentiroso quando
    alguém apaga um arquivo da pasta.
    """
    pasta = Path(pasta)
    dados = carregar_manifest(pasta)

    if dados is None:
        return False, "manifest ausente ou ilegivel"
    if not dados.get("completo"):
        return False, "manifest marcado como incompleto"

    artefatos = dados.get("artefatos") or []
    if not artefatos:
        return False, "manifest sem artefatos"

    for art in artefatos:
        alvo = pasta / art["nome"]
        if not alvo.exists():
            return False, f"artefato ausente no disco: {art['nome']}"
        if alvo.stat().st_size != art["bytes"]:
            return False, (
                f"tamanho divergente em {art['nome']}: "
                f"disco={alvo.stat().st_size} manifest={art['bytes']}"
            )
        if sha256_arquivo(alvo) != art["sha256"]:
            return False, f"sha256 divergente em {art['nome']}"

    return True, "ok"


def pasta_trabalho(raiz_work: Path, nome_pasta: str, *, limpar: bool = True) -> Path:
    """Cria a pasta temporária deste processo.

    `limpar=False` PRESERVA o que já foi baixado. É o que dá sentido ao estado
    PARCIAL: sem isso, retentar por causa de um XLSX de 3 KB rebaixa também o ZIP de
    131 MB — exatamente o desperdício que PARCIAL existe para evitar (§6).
    """
    tmp = Path(raiz_work) / f"{nome_pasta}{SUFIXO_TMP}"
    if tmp.exists() and limpar:
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True, exist_ok=True)
    return tmp


def promover(tmp: Path, destino: Path) -> Path:
    """Renomeia a `.tmp` para o destino final — o passo que torna a pasta 'real'.

    Recusa promover sem manifest válido (G11) e recusa sobrescrever destino
    existente: colisão é sinalizada, nunca resolvida em silêncio.
    """
    tmp, destino = Path(tmp), Path(destino)

    ok, motivo = manifest_valido(tmp)
    if not ok:
        raise RuntimeError(f"G11: promocao negada, manifest invalido em {tmp.name}: {motivo}")

    if destino.exists():
        raise FileExistsError(f"destino ja existe, colisao nao resolvida: {destino}")

    destino.parent.mkdir(parents=True, exist_ok=True)
    os.replace(tmp, destino)
    return destino


def limpar_tmp_orfas(raiz_work: Path) -> list[str]:
    """Remove `.tmp` deixadas por interrupção. Devolve o que foi limpo."""
    raiz = Path(raiz_work)
    if not raiz.exists():
        return []

    limpas = []
    for item in raiz.iterdir():
        if item.is_dir() and item.name.endswith(SUFIXO_TMP):
            shutil.rmtree(item, ignore_errors=True)
            limpas.append(item.name)
    return limpas
