# Homologação multiparceiro — etapa 11

**Situação em 21/09/2026:** `dry-run` integral GET-only concluído; carga persistente e geração de relatórios reais **não autorizadas e bloqueadas** pela ausência do mapeamento parceiro–carteira aprovado. Nenhum payload, nome, documento, texto livre ou identificador Advbox foi gravado neste documento.

## Execução sanitizada

| Evidência | Resultado |
|---|---:|
| Modo | `dry_run_no_persistence` |
| Identificador técnico da execução | `19aca24ab0a64fa9b0d1a1eaa37159cb` |
| Início/fim UTC | 21/09/2026 12:22:55 / 12:35:57 |
| Duração | 13 min 02,298 s |
| Requisições GET | 260 |
| HTTP 429 / HTTP 5xx / erros de transporte | 0 / 0 / 0 |
| Parceiros reais governados no banco | 0 |
| Vínculos reais ativos | 0 |
| Relatórios reais gerados / sem dados / desatualizados / com erro | 0 / 0 / 0 / 0 |

O coletor manteve em memória apenas IDs técnicos, datas e contadores necessários à reconciliação e descartou os objetos ao terminar. O banco foi consultado somente para verificar parceiros/vínculos não sintéticos; nenhuma linha da API, checkpoint ou versão de relatório foi persistida. As sete versões já existentes no banco são demonstrações sintéticas e foram excluídas das contagens acima.

## Fonte oficial dos parceiros

O responsável confirmou em 21/09/2026 que os parceiros válidos são os cadastrados no módulo **Parceiros** do Advbox. Esse módulo existe na interface e gerencia compartilhamento de processos entre escritórios, porém não aparece na referência pública atual da API, que enumera 22 endpoints. O campo `origins` de `/settings` é documentado como origem de lead e, portanto, não é cadastro de parceiros.

A rota experimental da API pública `/api/v1/partners` não aceitou o Bearer token. Em seguida, duas capturas HAR higienizadas e produzidas pelo responsável na interface autenticada confirmaram as rotas internas GET `/content/partners` e GET `/content/friendship`, ambas HTTP 200. A primeira listou 10 parceiros em duas colunas e expôs ID técnico pela rota `/partners/{id}/edit`. A segunda listou 19 compartilhamentos, com paginação e colunas de partes, tipo de ação, número, parceiro e data; os processos expõem ID em `/lawsuits/{id}/edit`.

Na segunda captura, o filtro por um parceiro enviou `account_id` numérico e reduziu o total de 19 para 5. Esse identificador coincidiu com o `{id}` da tela de edição do parceiro e com o campo técnico oculto `id`, confirmando uma chave estável sem associação por nome. Nenhum valor, nome, ID, cookie ou corpo foi copiado para este documento; os HARs permanecem apenas em `storage/private`, ignorados pelo Git, e os scripts temporários de análise foram removidos.

A viabilidade técnica da coleta parceiro–processo está confirmada. P-005 deixa de ser uma incerteza de disponibilidade de dados e passa a ser um portão de contrato e autenticação: as rotas são internas, dependem de sessão/CSRF e não têm estabilidade, limite ou uso automatizado documentados. Produção requer autorização da Advbox e conta técnica/autenticação homologada; não será usada inferência por origem, nome, pasta ou responsável.

Em 22/09/2026, o suporte informou que os processos de parceiros também constam nas requisições de processos, mas que não existe rota específica de parceiros. Uma contraprova integral em memória percorreu as 44 páginas de GET `/lawsuits` no teto conservador de 20 GET/min: 4.369 processos, zero 429, zero duplicidade e os 19 processos compartilhados do HAR presentes (19/19). A resposta oficial, inclusive para esses 19 registros, não trouxe nenhum caminho de campo com semântica de parceiro, escritório, compartilhamento ou `account_id`.

