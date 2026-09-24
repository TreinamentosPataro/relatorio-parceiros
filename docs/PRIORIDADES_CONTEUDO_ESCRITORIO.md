# Prioridades de conteúdo informadas pelo escritório

**Data da análise:** 23/09/2026  
**Estado:** requisitos candidatos; não equivalem a allowlist aprovada nem autorizam implementação/publicação  
**Fonte da evidência:** PDF real anotado pelo escritório, analisado somente em ambiente local e não incorporado ao repositório

## Evidência sanitizada

O material possui 55 páginas com camada de texto e 13 marcações amarelas, concentradas nas páginas 1, 2 e 4. A análise registrou somente as categorias dos elementos marcados, nunca seus valores, nomes, números, textos ou identificadores.

As marcações indicam cinco prioridades operacionais:

1. identificação da parte/cliente;
2. tipo de ação ou benefício;
3. fase atual do processo;
4. detalhe financeiro por processo;
5. data e conteúdo do andamento manual mais recente destacado pelo escritório.

Também foi marcada a distinção de registros internos no bloco financeiro. Isso reforça que informação útil à operação interna não é automaticamente adequada à visão do parceiro.

O PDF anotado é um **artefato de requisitos**, não um exemplo válido de upload: ele foi modificado depois da exportação e contém anotações. O parser não pode depender de cor, destaque ou comentário e o arquivo não será convertido em fixture, screenshot versionada ou dado de teste.

## Interpretação técnica inicial

| Prioridade | Fonte estruturada preferencial | Uso interno seguro enquanto pendente | Visão externa enquanto pendente | Decisão ainda necessária |
|---|---|---|---|---|
| Parte/cliente | `customers` e relação `lawsuit_customers` da API oficial | `restricted`; exibição nominal somente após P-007 e controle de acesso | Referência pseudonimizada; nome bloqueado | Definir se o escritório quer cliente principal, todas as partes ou outro papel; aprovar quem pode ver nomes |
| Tipo de ação/benefício | IDs e catálogo de tipo/grupo do processo na API oficial | Rótulo estruturado após validar o catálogo | Omitido ou `pending_validation` até allowlist | Aprovar rótulo, granularidade e eventual agrupamento de negócio |
| Fase atual | ID/rótulo de fase/etapa da API oficial | Fase operacional com fonte e data; não é status jurídico | `pending_validation` até mapa aprovado | Definir se o rótulo bruto basta ou se haverá mapa versionado; não inferir conclusão jurídica |
| Financeiro por processo | `transactions` da API oficial e regras financeiras aprovadas | Registros estruturados e segregados por acesso; valores continuam pendentes sem P-006 | Bloqueado por padrão; registro interno nunca sai por herança | Aprovar tipos, categorias, competência, vencimento/pagamento, parcelas, totais, sinal, rateio e tratamento de `is_internal` |
| Andamento manual mais recente | `last_movements`, `movements` e/ou `history`, conforme contrato oficial já auditado | Data cronológica pode ser exibida; texto permanece restrito até classificação | Texto livre bloqueado; no máximo resumo determinístico aprovado no futuro | Definir “mais recente” versus “relevante”, fonte entre endpoints, tamanho, redação permitida e necessidade de revisão humana |

O destaque do escritório prova prioridade de uso, não correção semântica nem permissão de exposição. Nome nunca é chave; fase não é status jurídico; presença de lançamento não prova valor devido; o movimento destacado não prova relevância jurídica por si só.

## Campos financeiros candidatos para a matriz PDF-5

O relatório de referência mostra necessidade de granularidade, mas os valores virão exclusivamente da API oficial. A etapa PDF-5 deverá avaliar, campo a campo, pelo menos:

- tipo de entrada/saída;
- vencimento;
- pagamento, quando fornecido;
- competência;
- categoria;
- identificação técnica da parcela/lançamento;
- valor com sinal e estado de disponibilidade;
- indicador de registro interno;
- totalização, somente com regra aprovada.

Ausência de pagamento, valor ou regra não vira zero. Receita, despesa, repasse, saldo e honorário são conceitos diferentes e não serão combinados por aproximação.

## Perguntas para homologação com o escritório — P-023

1. A identificação nominal será usada apenas pela equipe interna ou também no relatório destinado ao parceiro?
2. “Partes” significa cliente principal, todos os clientes vinculados, polo processual ou outro papel?
3. O tipo de ação deve reproduzir o catálogo do Advbox ou usar uma classificação mais curta aprovada?
4. A fase exibida é a fase operacional do Advbox ou um status de negócio diferente?
5. O financeiro precisa de lançamentos completos, apenas totais, ou ambos? Quais categorias e registros internos podem ser vistos por cada papel?
6. O andamento desejado é sempre o manual mais recente, o último cronológico de qualquer origem ou um item escolhido por revisor?
7. O texto integral do andamento pode aparecer somente internamente? Qual resumo, se algum, pode aparecer externamente?
8. Quantos lançamentos e andamentos devem aparecer antes de resumir/expandir a interface?

Até essas respostas serem aprovadas, todos os cinco grupos são requisitos candidatos. A implementação poderá provar contratos e estados com dados sintéticos, mas não liberar valores reais na visão externa.

## Impacto na trilha PDF

| Etapa | Ajuste decorrente |
|---|---|
| PDF-1 | Recusar arquivo pós-editado com destaque/comentário como fonte de importação; preservar o PDF anotado apenas como requisito privado |
| PDF-2 | Extrair somente o manifesto; não persistir parte, ação, fase, financeiro ou andamento e não usar cor/anotação como sinal |
| PDF-3 | Confirmar cobertura das cinco prioridades nos endpoints oficiais e registrar lacunas sem copiar valores |
| PDF-5 | Construir e aprovar matriz interna/externa específica para os cinco grupos e suas regras |
| PDF-6 | Priorizar no layout apenas os campos aprovados, com contratos separados para equipe interna e parceiro |
| PDF-7 | Homologar com usuários do escritório a semântica, completude e visibilidade por papel, sem dados reais em artefatos versionados |

