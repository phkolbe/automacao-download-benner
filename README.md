# Automação de download — Benner

Robô que baixa, para cada processo de uma planilha, o pacote de documentos e a
exportação de Pedidos do sistema jurídico Benner. **Somente leitura no Benner.**

Construído com Playwright em Python, com doze *gates* de veto que valem mais que
qualquer teste: eles definem o que o robô tem proibido fazer.

---

## O que este repositório contém — e o que não contém

Este repositório é **público**, então tudo que identifica pessoas ficou de fora:

| Fora do repositório | Por quê |
| :-- | :-- |
| `.env` | credenciais |
| `data/` | planilha com nomes de reclamantes e números de processo reais |
| `saida/` | documentos judiciais baixados |
| `benner-rpa-extractor-screenshots/` | telas do Benner com nomes reais |

As **fixtures HTML** em `src/benner_rpa/fixtures/` reproduzem as telas do Benner com
dados fictícios. É contra elas que a maior parte dos testes roda — sem precisar de
acesso ao sistema real, sem expor ninguém.

---

## Rodar em outra máquina

### 1. O que você precisa antes

- **Python 3.11** — o projeto fixa essa versão
- **[uv](https://docs.astral.sh/uv/)**, que instala o próprio Python se faltar
- Acesso ao Benner (usuário e senha)

Se não tiver `uv`:

```bash
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 2. Clonar e preparar

```bash
git clone https://github.com/phkolbe/automacao-download-benner.git
```

```bash
cd automacao-download-benner/benner-rpa-extractor
```

```bash
uv venv --python 3.11 .venv
```

```bash
uv pip install --python .venv -e ".[dev]"
```

```bash
.venv\Scripts\python.exe -m playwright install chromium
```

### 3. Credenciais

Copie `.env.example` para `.env` e preencha:

```
BENNER_URL=https://ccr.bennercloud.com.br/JURIDICO_EXT/Login
BENNER_USER=seu.usuario
BENNER_PASSWORD=sua.senha
```

O `.env` está no `.gitignore` e nunca deve ser commitado.

### 4. Conferir que está tudo de pé

```bash
.venv\Scripts\python.exe -m pytest tests -q
```

165 testes, todos offline. Se passarem, o robô está saudável — nenhum deles toca o
Benner.

### 5. Fornecer a planilha de entrada

> ⚠️ **A planilha não vem no repositório** e sem ela o robô não roda. A original tem
> nomes de reclamantes e números de processo reais, e este repositório é público —
> por isso `data/` está no `.gitignore`. Você precisa fornecer a sua.

Crie a pasta `data/` na raiz do projeto e coloque ali o `.xlsx`. Ele precisa ter:

| Requisito | Detalhe |
| :-- | :-- |
| **Uma aba** com os processos | padrão `Partes e Processos`; outro nome, ajuste `planilha.aba` |
| **Uma coluna com o número do processo** | **obrigatória** — sem ela o robô para e diz o que encontrou, em vez de adivinhar |
| Coluna `Benner OK` | opcional, mantida à mão — ver abaixo |

O cabeçalho da coluna de processo é detectado de forma tolerante: `Nº PROCESSO`,
`N° PROCESSO`, `Numero Processo`, `Processo` e `CNJ` funcionam, com ou sem acento e em
qualquer caixa. Se o seu for diferente, acrescente-o em `planilha.deteccao_coluna` no
`config.yaml`.

Os números devem estar no formato CNJ (`NNNNNNN-NN.NNNN.N.NN.NNNN`). Guarde-os como
**texto** na planilha — como número, o Excel come os zeros à esquerda.

Depois ajuste em `config.yaml` os caminhos da sua máquina:

```yaml
planilha:
  caminho: 'C:\...\data\sua-planilha.xlsx'
  aba: 'Partes e Processos'
saida:
  raiz: 'C:\...\saida'
```

Para conferir que a planilha foi entendida antes de qualquer acesso ao Benner:

```bash
.venv\Scripts\python.exe -m benner_rpa.cli auditar
```

---

## Usar

Todos os comandos rodam de `benner-rpa-extractor/`.

### Ver o que há para fazer (não toca o Benner)

```bash
.venv\Scripts\python.exe -m benner_rpa.cli auditar
```

Mostra quantos processos existem, quantos já foram resolvidos à mão, quantos faltam,
e quanto disco o lote vai exigir — com a média **medida**, não estimada.

### Conferir o que já está no disco (não toca o Benner)

```bash
.venv\Scripts\python.exe -m benner_rpa.cli verificar
```

Confronta as pastas produzidas com o registro de execução, limpa temporárias órfãs e
rebaixa qualquer processo marcado como concluído que não tenha lastro no disco.

### Acompanhar o tempo

Cada processo registra no seu `_manifest.json` quando começou, quando terminou e
quanto levou — a duração cobre as retentativas, então é o custo real daquele processo,
não o da última passada:

```json
{
  "iniciado_em": "2026-08-29T01:10:00-03:00",
  "concluido_em": "2026-08-29T01:14:12-03:00",
  "duracao_s": 252.0,
  "duracao": "4m 12s",
  "tentativas": 1
}
```

O mesmo vai para o ledger. Ao fim da execução o CLI imprime o **tempo de parede** do
lote — que inclui login, throttle e retentativas, e por isso é maior que a soma dos
processos. É esse número que responde "quanto tempo vai levar".

O `relatorio_lote.md` traz média, mais rápido, mais lento e a projeção para o que
falta.

### Rodar de verdade

Primeiro **autorize**, em `config.yaml`:

```yaml
gates:
  acesso_real_autorizado: true
```

Isso é deliberadamente chato: um teste guarda o padrão desligado, então ligar aparece
no diff. Depois:

```bash
.venv\Scripts\python.exe -m benner_rpa.cli lote --processo 0000000-00.0000.0.00.0000
```

Um processo só — é assim que o **G10** quer o primeiro acesso. Para o lote:

```bash
.venv\Scripts\python.exe -m benner_rpa.cli lote --limite 10
```

Sem `--limite`, usa o valor de `config.yaml`. O lote é retomável: rodar de novo
continua de onde parou, sem refazer o que já está íntegro.

### Windows PowerShell

Não use `&&` para encadear — o PowerShell 5.1 não tem esse operador. Rode um comando
por vez, ou separe com `;`.

---

## A coluna `Benner OK`

Se alguém estiver baixando em paralelo, marque na planilha e o robô respeita:

| Valor | Significado |
| :-- | :-- |
| `1` | já concluído à mão |
| `98` | aparece só em `PROCESSOS (PASTAS)` — não há o que baixar |
| `99` | não existe no Benner |
| *(vazio)* | o robô processa |

A marca humana vence tudo, inclusive `--forcar`. Valor fora dessa lista não é
processado nem ignorado: vira `BLOQUEADO` e sai no relatório, porque adivinhar a
intenção de quem escreveu seria pior que parar.

O robô **lê e respeita, nunca escreve** nessa planilha.

---

## Os doze gates

Estão em [`GATES.md`](GATES.md), na raiz. Não são sugestões — um build que viole
qualquer um está reprovado. Os três que protegem o acervo:

**G1 — não alterar o Benner.** O menu `Ações` tem seis itens e cinco são de escrita;
`Baixar documentos` é o último, logo abaixo de `Inserir documentos em lote`. O robô
confere **dois sinais independentes** antes de clicar: o comando de servidor no id
(`BTBAIXARLOTE`) e o texto visível. Se discordarem, não aciona.

**G2 — não arquivar pacote incompleto.** A popup lista 10 documentos por página. Ao
marcar o cabeçalho, o Benner oferece `Selecionar todos os restantes?`, e é proibido
baixar enquanto esse link existir. O total vem do banner (`93 itens selecionados`),
nunca da contagem de linhas — a tela mostra 10 mesmo com 93 selecionados.

**G4 — não arquivar no processo errado.** O número lido na tela é conferido contra o
da planilha antes de qualquer download.

---

## Como isto foi construído

O robô foi desenvolvido inteiro **offline**, contra fixtures HTML que reproduzem as
telas do Benner. Só depois foi autorizado a tocar o sistema real, um processo por vez.

Praticamente toda parada no acesso real foi uma **suposição minha sobre o DOM** que o
sistema desmentiu — papéis ARIA que não existem, links sem `href`, popups que são
iframes, listas planas onde eu esperava aninhamento. Cada correção virou uma entrada
no mapa de seletores com o **porquê**, para que ninguém a "simplifique" de volta.

Duas valem ser lidas antes de mexer no código, em
[`selectors/benner.json`](benner-rpa-extractor/selectors/benner.json):

- `busca._como_digitar` — `fill()` não dispara a busca ao vivo, e produzia um falso
  "processo não encontrado" que era **terminal**
- `popup_documentos.link_selecionar_restantes` — o seletor errado fez o robô baixar
  10 documentos de 93 e marcar como concluído, exatamente a falha que o G2 existe
  para impedir

Detalhes em [`docs/GROUND-TRUTH.md`](benner-rpa-extractor/docs/GROUND-TRUTH.md).
