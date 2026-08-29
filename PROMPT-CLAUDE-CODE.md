# Prompt Gauntlet Loop — Robô de Extração Benner (Fase 1)

Padrão conforme `github.com/robonuggets/gauntlet-loop` (técnica original de Matt Shumer / Claude of Duty).

---

## PARTE 1 — O prompt (cole isto numa sessão nova do Claude Code)

```
Build o robô de extração de documentos do Benner especificado em
C:\MyWorkspace\obsidian\DeCastro\DeCastro\Fase 1 - Extração de Documentos Benner.md
(revisão 4). Código em C:\MyWorkspace\claude-code\automacaoDeCastro\benner-rpa-extractor.
Python 3.11 + Playwright, headless. Entrada: data\CCR - Partes e Processos sem
duplicidades.xlsx, aba "Partes e Processos", coluna "Nº PROCESSO", 333 processos.

Há duas barras. Pegue a coisa real primeiro e compare contra ela direto, nunca contra
uma descrição dela.

Barra 1, para as peças de interface: os 6 screenshots reais em
benner-rpa-extractor-screenshots\. A comparação é imagem contra imagem — você renderiza
a sua fixture HTML, screenshota com o Playwright, e o crítico recebe as duas imagens sem
rótulo e responde qual é a tela real do Benner.

Barra 2, para o resultado final: a pasta saida\0000000-22.2023.5.15.0002 - exemplo, que
foi montada à mão e contém o ZIP e o Pedidos.xlsx verdadeiros daquele processo. O robô
processa o MESMO processo e o crítico recebe as duas pastas sem saber qual é qual.

Quebre isto nas menores peças que podem ser melhoradas e julgadas por si só. Para cada
peça, faça fan out de um builder e de um crítico separado com contexto fresco. O crítico
abre o output de verdade, põe ao lado da barra às cegas com os rótulos removidos, diz qual
dos dois é melhor e nomeia a única maior lacuna restante. Depois volta ao builder.

O crítico deve ser um crítico severo. Elogio não é útil. Se o nosso não ganhar, continua.

/loop em cada peça até o crítico escolher o nosso às cegas. Não pare antes disso.

Antes de qualquer peça: leia GATES.md e trate aqueles gates como veto. O crítico não pode
sobrepô-los — build que os viole está reprovado mesmo que ele escolha o nosso como melhor.
Dois em especial: nenhum clique em menu por índice ou posição, só por nome acessível exato;
e é proibido baixar enquanto a popup oferecer "Selecionar todos os restantes?".

Mantenha uma página de progresso ao vivo para eu acompanhar.

Fan out subagents and ultracode.
```

---

## PARTE 2 — As barras

### Barra 1 — os 6 screenshots (peças de interface)

Um print não é comparável com código, então a comparação é montada para ser **do mesmo tipo dos dois lados**:

**Comparação A — fixture renderizada × print real.** O builder produz a fixture HTML; o crítico renderiza com Playwright, screenshota, e recebe as duas imagens sem rótulo:

> Uma destas duas imagens é a tela real do Benner e a outra é uma reprodução. Qual é a real? E qual a maior diferença que te fez decidir?

Enquanto o crítico souber dizer qual é a real, o nosso perdeu. Isso força a fixture a reproduzir rótulos exatos, ordem dos itens do menu Ações, os três grupos de resultado, as colunas das tabelas e **os dois banners diferentes** — que é exatamente o que os seletores precisam para funcionar contra o sistema real.

**Comparação B — cobertura do mapa de seletores × print real.** O crítico enumera todos os elementos interativos visíveis no print e põe a lista ao lado do `selectors/benner.json`:

> Qual das duas listas descreve melhor esta tela? Nomeie o elemento mais importante que não está mapeado, ou que está mapeado de forma frágil.

### Barra 2 — a pasta de referência (o entregável)

Esta é a barra que a revisão anterior não tinha, e é a mais valiosa: `saida\0000000-22.2023.5.15.0002 - exemplo` foi montada à mão e contém o resultado verdadeiro — `Lote_de_documentos_TRAB.000003.zip` (131 MB) e `Pedidos.xlsx`.

O processo `0000000-22.2023.5.15.0002` é a **linha 2 da planilha real**, então o robô pode processá-lo de verdade. A comparação:

> Duas pastas para o mesmo processo. Uma foi montada por uma pessoa, a outra por um robô. Qual você preferiria receber, e por quê? Se a diferença estiver no ZIP, compare o índice central dos dois — sem extrair — e diga qual está mais completo.

