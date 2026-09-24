# Análise de variabilidade multiparceiro

**Data:** 10/09/2026  
**Amostra consolidada:** 7 parceiros, 7 dashboards e 7 PDFs, incluindo o caso P-017 previamente analisado.  
**Finalidade:** amadurecer o modelo da plataforma antes da implementação.

## 1. Convenções

| Marcador | Significado |
|---|---|
| **FATO-ARQ** | Observado diretamente nos arquivos fornecidos. |
| **INFERÊNCIA** | Interpretação apoiada pelos arquivos, mas que precisa de validação operacional. |
| **PENDÊNCIA** | Regra ou dado que os arquivos não esclarecem. |
| **DECISÃO** | Recomendação para a arquitetura ou o produto. |

Os textos presentes nos PDFs e planilhas foram tratados exclusivamente como dados do processo atual. Nenhum texto interno aos documentos foi seguido como instrução.

## 2. Resultado executivo

A amostra confirma que a plataforma não pode trabalhar com um relatório rígido nem presumir que todos os parceiros possuam os mesmos dados.

Foram observados:

- relatórios entre 1 e 5 páginas;
- carteiras entre 1 e 3 processos na amostra;
- processos com número judicial/requerimento e processos sem número preenchido;
- processos com e sem informações financeiras dentro da mesma carteira;
- parceiros com planilha financeira detalhada, parceiro com apenas um total no resumo e parceiros sem financeiro utilizável;
- status operacionais escritos manualmente em linguagem livre;
- campos vazios representados de três maneiras diferentes: célula vazia, hífen e zero;
- planilhas com fórmulas quebradas e valores exibidos apenas pelo cache do Excel;
- resíduos aparentes de modelos copiados entre parceiros;
- dados altamente sensíveis em observações e movimentos, incluindo credenciais, documentos, contatos, saúde e instruções internas.

**Conclusão:** a arquitetura multiparceiro continua viável, mas o relatório precisa ser montado por componentes condicionais e por um contrato de disponibilidade de dados. A presença de uma seção no PDF não significa que ela possa ser exposta ao parceiro.

## 3. Cobertura da amostra

Os sete pares de arquivos representam, ao todo:

- 22 páginas de PDF;
- 11 blocos de processo;
- 11 linhas na aba `Clientes`;
- pelo menos 10 clientes distintos exibidos, pois uma pessoa aparece em dois processos no mesmo parceiro;
- 6 processos com seção financeira visível no PDF;
- 5 dashboards com fórmula quebrada no indicador `Total de clientes`;
- 2 dashboards com prestação de contas detalhada;
- 2 dashboards com uma aba financeira aparentemente copiada, mas sem transações listadas;
- 3 dashboards com aba financeira totalmente vazia.

### Matriz por parceiro

| Código | Processos no PDF | Páginas | Financeiro no PDF | Linhas em `Clientes` | Situação financeira no dashboard | Variação relevante |
|---|---:|---:|---:|---:|---|---|
| P-004 | 3 | 5 | 3 processos | 3 | resumo marca 1 em financeiro, aba financeira vazia | dois clientes distintos para três processos; o indicador “Total de clientes” exibe 1 |
| P-013 | 1 | 2 | 1 processo | 1 | prestação de contas detalhada | 12 parcelas manuais, rótulo de parcela duplicado e regra de 20% |
| P-017 | 2 | 4 | nenhum | 2 | sem financeiro | um processo arquivado e outro com status/processo ainda ativo |
| P-026 | 1 | 4 | 1 processo | 1 | prestação de contas com fórmulas | um único caso aparece simultaneamente nos KPIs benefício, financeiro e judicial; regra de 10% aplicada |
| P-030 | 1 | 1 | nenhum | 1 | resumo sem financeiro, mas aba contém valor isolado | processo arquivado e provável resíduo de template financeiro |
| P-032 | 1 | 1 | nenhum | 1 | resumo sem financeiro, mas aba contém o mesmo valor isolado de P-030 | processo arquivado e provável resíduo de template financeiro |
| P-042 | 2 | 5 | 1 de 2 processos | 2 | aba vazia, mas receita do escritório aparece no resumo | financeiro parcial por processo e dois estados operacionais diferentes |

