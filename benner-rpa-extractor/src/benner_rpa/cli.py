"""CLI do robô.

Todo comando que tocaria o Benner passa por `exigir_autorizacao_de_acesso` (G10),
então os comandos offline — `auditar`, `verificar` — rodam sempre, e `pre-voo` e
`lote` param com uma mensagem que diz como autorizar.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .core.config import AcessoRealNaoAutorizado, carregar_config
from .core.disco import MEDIA_OBSERVADA_BYTES, estimar, humanizar, media_medida
from .core.ledger import Ledger, reconciliar
from .core.manifest import limpar_tmp_orfas, manifest_valido
from .core.planilha import auditar_entrada, ler_processos


def _processos(cfg):
    return ler_processos(
        cfg.caminho_planilha,
        cfg.planilha["aba"],
        cfg.planilha["deteccao_coluna"],
    )


def cmd_auditar(cfg, _args) -> int:
    """Lê a planilha e reporta. Nenhum acesso ao Benner."""
    processos = _processos(cfg)
    a = auditar_entrada(processos)

    print(f"planilha : {cfg.caminho_planilha}")
    print(f"aba      : {cfg.planilha['aba']}")
    print(f"processos: {a['total']} ({a['distintos']} distintos)")
    print()
    print(f"coluna '{cfg.planilha.get('coluna_controle_humano', 'Benner OK')}' (mantida a mao):")
    for marca, n in sorted(a["por_marca_benner"].items()):
        rotulo = {"1": "concluido manualmente", "98": "so Processos (Pastas)",
                  "99": "nao encontrado", "pendente": "A PROCESSAR"}.get(marca, "?")
        print(f"   {marca:>9s} : {n:4d}  {rotulo}")
    print(f"   {'':>9s}   ----")
    print(f"   {'restam':>9s} : {a['pendentes']:4d}  processos para o robo")

    for m in a["marca_desconhecida"]:
        print(f"  ! linha {m['linha']}: valor {m['valor']!r} fora do dominio "
              f"({m['processo']}) — sera BLOQUEADO ate esclarecimento")
    print()
    print(f"duplicados          : {len(a['duplicados'])}")
    print(f"colisoes de pasta   : {len(a['colisoes_de_pasta'])}")
    print(f"fora do formato CNJ : {len(a['fora_do_formato_cnj'])}")

    for chave, linhas in a["duplicados"].items():
        print(f"  ! duplicado {chave} nas linhas {linhas}")
    for item in a["fora_do_formato_cnj"]:
        print(f"  ! linha {item['linha']}: {item['valor']!r}")

    from .core.planilha import comparar_com_registro
    ok_sha, msg_sha = comparar_com_registro(
        cfg.caminho_planilha, cfg.planilha.get("sha256_registrado"))
    print(("hash: " if ok_sha else "hash: AVISO — ") + msg_sha)
    print()

    media = media_medida(cfg.raiz_saida) or MEDIA_OBSERVADA_BYTES
    origem = "medida" if media_medida(cfg.raiz_saida) else "observada na referencia"
    # A estimativa vale para o que FALTA, não para os 333.
    est = estimar(cfg.raiz_saida, a["pendentes"], media_bytes=media,
                  margem=cfg.lote["margem_disco"])
    print(f"\ndisco ({origem}): {est.resumo()}")
    print("       suficiente" if est.suficiente else "       INSUFICIENTE")

    return 0


def cmd_verificar(cfg, _args) -> int:
    """Confere o que está no disco contra o ledger. Nenhum acesso ao Benner."""
    ledger = Ledger(cfg.caminho_ledger)

    limpas = limpar_tmp_orfas(cfg.raiz_work)
    for nome in limpas:
        print(f"limpa .tmp orfa: {nome}")

    correcoes = reconciliar(ledger, cfg.raiz_saida)
    for c in correcoes:
        print(f"corrigido {c['processo']}: -> {c['status']} ({c['motivo']})")

    ok = quebrados = 0
    for pasta in sorted(cfg.raiz_saida.glob("*")):
        if not pasta.is_dir() or pasta.name.startswith("_") or pasta.name.endswith(" - exemplo"):
            continue
        valido, motivo = manifest_valido(pasta)
        if valido:
            ok += 1
        else:
            quebrados += 1
            print(f"  ! {pasta.name}: {motivo}")

    print(f"\npastas integras: {ok}   quebradas: {quebrados}   correcoes: {len(correcoes)}")
    return 1 if quebrados else 0


def _selecionar(cfg, args):
    """Aplica `--processo`, que é como o G10 quer o primeiro acesso: um só."""
    processos = _processos(cfg)

    if not args.processo:
        return processos

    from .core.normalizacao import normalizar_processo

    alvo = normalizar_processo(args.processo)
    escolhidos = [p for p in processos if p.normalizado == alvo]

    if not escolhidos:
        raise SystemExit(f"processo {args.processo!r} nao esta na planilha")
    return escolhidos


def cmd_lote(cfg, args) -> int:
    """Executa o lote (ou um processo com `--processo`). Exige autorização (G10)."""
    from .core.config import carregar_credenciais
    from .core.ledger import Ledger
    from .core.lote import Orquestrador
    from .core.relatorio import compor, gravar
    from .steps.extrator import ExtratorBenner

    processos = _selecionar(cfg, args)
    escopo = f"1 processo ({processos[0].numero})" if len(processos) == 1 \
        else f"lote de {len(processos)} processos"
    cfg.exigir_autorizacao_de_acesso(f"execucao de {escopo}")

    # G6 — o hash de AGORA. Conferido no fim: se mudou, foi o robô.
    from .core.planilha import conferir_integridade, sha256_planilha
    sha_inicio = sha256_planilha(cfg.caminho_planilha)

    credenciais = carregar_credenciais()
    extrator = ExtratorBenner(cfg=cfg, credenciais=credenciais, headless=not args.visivel)

    print(f"executando {escopo}")
    print(f"saida: {cfg.raiz_saida}\n")

    with extrator:
        orq = Orquestrador(
            extrator=extrator,
            raiz_saida=cfg.raiz_saida,
            ledger=Ledger(cfg.caminho_ledger),
            throttle_s=cfg.lote["throttle_s"],
            max_tentativas=cfg.lote["max_tentativas"],
            limite_por_execucao=(
                args.limite if args.limite is not None
                else (None if args.processo else cfg.lote["limite_por_execucao"])
            ),
            margem_disco=cfg.lote["margem_disco"],
            forcar=args.forcar,
        )
        resultados = orq.executar(processos)

    if not resultados:
        # `all([])` é True — um lote vazio jamais pode sair como sucesso.
        print("NADA FOI PROCESSADO.")
        print("Os processos pedidos ja estao em estado terminal no ledger")
        print("(CONCLUIDO integro, NAO_ENCONTRADO, AMBIGUO ou BLOQUEADO).")
        print("Para reprocessar assim mesmo: --forcar")
        return 3

    for r in resultados:
        marca = "ok" if r.status.value == "CONCLUIDO" else "!!"
        tempo = f"  [{humanizar_duracao(r.duracao_s)}]" if r.duracao_s else ""
        print(f"  {marca} {r.processo.numero}  {r.status.value}{tempo}  {r.observacao}")

    # Tempo de PAREDE do lote: inclui login, throttle e retentativas. É maior que a
    # soma dos processos, e é ele que responde "quanto tempo vai levar".
    parede = _time.monotonic() - inicio_lote
    print()
    print(f"tempo total da execucao: {humanizar_duracao(parede)}  "
          f"({len(resultados)} processos)")

    # G6 — o original tem que estar intacto ao fim da execução.
    conferir_integridade(cfg.caminho_planilha, sha_inicio)

    destino = gravar(
        compor(resultados, total_na_planilha=len(_processos(cfg)),
               raiz_saida=cfg.raiz_saida,
               pendencias=["'Exportar para Excel' respeita a paginacao? — conferir "
                           "linhas_na_tela contra as linhas do XLSX"]),
        cfg.raiz_saida / "relatorio_lote.md",
    )
    print(f"\nrelatorio: {destino}")

    return 0 if all(r.status.value == "CONCLUIDO" for r in resultados) else 1


def cmd_pre_voo(cfg, args) -> int:
    """Navega e abre a popup, sem baixar. Exige autorização (G10)."""
    cfg.exigir_autorizacao_de_acesso("pre-voo (navega no Benner sem baixar)")
    print("pre-voo ainda nao implementado — use `lote --processo` para um processo unico")
    return 2


COMANDOS = {
    "auditar": (cmd_auditar, "lê a planilha e reporta duplicidade, formato e disco"),
    "verificar": (cmd_verificar, "confere disco × ledger e limpa .tmp órfãs"),
    "pre-voo": (cmd_pre_voo, "navega sem baixar — exige autorização G10"),
    "lote": (cmd_lote, "executa o lote — exige autorização G10"),
}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="benner-rpa",
        description="Robô de extração de documentos do Benner — somente leitura.",
    )
    p.add_argument("--config", type=Path, default=None)
    sub = p.add_subparsers(dest="comando", required=True)
    for nome, (_fn, ajuda) in COMANDOS.items():
        sp = sub.add_parser(nome, help=ajuda)
        if nome in ("lote", "pre-voo"):
            sp.add_argument("--processo", default=None,
                            help="roda um processo só — como o G10 pede no primeiro acesso")
            sp.add_argument("--visivel", action="store_true",
                            help="abre o browser com janela (padrão é headless)")
            sp.add_argument("--limite", type=int, default=None,
                            help="quantos processos nesta execução (padrão: config)")
            sp.add_argument("--forcar", action="store_true",
                            help="reprocessa mesmo em estado terminal no ledger — "
                                 "use quando a classificação anterior foi errada")

    args = p.parse_args(argv)
    cfg = carregar_config(args.config)

    try:
        return COMANDOS[args.comando][0](cfg, args)
    except AcessoRealNaoAutorizado as erro:
        print(f"\n{erro}\n", file=sys.stderr)
        return 10


if __name__ == "__main__":
    raise SystemExit(main())