Isso julga o que nenhum screenshot alcança: o pacote está completo? o `Pedidos.xlsx` tem o mesmo conteúdo? a pasta é utilizável por um advogado?

**Cuidado obrigatório:** a pasta de referência é **somente leitura**. O robô nunca escreve nela. A saída dele vai para `saida\0000000-22.2023.5.15.0002` (sem o sufixo ` - exemplo`).

### Onde nenhuma barra se aplica

Normalização, ledger, manifest, atomicidade e orquestração do lote não têm referência comparável. Ali o Gauntlet Loop não vale e o critério é o gate. Dizer isso em voz alta é melhor que forçar uma comparação artificial — que é justamente como barras vagas nascem, a falha nº 1 do padrão.

---

## PARTE 3 — `GATES.md` (veto que o crítico não sobrepõe)

Crie este arquivo na raiz do projeto.

```markdown
# GATES — veto absoluto

Pass/fail, rodam a cada rodada. Não podem ser afrouxados, marcados como skip/xfail ou
removidos sem autorização humana explícita. Build que viole qualquer um está reprovado,
mesmo que o crítico escolha o nosso como melhor.

## G1 · Benner é somente leitura
`PASTA ▸ Ações` tem 6 itens e 5 são de ESCRITA. `Baixar documentos` é o ÚLTIMO, logo
abaixo de `Inserir documentos em lote`.
Proibidos: `Atualizar valores`, `Atualizar identificador da pasta`,
`Bloqueio/Desbloqueio atualização de valores`, `Nova mensagem`,
`Inserir documentos em lote`. O painel `DOCUMENTOS` tem editar (lápis) e excluir
(vermelho) por linha.
- Clique em item de menu só por nome acessível EXATO, com verificação do texto antes.
- Proibido: índice, posição, coordenada, `nth()`, seletor parcial, match por
  "contém documentos".
- Teste obrigatório: localizar por índice falha por design.

## G2 · Seleção completa antes de baixar  ← o gate novo, e o mais fácil de errar
O checkbox do cabeçalho da popup seleciona APENAS a página corrente (10 itens). O
Benner então exibe:
  "Os 10 itens desta página estão selecionados. Selecionar todos os restantes?"
com `Selecionar todos os restantes?` como link.
- É PROIBIDO clicar em `Baixar documentos` enquanto esse link estiver sendo oferecido.
- Sequência: dispensar banner antigo → marcar checkbox → se o link existir, clicar →
  reler e confirmar que o link DESAPARECEU → só então baixar.
- O critério é a AUSÊNCIA do link, não a presença de um texto de confirmação (cujo
  texto exato é desconhecido).
- A popup usa a mesma faixa de alerta para este banner e para "Download de documentos
  em lote executado." — distinguir por CONTEÚDO, nunca por posição.
- Teste obrigatório (negativo): fixture com o link presente + tentativa de download
  precisa FALHAR, não avisar.
- Teste obrigatório: `entradas_no_zip == docs_listados_popup`.

## G3 · Grupo PASTAS com match exato
A busca retorna 3 grupos contendo a palavra PASTAS: `CAUSA RAIZ (PASTAS)`, `PASTAS`,
`PROCESSOS (PASTAS)`. O item correto está no grupo de título EXATAMENTE `PASTAS`.
Teste obrigatório: a fixture contém os três e o localizador acha só um.

## G4 · Verificação do processo antes de baixar
O detalhamento exibe `PROCESSO ▸ Número`. Confere contra o esperado antes de qualquer
download. Divergência = ERRO, sem download.

## G5 · Credenciais
Só via `.env` fora do Git. Ausentes de log, exceção, ledger, relatório, screenshot e
trace. Teste que varre todas as saídas.

## G6 · Planilha original imutável
Hash inalterado ao fim de qualquer execução. Escrita só na cópia de controle.

## G7 · ZIP nunca extraído
Validação só por `namelist()` / `testzip()` / bytes mágicos `PK\x03\x04`.
Teste obrigatório: nenhum arquivo é criado no disco durante a validação.

## G8 · Sucesso é o evento de download
Nunca o banner. A fixture deve incluir "Download de documentos em lote executado."
pré-existente, e um teste com esse banner e nenhum download real precisa FALHAR.

## G9 · Pasta de referência é somente leitura
`saida\0000000-22.2023.5.15.0002 - exemplo` nunca é escrita, movida ou apagada.
Teste obrigatório: hashes inalterados ao fim de qualquer execução.

## G10 · Nenhum acesso ao Benner real sem autorização humana
Desenvolvimento offline contra fixtures. O primeiro acesso real é de UM processo, com
autorização explícita.

## G11 · Atomicidade
Pasta final só existe com manifest válido. Interrupção deixa `.tmp` e o processo volta
a PENDENTE.

## G12 · Nada de seletor inventado
Onde o screenshot não permitir determinar, fica `TODO` explícito no JSON e é reportado.
```

