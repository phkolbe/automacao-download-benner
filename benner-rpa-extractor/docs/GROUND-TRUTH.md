# Ground truth medido — não inferido

Tudo aqui foi lido dos arquivos reais em 2026-08-28. Builders e críticos comparam contra
estes números, nunca contra a descrição deles.

## Planilha de entrada

`data\CCR - Partes e Processos sem duplicidades.xlsx`

| Fato | Valor medido |
| :-- | :-- |
| Abas | `['Partes e Processos']` — aba única |
| Linhas totais | 334 (1 header + 333 dados) |
| Header | `RECLAMADA` \| `RECLAMANTE` \| `Nº PROCESSO` |
| Processos | 333, todos `str`, 333 distintos |
| Fora do formato CNJ | 0 |
| sha256 em 28/08 | `acfae637…d8b1f084` |
| sha256 em 29/08 | `0e387a5e…a7add7c1` |

> ⚠️ **A planilha é um documento vivo.** Em 29/08/2026 o responsável acrescentou as
> colunas `Benner OK` e `Obs` e reordenou as linhas — o `0012033` saiu da linha 2 para
> a 91. Qualquer coisa que dependa de posição de linha está errada por construção;
> processos são procurados por identidade.

### A coluna `Benner OK` — controle humano

Mantida à mão por quem está baixando em paralelo. O robô **lê e respeita; nunca escreve**.

| Valor | Significado | Em 29/08 |
| :-- | :-- | --: |
| `1` | concluído manualmente | 159 |
| `98` | só aparece em `PROCESSOS (PASTAS)` — não há o que baixar | 1 |
| `99` | não encontrado no Benner | 10 |
| *(vazio)* | ainda por fazer | **162** |
| `0` | **fora do domínio combinado** — bloqueado até esclarecimento | 1 |

O `98` é a confirmação independente do **G3**: existe processo que aparece na busca só
no grupo `PROCESSOS (PASTAS)`, sem grupo `PASTAS`. Foi descoberto à mão e bate com a
distinção que o robô já fazia.

### O que o G6 realmente protege

Não é "o arquivo nunca muda" — isso seria falso, e derrubou o gate quando a coluna foi
criada. É **o robô nunca escreve**, verificado comparando o hash no início e no fim da
mesma execução. Entre execuções, mudança é esperada e vira nota no relatório.

## Dimensionamento, medido

Com três processos reais baixados pelo robô, a média é **57 MB** por processo — não os
131 MB da amostra única de que partimos. Para os 162 pendentes: **≈ 13,6 GB**, contra os
44 GB estimados originalmente para 333.

## Pasta de referência (barra 2)

`saida\0000000-22.2023.5.15.0002 - exemplo\` — **somente leitura, G9**

| Arquivo | Bytes |
| :-- | :-- |
| `Lote_de_documentos_TRAB.000003.zip` | 131.059.962 |
| `Pedidos.xlsx` | 3.227 |

Layout **plano**, sem subpastas e sem `_manifest.json` (a pasta manual não tem manifest;
a do robô terá — é a única diferença esperada e legítima).

### O ZIP

| Fato | Valor |
| :-- | :-- |
| Bytes mágicos | `PK\x03\x04` ✓ |
| `testzip()` | `None` (íntegro) |
| **Entradas** | **93** |
| Subpastas internas | nenhuma — o ZIP também é plano |
| Descompactado | 131.025.329 bytes (compressão ~0%, é PDF) |

**93 entradas é o número mais importante deste documento.** A popup pagina de 10 em 10,
logo este processo tem ~10 páginas e a pasta manual só pode ter sido montada **com o
link `Selecionar todos os restantes?` acionado**. Um robô que ignore o link produz um ZIP
com 10 entradas em vez de 93 — a falha silenciosa do **G2**, aqui com número exato para
bater.

Nomes observados: `20250219 - Ata audiencia.pdf` e o padrão
`99317_<id>_<id>_<descritor>.pdf`. Nomes vêm do servidor; o robô não os gera.

### `Pedidos.xlsx`

Aba única `Pedidos`, 11 linhas (1 header + **10 pedidos**), 5 colunas:

`Data` | `Pedido Envolvido` | `Risco do pedido` | `Valor risco` | `Valor pedido`

`Data` vem como `datetime`, os valores como `float`.

> ⚠️ **Risco aberto, não premissa.** 10 linhas é exatamente o tamanho de uma página deste
> sistema. Ou o processo tem mesmo 10 pedidos, ou o export manual **também** pegou só a
> primeira página. O screenshot 06 mostra 4 pedidos visíveis com controles `<` `>` ativos
> — não permite decidir. Consequência: bater 10 linhas contra a referência **não prova**
> que o export está completo. A prova só vem do piloto, contando os pedidos na tela com
> `Ver todos` aplicado. Registrado em §13 do plano e no relatório do piloto.

## Menu `PASTA ▸ Ações` — ordem real (screenshot 03)

```
1. Atualizar valores                             ← ESCRITA
2. Atualizar identificador da pasta              ← ESCRITA
3. Bloqueio/Desbloqueio atualização de valores   ← ESCRITA
4. Nova mensagem                                 ← ESCRITA
5. Inserir documentos em lote                    ← ESCRITA
6. Baixar documentos                             ← o nosso
```

## Os dois banners da popup (screenshots 04 e 05)

Mesma faixa azul, conteúdos diferentes — **distinguir por texto, nunca por posição**:

| Screenshot | Texto |
| :-- | :-- |
| 04 | `Download de documentos em lote executado.` (sobra de execução anterior) |
| 05 | `Os 10 itens desta página estão selecionados.` + link `Selecionar todos os restantes?` |

## Grupos da busca (screenshot 02)

`CAUSA RAIZ (PASTAS)` · `PASTAS` · `PROCESSOS (PASTAS)` — o alvo é o do meio, match exato.