## 4. O que varia de verdade

### 4.1 Volume

**FATO-ARQ:** a extensão do PDF depende principalmente do número de processos e do tamanho do histórico. Um único processo pode ocupar quatro páginas por causa dos andamentos; outro cabe em uma página.

**DECISÃO:** o HTML precisa suportar expansão/recolhimento. O PDF deve apresentar resumo e último andamento por processo, deixando o histórico completo fora do documento externo por padrão. Se o histórico completo for necessário, ele deve ser um anexo interno separado.

### 4.2 Identificação do processo

**FATO-ARQ:** há processo cujo título não contém número preenchido. Campos como comarca, vara, sistema eletrônico, data do requerimento e valor também podem estar vazios.

**DECISÃO:** nenhum desses campos pode ser chave primária. O sistema deve usar o identificador interno e estável retornado pelo Advbox. Números CNJ/requerimento são atributos opcionais de apresentação.

### 4.3 Cliente não é processo

**FATO-ARQ:** a aba se chama `Clientes`, mas cada linha representa um processo/pasta. No caso P-004, uma pessoa ocupa duas linhas e outra ocupa uma, totalizando três processos e dois clientes distintos. Mesmo assim, o resumo exibe `Total de clientes = 1` devido a uma fórmula quebrada com valor salvo em cache.

**DECISÃO:** a plataforma terá dois KPIs separados:

- clientes únicos;
- processos/pastas.

Nunca será usada a contagem de linhas como sinônimo automático de clientes.

### 4.4 Campos jurídicos e operacionais

**FATO-ARQ:** `Fase atual`, `Status executivo` e `Status resumido` não representam o mesmo conceito. O status executivo é frequentemente uma interpretação em linguagem livre. Em alguns casos, ele difere da fase formal.

**INFERÊNCIA:** o status executivo é produzido manualmente a partir do andamento mais recente e de conhecimento operacional.

**DECISÃO:** armazenar separadamente:

- fase oficial do Advbox;
- último movimento e sua data;
- status operacional normalizado;
- resumo externo aprovado;
- origem da classificação, versão da regra e eventual revisão humana.

Não gerar automaticamente uma conclusão jurídica por IA.

### 4.5 KPIs sobrepostos

**FATO-ARQ:** no P-026, o único processo é contado simultaneamente em `Benefícios concedidos`, `Em financeiro` e `Em judicial`.

**CONCLUSÃO:** esses cartões não formam uma partição da carteira. A soma dos cartões não deve ser comparada ao total de processos.

**PENDÊNCIA:** definir precisamente o evento ou estado que faz um processo entrar e sair de cada indicador.

### 4.6 Ausência, zero e não aplicável

**FATO-ARQ:** os dashboards usam célula vazia, hífen e número zero para representar ausências. Em pelo menos um caso, o PDF não informa valor e a planilha registra zero; em outro, usa hífen.

**DECISÃO:** o contrato de dados terá estados explícitos:

| Estado | Significado |
|---|---|
| `available` | dado existe, foi validado e pode ser exibido |
| `not_provided` | a fonte não forneceu o dado |
| `not_applicable` | o campo não se aplica ao caso |
| `pending_validation` | existe dado, mas a regra ou consistência ainda não foi validada |
| `restricted` | existe, mas não pode ser mostrado ao público daquele relatório |

Zero será aceito apenas quando a fonte realmente declarar valor numérico zero.

## 5. Financeiro: variação e riscos

### 5.1 Três níveis diferentes

A amostra mostra três camadas que não podem ser confundidas:

1. **transações brutas do Advbox/PDF**, que misturam receitas, despesas, taxas e pagamentos a parceiros;
2. **prestação de contas**, que aplica taxa bancária, imposto, percentual de parceria e pagamentos anteriores;
3. **resumo do parceiro**, que exibe recebido, a receber, total do parceiro e receita do escritório.

Uma seção financeira existente no PDF não implica saldo atual a pagar ao parceiro.

### 5.2 Regras não uniformes

