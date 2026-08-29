"""G7 — validação de ZIP sem NUNCA extrair.

Só o índice central e os bytes mágicos. Nada é escrito no disco: `namelist()` e
`testzip()` leem o arquivo, não o expandem.

O motivo de existir mais que "o arquivo existe": servidores devolvem página de erro
HTML com nome `.zip`. Um HTML de 4 KB passa por qualquer checagem de existência e
falha nos bytes mágicos.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from pathlib import Path

ASSINATURA_ZIP = b"PK\x03\x04"

# Um ZIP vazio legítimo começa com a assinatura de "end of central directory".
ASSINATURA_ZIP_VAZIO = b"PK\x05\x06"

# Abaixo disto não é um pacote de documentos — é página de erro ou download truncado.
BYTES_MINIMOS = 1024


@dataclass
class ResultadoZip:
    valido: bool
    caminho: Path
    bytes: int = 0
    entradas: int = 0
    nomes: list[str] = field(default_factory=list)
    motivo: str = ""

    def como_dict(self) -> dict:
        return {
            "valido": self.valido,
            "bytes": self.bytes,
            "entradas": self.entradas,
            "motivo": self.motivo,
        }


def validar_zip(caminho: Path, *, minimo_bytes: int = BYTES_MINIMOS) -> ResultadoZip:
    """Valida um ZIP lendo apenas cabeçalho e índice central. Nunca extrai."""
    caminho = Path(caminho)

    if not caminho.exists():
        return ResultadoZip(False, caminho, motivo="arquivo nao existe")

    tamanho = caminho.stat().st_size
    if tamanho == 0:
        return ResultadoZip(False, caminho, bytes=0, motivo="arquivo vazio")

    with caminho.open("rb") as fh:
        cabecalho = fh.read(4)

    if cabecalho == ASSINATURA_ZIP_VAZIO:
        # ZIP legítimo sem entradas. Deixa passar como válido com 0 entradas; quem
        # decide se zero é aceitável é a regra de negócio, não a validação.
        return ResultadoZip(True, caminho, bytes=tamanho, entradas=0, motivo="zip vazio")

    if cabecalho != ASSINATURA_ZIP:
        return ResultadoZip(
            False, caminho, bytes=tamanho,
            motivo=f"bytes magicos {cabecalho!r} != {ASSINATURA_ZIP!r} "
                   "(provavel pagina de erro HTML com nome .zip)",
        )

    if tamanho < minimo_bytes:
        return ResultadoZip(
            False, caminho, bytes=tamanho,
            motivo=f"{tamanho} bytes abaixo do minimo {minimo_bytes}",
        )

    try:
        with zipfile.ZipFile(caminho) as z:
            nomes = z.namelist()      # só o índice central
            corrompida = z.testzip()  # None = íntegro; nada é escrito no disco
    except zipfile.BadZipFile as erro:
        return ResultadoZip(False, caminho, bytes=tamanho, motivo=f"zip invalido: {erro}")

    if corrompida is not None:
        return ResultadoZip(
            False, caminho, bytes=tamanho, entradas=len(nomes), nomes=nomes,
            motivo=f"entrada corrompida: {corrompida}",
        )

    return ResultadoZip(True, caminho, bytes=tamanho, entradas=len(nomes), nomes=nomes)


def conferir_contagem(
    resultado: ResultadoZip, docs_listados_popup: int
) -> tuple[bool, str]:
    """G2 — a prova final de que a seleção completa funcionou.

    Se a popup listou 93 documentos e o ZIP tem 10 entradas, o link
    "Selecionar todos os restantes?" não foi acionado e o pacote está incompleto.
    """
    if not resultado.valido:
        return False, f"zip invalido: {resultado.motivo}"

    if resultado.entradas != docs_listados_popup:
        return False, (
            f"entradas_no_zip={resultado.entradas} != "
            f"docs_listados_popup={docs_listados_popup} — pacote incompleto (G2)"
        )

    return True, "ok"