---

## PARTE 4 — Decomposição sugerida em peças

O prompt manda quebrar nas menores peças julgáveis; esta é a partida.

| Peça | Barra / como é julgada |
| :-- | :-- |
| 1 · Fixture tela inicial + busca | Comp. A × `01 - lupa-de-pesquisa.png` |
| 2 · Fixture resultado agrupado | Comp. A × `02` — os 3 grupos presentes |
| 3 · Fixture detalhamento + menu Ações | Comp. A × `03` — os 6 itens na ordem exata |
| 4 · Fixture popup, página única | Comp. A × `04` — com o banner antigo de download |
| 5 · **Fixture popup, mais de uma página** | Comp. A × `05` — **com o link "Selecionar todos os restantes?"**. Peça mais importante do conjunto |
| 6 · Fixture PEDIDOS paginado | Comp. A × `06` — `Ver todos`, `⋮`, controles `<` `>` |
| 7 · Mapa de seletores | Comp. B × os 6 prints |
| 8 · Busca e identificação | Árvore da §4 do plano, ramo por ramo, × fixtures 2 e 3 |
| 9 · **Lógica de seleção total** | × fixtures 4 e 5; **G2 como veto**, incluindo o teste negativo |
| 10 · Download e interceptação | × fixture 5; G7 e G8 como veto; preserva o nome do servidor |
| 11 · Export de Pedidos | × fixture 6; dúvida da paginação registrada para o piloto |
| 12 · Normalização, planilha, ledger, manifest, atomicidade | Sem barra — gates G6, G7, G11 e testes de propriedade |
| 13 · Orquestração do lote | Máquina de estados da §6 coberta integralmente |
| 14 · Primeiro acesso real | G10 — para e pede autorização |
| 15 · **Processo 0000000-22.2023.5.15.0002 ponta a ponta** | **Barra 2** — a pasta produzida × a pasta de referência, às cegas |
| 16 · Empacotamento como plugin | `Plano de Componentes.md`; cada hook com teste que prova que BLOQUEIA |

As peças 5, 9 e 15 são o coração desta revisão: uma reproduz a tela do link, outra implementa a lógica, e a última prova contra o resultado humano real.

---

## PARTE 5 — O que mudou nesta versão

**A informação nova é a que mais importa.** As revisões anteriores afirmavam que o checkbox do cabeçalho resolvia a seleção no servidor. Está errado: ele marca só a página corrente (10 itens), e o sistema oferece um link `Selecionar todos os restantes?`. Um robô que ignore esse link produz, num processo com 47 documentos, um ZIP com 10 — e marca `CONCLUIDO`. Virou o gate **G2**, com teste negativo obrigatório.

Curiosamente, isso também **reforça a suspeita sobre o export de Pedidos**: agora está provado que este sistema tem o hábito de agir apenas sobre a página visível. O `Ver todos` antes de exportar deixa de ser precaução e passa a ser expectativa.

**Duas mudanças de menor peso, vindas da pasta de referência:** o nome do ZIP passa a ser **preservado como vem do servidor** (`Lote_de_documentos_TRAB.000003.zip`), porque carrega o identificador da pasta no Benner e serve como conferência cruzada — a revisão 3 o renomeava para `documentos.zip` e jogava isso fora. E o layout da pasta passa a ser **plano**, igual ao da referência, para que as duas sejam comparáveis diretamente.

**A planilha, inspecionada:** 333 processos, aba `Partes e Processos`, coluna `Nº PROCESSO`, todas as células em texto, formato 100% uniforme, zero duplicidade, zero caractere problemático para o Windows. As guardas de sanitização e duplicidade continuam, como rede de segurança.

**Dimensionamento:** o ZIP da referência tem 131 MB para um processo. Se representativo, 333 processos ≈ **44 GB**. O pré-voo mede a média real antes do lote.

Suas duas pendências seguem: criar o `.env` e remover a senha em texto plano de `System of Record.md`.