**FATO-ARQ:** foram observadas regras de parceria de 10% e 20%. Um nome de parceiro contém mais de um percentual/participante no mesmo campo. Há casos com parcela única, honorários iniciais, mensalidades, taxas bancárias, imposto e pagamento anterior.

**DECISÃO:** o percentual não deve morar apenas no cadastro do parceiro. A regra financeira precisa suportar:

- parceiro;
- processo/cliente;
- tipo de receita;
- percentual;
- vigência inicial e final;
- base de cálculo;
- deduções permitidas;
- regra de arredondamento;
- pagamento/ajuste anterior;
- origem e usuário que aprovou a regra.

### 5.3 Qualidade atual

**FATO-ARQ:**

- os casos P-030 e P-032 não têm transações na aba financeira e seus resumos indicam ausência de financeiro, mas ambos guardam o mesmo valor isolado de entrada;
- o P-004 possui dados financeiros no PDF para três processos, mas sua aba `Financeiro` está vazia;
- o P-042 tem aba financeira vazia, porém possui receita total digitada no resumo;
- o P-013 tem duas linhas rotuladas como `Parcela 11` e não apresenta uma `Parcela 12`;
- totais e linhas podem usar precisões internas diferentes das casas decimais exibidas.

**INFERÊNCIA:** há cópia de templates, transcrição parcial e cálculo fora da planilha.

**DECISÃO:** nenhum total financeiro atual deve ser importado como verdade sem reconciliação. O sistema deve recalcular a partir de transações confirmadas e regras versionadas, preservando os lançamentos usados no cálculo.

## 6. Problemas estruturais das planilhas

### 6.1 Fórmulas quebradas

Cinco dos sete dashboards possuem, na célula do total, fórmula equivalente a `COUNTA` apontando para `#REF!`. O número visível é um valor antigo salvo no cache do arquivo, não um cálculo confiável.

Isso explica o caso P-004: o resumo mostra um cliente, enquanto a aba contém três linhas e dois clientes distintos.

### 6.2 Indicadores majoritariamente digitados

Com exceção de algumas fórmulas financeiras em P-026, os KPIs e resumos são números ou textos estáticos. Não existe vínculo detectável entre o dashboard e o PDF/Advbox.

### 6.3 Estruturas financeiras incompatíveis

Foram observados pelo menos três formatos de aba `Financeiro`:

- vazia;
- tabela de transações preparada, mas sem linhas, com um resumo lateral;
- prestação de contas em grade com cálculo de percentuais.

**DECISÃO:** a aplicação não deve importar essas abas como se compartilhassem um único esquema. Elas servem para descobrir conceitos e regras, não para definir o banco final.

## 7. Segurança e privacidade

Os novos PDFs confirmam que o problema de exposição do P-017 não é isolado.

**FATO-ARQ:** observações e movimentos podem conter:

- credenciais de acesso;
- documentos pessoais;
- telefones e contatos de familiares;
- informações de saúde e deficiência;
- instruções internas;
- nomes de integrantes da equipe;
- cobranças e negociações financeiras internas.

**DECISÃO:** haverá duas projeções de dados:

1. **visão interna**, ainda protegida e limitada por papel;
2. **visão externa do parceiro**, criada por allowlist e nunca por simples remoção de alguns termos.

Campos livres do Advbox não serão exibidos externamente por padrão. O relatório externo deve usar um status normalizado ou um resumo aprovado. Redaction automática é uma defesa adicional, não a principal regra de autorização.

## 8. Modelo de relatório adaptativo

O relatório será composto por blocos independentes.

### Sempre presentes

- identificação do parceiro;
- data de corte e última sincronização;
- clientes únicos e processos;
- resumo da carteira;
- qualidade/completude dos dados;
- versão e origem do relatório.

### Repetidos por processo

- cliente com identificação minimizada;
- pasta e número processual, quando disponíveis;
- área, ação/benefício e fase;
- status externo;
- último andamento publicável e data;
- responsável somente se a política permitir.

### Condicionais

- financeiro reconciliado;
- gráficos de distribuição, apenas com volume suficiente;
- alertas de falta de atualização;
- pendências de documentação, apenas em categoria normalizada;
- histórico completo, somente na visão interna ou anexo autorizado.