Logo, a API pública é suficiente para obter os dados dos processos, mas não para segmentá-los. O desenho tecnicamente mínimo passa a ser híbrido e condicional: usar a API Bearer para todo o conteúdo e, somente com autorização expressa, usar `/content/partners` e `/content/friendship` para o mapeamento de IDs. Alternativamente, o suporte deve indicar um campo ou critério oficial de atribuição ainda não documentado.

## Cobertura e validação

| Recurso | Total informado | Páginas | Aceitos | Rejeitados | IDs duplicados |
|---|---:|---:|---:|---:|---:|
| Clientes | 4.226 | 43 | 4.226 | 0 | 0 |
| Processos | 4.363 | 44 | 4.363 | 0 | 0 |
| Transações | 12.845 | 129 | 12.845 | 0 | 0 |
| Últimos andamentos | 4.320 | 44 | 4.320 | 0 | 0 |

O total informado permaneceu estável em cada coleção. “Aceito” significa apenas compatível com o contrato técnico allowlisted; não significa vínculo aprovado, correção jurídica ou regra financeira aprovada.

Em relação aos totais informados no ensaio limitado de 16/09/2026, a origem cresceu em 13 clientes, 10 processos, 124 transações e 18 últimos andamentos. Isso comprova que a API é uma fonte mutável e reforça a decisão de não retomar offsets de fotografias antigas nem inferir exclusão pela ausência em uma única paginação.

## Qualidade consolidada

### Vínculo e carteira

| Medida | Contagem | Tratamento |
|---|---:|---|
| Processos vinculados | 0 | Nenhum mapeamento real foi fornecido; não inferir por nome, origem, pasta ou responsável. |
| Processos sem vínculo | 4.363 | Bloqueio explícito da carga útil para parceiros e de qualquer relatório real. |
| Processos em conflito | 0 | Resultado esperado com mapeamento vazio; não prova que o futuro mapeamento será isento de conflito. |
| Número processual ausente | 2.733 | Usar ID técnico como chave; externamente mostrar “não informado” somente após aprovação da visão. |
| Clientes relacionados a múltiplos processos | 659 | Deduplicar cliente e contar processos separadamente. |

### Financeiro

| Medida | Contagem | Tratamento |
|---|---:|---|
| Transações com valor tecnicamente disponível | 12.845 | Presença de valor não autoriza cálculo de repasse. P-006 permanece aberta. |
| Transações com valor ausente | 0 | Não converte ausência financeira de um processo em zero. |
| Processos com algum registro financeiro | 1.043 | Não publicável sem vínculo e regra aprovada. |
| Processos sem registro financeiro | 3.320 | Estado “não fornecido/sem registro”, nunca `0,00` implícito. |
| Processos com múltiplos registros financeiros | 943 | Preserva parcelas/lançamentos distintos; totalização e arredondamento aguardam regra. |
| Registros financeiros órfãos ou sem processo válido | 2.205 | Não associar por aproximação. Exigir correção da referência e reprocessamento identificável. |

### Idade do último andamento

| Faixa | Processos |
|---|---:|
| 0–30 dias | 1.020 |
| 31–90 dias | 397 |
| 91–180 dias | 401 |
| 181–365 dias | 607 |
| Mais de 365 dias | 1.893 |
| Sem andamento | 44 |
| Data futura | 1 |

A data futura é exceção de qualidade e não foi silenciosamente encaixada em uma faixa. “Sem andamento” permanece ausência, e a idade não determina relevância jurídica nem status executivo.

## Cenários de variabilidade

