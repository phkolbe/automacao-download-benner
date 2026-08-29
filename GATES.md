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