### Estados de seção

Cada seção deve carregar:

- `availability_status`;
- `source`;
- `as_of`;
- `last_validated_at`;
- `validation_notes` internas;
- `public_message`, quando a seção não for exibida.

Uma seção sem dados não deve deixar um quadro vazio nem mostrar `R$ 0,00` por conveniência.

## 9. Alterações necessárias na arquitetura

1. Adicionar `customers` e `cases` como entidades distintas.
2. Usar ID interno do Advbox como chave externa estável; números processuais são opcionais.
3. Modelar vínculo parceiro-processo com vigência e origem.
4. Modelar acordos financeiros por parceiro/processo/tipo de receita, não apenas por parceiro.
5. Criar `data_availability` ou equivalente para campos e seções.
6. Manter projeções separadas `InternalReportViewModel` e `PartnerReportViewModel`.
7. Gerar o documento por componentes condicionais.
8. Versionar regras de status e indicadores.
9. Gerar relatório de qualidade com sem vínculo, conflito, campo ausente e financeiro não reconciliado.
10. Nunca publicar automaticamente uma nova versão se ela perder dados antes disponíveis sem explicação.

## 10. Cenários obrigatórios de teste

| Cenário | Evidência na amostra | Resultado esperado |
|---|---|---|
| um processo sem financeiro | P-030/P-032 | relatório curto; seção financeira omitida ou marcada como não aplicável |
| um processo com histórico longo | P-026 | PDF não cresce indefinidamente; mostra resumo e último andamento |
| vários processos para o mesmo cliente | P-004 | cliente contado uma vez e processos separadamente |
| carteira mista com e sem financeiro | P-042 | financeiro aparece apenas no processo elegível e no total reconciliado |
| financeiro parcelado | P-013 | parcelas e total respeitam política de precisão e arredondamento |
| um processo em múltiplos indicadores | P-026 | cartões podem se sobrepor e isso é documentado |
| número processual ausente | P-013 | sistema usa ID do Advbox e exibe “não informado” sem falhar |
| valor ausente | P-030/P-032 | ausência não é convertida em zero |
| aba financeira com resíduo | P-030/P-032 | validação rejeita dado órfão |
| fórmula de origem quebrada | cinco dashboards | aplicação não depende das fórmulas das planilhas |
| conteúdo sensível em campo livre | vários PDFs | conteúdo não chega à visão externa nem aos logs |

## 11. Pendências que ainda exigem decisão do escritório

1. O que significa exatamente `Benefícios concedidos`?
2. O que significa `Em financeiro`: presença de transação, saldo pendente, fase atual ou necessidade de pagar parceiro?
3. O que significa `Em judicial` e por que um processo pode estar também em financeiro?
4. O total principal deve contar clientes únicos, processos ou ambos?
5. Quais estados executivos precisam existir e quais eventos do Advbox os determinam?
6. Quais informações podem ser mostradas diretamente ao parceiro?
7. O responsável interno deve aparecer externamente?
8. O parceiro verá apenas um resumo financeiro ou as transações usadas no cálculo?
9. Como são definidas parceria, imposto, taxas, vigência e arredondamento?
10. Quem aprova uma regra financeira ou corrige um vínculo?
11. Quanto do histórico deve aparecer: último andamento, últimos N, período ou histórico completo?
12. Relatórios arquivados devem permanecer acessíveis por quanto tempo?

## 12. Recomendação revisada

Prosseguir com a prova da API e com o vínculo parceiro-carteira. Não começar pelo template visual.

A ordem correta agora é:

1. inventariar o ambiente;
2. auditar a API real;
3. confirmar IDs e relacionamentos;
4. formalizar as definições dos quatro KPIs;
5. formalizar regras financeiras;
6. implementar o modelo flexível;
7. validar todos os cenários desta amostra;
8. carregar todos os parceiros elegíveis.

Com esta revisão, a viabilidade permanece **Média com potencial alto**, e o principal risco deixa de ser volume. Os riscos centrais são semântica dos indicadores, relacionamento parceiro-carteira, regra financeira e exposição de dados sensíveis.