| Cenário obrigatório | Evidência/estado no `dry-run` | Tratamento |
|---|---|---|
| Processo sem financeiro | 3.320 processos sem registro | Ausência explícita; não gerar zero. |
| Histórico longo | A coleção global confirma somente o último andamento | Coberto por regressão sintética de layout; histórico integral real exige endpoint/paginação e autorização confirmados. |
| Vários processos para o mesmo cliente | 659 clientes nessa condição | Cliente único e processos distintos. |
| Carteira com financeiro parcial | Não avaliável por parceiro sem mapeamento | Bloquear relatório; não projetar a proporção global como carteira. |
| Financeiro parcelado | 943 processos têm múltiplos registros | Preservar lançamentos; regra de soma/rateio continua pendente. |
| Número processual ausente | 2.733 processos | ID Advbox continua chave; número é opcional. |
| Valor ausente | Nenhuma transação aceita sem valor; 3.320 processos não têm registro | Distinguir registro ausente de valor zero. |
| Dado financeiro órfão | 2.205 registros | Rejeitar associação automática e manter exceção reprocessável. |
| Indicadores sobrepostos | Não calculável sem regras P-006 | Regressão sintética mantém cartões independentes; não somar indicadores. |
| Campo livre sensível | Conteúdo não entra no resumo | Normalização e projeção externa por allowlist; testes de privacidade continuam obrigatórios. |

## Exceções e reprocessamento

| Código operacional | Condição | Estado | Próxima ação segura |
|---|---|---|---|
| `PARTNER_ATTRIBUTION_UNAVAILABLE` | `/lawsuits` contém 19/19 processos compartilhados, mas não informa a qual parceiro pertencem; rota interna de mapeamento existe, sem autorização respondida | Bloqueante para produção | Perguntar qual campo ou critério oficial identifica o parceiro ou obter autorização expressa para as duas rotas internas e homologar autenticação. |
| `MAPPING_NOT_APPROVED` | Coleta da relação foi demonstrada, mas há 0 parceiros/vínculos reais persistidos e 4.363 processos ainda sem vínculo local | Bloqueante | Implementar adaptador GET-only autorizado, carregar por IDs e aprovar o mapeamento com vigência e responsável. |
| `FINANCIAL_ORPHAN` | 2.205 registros sem processo válido | Bloqueante para financeiro afetado | Corrigir a origem/referência; após carga autorizada, usar dead-letter e reprocessar sem associação heurística. |
| `FUTURE_MOVEMENT_DATE` | 1 último andamento futuro | Revisão de qualidade | Confirmar fuso/data na origem; excluir de classificação até correção. |
| `NO_MOVEMENT` | 44 processos sem andamento | Não bloqueia ingestão; bloqueia inferência | Manter `not_provided`; não inventar data/status. |
| `PROCESS_NUMBER_MISSING` | 2.733 processos | Não bloqueia ingestão | Usar ID técnico, sem fabricar número. |
| `BUSINESS_RULE_NOT_APPROVED` | Financeiro/KPIs sem P-006 | Bloqueante para publicação | Aprovar fonte, fórmula, exceções, precisão e proprietário. |
| `SOURCE_CHANGED_SINCE_PRIOR_AUDIT` | Totais aumentaram desde 16/09/2026 | Informativo e relevante para consistência | Abrir lote novo desde offset zero; nunca reutilizar checkpoint de outra fotografia. |

## Portão para a carga integral

O critério de aceite da etapa 11 ainda **não está atendido**, pois não existe parceiro real elegível para o qual gerar relatório ou erro reprocessável. Para abrir a carga somente leitura são necessários, em conjunto:

1. resposta da Advbox indicando o campo ou critério oficial de parceiro em `/lawsuits`, ou autorização expressa para as duas rotas internas confirmadas;
2. conta técnica/autenticação homologada, incluindo sessão, CSRF, expiração, MFA e limites;
3. adaptador GET-only testado e mapeamento inicial por IDs aprovado, com tratamento explícito das referências ausentes e dos conflitos;
4. aprovação dos campos externos e das regras de negócio aplicáveis (P-006/P-007);
5. autorização explícita específica para persistir a carga integral após novo `dry-run` integrado;
6. decisão sobre tratamento dos 2.205 registros financeiros órfãos e da data futura;
7. storage privado e identidade homologada antes de qualquer publicação real.

Até esse portão ser satisfeito, executar somente `homologate-advbox`, que não persiste dados da API. Não executar `sync-advbox initial`, geração em massa nem publicação.
