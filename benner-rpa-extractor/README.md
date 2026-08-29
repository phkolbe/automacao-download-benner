# benner-rpa-extractor

Robô de extração de documentos do Benner — Fase 1. **Somente leitura no Benner.**

Para cada processo de uma planilha de 333 linhas, consulta o Benner, baixa o pacote de
documentos (um ZIP, nunca extraído) e a exportação de Pedidos, organiza numa pasta
nomeada pelo processo e marca o andamento numa cópia de controle.

Spec: `Fase 1 - Extração de Documentos Benner.md` (revisão 4) no vault do Obsidian.
Vetos: [`../GATES.md`](../GATES.md). Números medidos: [`docs/GROUND-TRUTH.md`](docs/GROUND-TRUTH.md).

## Estado

O desenvolvimento é **offline contra fixtures**. Nenhum acesso ao Benner real aconteceu,
e nenhum acontece sem autorização humana explícita — ver **G10** abaixo.

```bash
cd benner-rpa-extractor && .venv/Scripts/python.exe -m pytest tests -q
```

## Como rodar

Comandos offline, funcionam sempre:

```bash
PYTHONPATH=src .venv/Scripts/python.exe -m benner_rpa.cli auditar
```

```bash
PYTHONPATH=src .venv/Scripts/python.exe -m benner_rpa.cli verificar
```

`auditar` lê a planilha e reporta duplicidade, formato e espaço em disco.
`verificar` confronta o disco com o ledger, limpa `.tmp` órfãs e rebaixa `CONCLUIDO`
sem lastro.

Comandos que tocariam o Benner (`pre-voo`, `lote`) param com exit code 10 e explicam
como autorizar.

## Como autorizar o primeiro acesso real (G10)

Isto é deliberadamente chato de fazer por acidente. Em `config.yaml`:

```yaml
gates:
  acesso_real_autorizado: true
```

Um teste guarda o padrão desligado no arquivo versionado, então ligar isso aparece no
diff. A recomendação da spec é o primeiro acesso ser de **um** processo, não do lote.

## Setup

```bash
uv venv --python 3.11 .venv && uv pip install --python .venv -e ".[dev]" && .venv/Scripts/python.exe -m playwright install chromium
```

Credenciais em `.env` (fora do Git), a partir de `.env.example`:
`BENNER_URL`, `BENNER_USER`, `BENNER_PASSWORD`.

## Desenho

```
src/benner_rpa/
├── cli.py              comandos; tudo que tocaria o Benner passa por G10
├── core/
│   ├── config.py       config.yaml + .env; único ponto que lê credencial
│   ├── segredos.py     G5 — redação de credenciais em toda saída
│   ├── normalizacao.py número de processo e nome de pasta
│   ├── planilha.py     G6 — original somente leitura, controle é outro arquivo
│   ├── zip_seguro.py   G7 — validação sem extrair
│   ├── manifest.py     G11 — manifest e promoção atômica
│   ├── ledger.py       trilha append-only + reconciliação com o disco
│   ├── estados.py      máquina de estados da §6, transições declaradas
│   ├── disco.py        pré-voo de espaço
│   ├── lote.py         orquestração; fala com um protocolo, não com Playwright
│   └── relatorio.py    relatorio_lote.md
├── steps/              camada Playwright (contra as fixtures)
└── fixtures/           reproduções HTML das 6 telas
selectors/benner.json   mapa de seletores — papel + nome acessível, nunca CSS
scripts/                render_fixture.py e blind_pair.py (o harness do Gauntlet)
```

### Por que o orquestrador não conhece o Playwright

`core/lote.py` conversa com um `Protocol` de quatro métodos. Isso deixa cobrir a máquina
de estados inteira com um extrator falso, incluindo o que contra o sistema real seria
caro ou impossível de provocar: sessão caindo no meio, processo ambíguo, ZIP com 10 de
93 documentos, seleção não resolvida.

## Os três gates que protegem o acervo

**G1 — não alterar o Benner.** O menu `PASTA ▸ Ações` tem 6 itens e 5 são de escrita.
`Baixar documentos` é o último, imediatamente abaixo de `Inserir documentos em lote`.
Clique só por nome acessível exato; índice, posição e `nth()` são proibidos.

**G2 — não arquivar pacote incompleto.** O checkbox do cabeçalho da popup marca apenas
a página corrente (10 itens) e o Benner oferece o link `Selecionar todos os restantes?`.
É proibido baixar enquanto o link estiver sendo oferecido, e o critério é a **ausência**
do link — não a presença de um texto de confirmação, cujo texto exato é desconhecido.

A pasta de referência dá a esse gate um número exato: 93 entradas no ZIP para um
processo que pagina de 10 em 10. Um robô que ignore o link produz 10.

**G4 — não arquivar no processo errado.** O número lido em `PROCESSO ▸ Número` é
conferido contra o da planilha antes de qualquer download. Divergência é ERRO.

## O Gauntlet Loop

Cada peça é construída por um builder e julgada por um crítico com contexto fresco,
em loop até o crítico não conseguir mais distinguir.

**Barra 1 — os 6 screenshots.** O builder escreve a fixture HTML, o Playwright renderiza
no viewport exato do print e o crítico recebe as duas PNGs como `A.png` e `B.png`:
*qual é a tela real do Benner?* Enquanto ele souber responder, a nossa perdeu. A
atribuição A/B alterna a cada rodada.

**Barra 2 — a pasta de referência.** `saida\0000000-22.2023.5.15.0002 - exemplo` foi
montada à mão e é **somente leitura** (G9). O robô processa o mesmo processo e escreve
em `saida\0000000-22.2023.5.15.0002`, sem o sufixo.

**Onde nenhuma barra se aplica.** Normalização, ledger, manifest, atomicidade e
orquestração não têm referência comparável. Ali o critério é o gate, e dizer isso em voz
alta é melhor que forçar uma comparação artificial.

## Pendências abertas

- **O export de Pedidos respeita a paginação?** O `Pedidos.xlsx` de referência tem
  exatamente 10 linhas — o mesmo tamanho de uma página deste sistema. Ou o processo tem
  10 pedidos, ou o export manual também pegou só a página 1. Bater 10 linhas contra a
  referência **não prova** que o export está completo; a prova vem do piloto.
- **Texto do banner depois de acionar o link** — desconhecido. A regra não depende dele.
- **O filtro "Todos" oferece "Pastas"?** Se sim, simplifica a identificação do grupo.
- **Quantos dos 333 têm mais de 10 documentos** — o pré-voo responde.
