# ADR-004 — Escopo operacional e conteúdo do MVP

**Data:** 25/09/2026

**Estado:** aprovado pelo responsável do projeto, incluindo retenção P-012/P-019 em 25/09/2026 e contas individuais de operadores internos em 29/09/2026

## Objetivo

Manter a rotina simples para o escritório: operadores internos autorizados exportam o PDF no Advbox, enviam o arquivo, revisam exceções e geram uma versão privada. Não haverá login de parceiros nem automação de envio no MVP.

## Papéis e aprovação — P-018

- `portal_admin` pode enviar, revisar, aprovar, rejeitar, substituir e gerar o relatório.
- `internal_reader` pode consultar versões já validadas, sem enviar ou decidir lotes.
- Cada advogado operador usa uma conta `portal_admin` individual; credenciais compartilhadas são proibidas para preservar autoria, revogação e auditoria.
- Não haverá regra obrigatória de quatro olhos no MVP.
- A mesma pessoa poderá enviar e aprovar, mas cada ação exige confirmação, CSRF e auditoria allowlisted.
- “Publicar” no MVP significa tornar a versão validada disponível no portal interno. Envio ao parceiro permanece uma ação manual externa à plataforma.

## Exportação — P-020

- Processamento sob demanda, sem agenda automática.
- Um lote representa um parceiro e um período mensal de referência.
- O operador exporta a carteira completa disponível para o parceiro, sem filtros casuais por nome, responsável ou situação.
- Correção do mesmo parceiro/período usa substituição versionada; não cria carteira paralela.

## Exceções de reconciliação — P-022

- Número processual canônico exato permanece a chave principal.
- Pasta exata é fallback somente quando o número estiver ausente e houver uma correspondência única.
- `unmatched`, `ambiguous`, `duplicate_source` e `invalid_identifier` bloqueiam aprovação.
- A correção ocorre no Advbox e por nova exportação, ou por seleção explícita de ID técnico já existente conforme o fluxo auditado. Nome, cliente, parte, similaridade e texto livre nunca são chaves.

## Conteúdo do MVP — P-006/P-007/P-023

O portal e os artefatos continuam privados e internos. Não haverá visão externa autenticada para parceiros no MVP.

| Conteúdo | Decisão do MVP |
|---|---|
| Parte/cliente | Nome restrito à visão interna e somente para usuários autenticados; nunca é chave. Não entra em artefato externo. |
| Ação/benefício | Usar apenas ID e rótulo oficial confirmado da API. Não criar classificação jurídica própria. |
| Fase | Exibir somente a fase operacional oficial, rotulada como tal. Não inferir status jurídico. |
| Clientes e processos | Publicar internamente apenas contagens com vínculo único e fotografia completa; ausência não vira zero. |
| Financeiro | Não calcular nem publicar valores no MVP. Registros, fórmulas, repasses e `is_internal` permanecem `restricted`/`pending_validation`. |
| Andamento | Data/origem estruturada podem aparecer internamente quando confirmadas. Texto integral e “andamento relevante” permanecem restritos; não haverá seleção automática por relevância. |
| PDF-fonte | Nunca é relatório e nunca fica disponível para download pelo portal. |

Essas escolhas reduzem o primeiro ciclo operacional. A inclusão posterior de nome em material enviado a parceiro, financeiro, texto de movimentação ou status jurídico exige nova decisão de conteúdo e testes de privacidade.

## Retenção operacional — P-019

A política abaixo foi aprovada pelo responsável do projeto em 25/09/2026 para o MVP interno:

- texto temporário: somente em memória e descartado ao fim da operação;
- PDF-fonte: 30 dias após aprovação ou substituição;
- carteira normalizada, vínculos, manifestos, reconciliações e versões internas: 12 meses após substituição ou encerramento da finalidade ativa;
- dados financeiros: não persistidos pelo MVP; futura ativação exige prazo específico;
- auditoria de segurança e decisões: 24 meses;
- backups: janela móvel de 30 dias, incluindo expiração coerente do conteúdo removido.

Esses prazos devem ser implementados e testados no PDF-8 antes da produção. Não haverá retenção indefinida por omissão.

## Resultado

P-018, P-020 e P-022 ficam decididas para o MVP. P-006, P-007 e P-023 ficam decididas por minimização, com financeiro, texto livre, status jurídico e visão externa fora do primeiro ciclo. P-012/P-019 foram aprovadas pelo responsável; a automação de expiração e sua restauração ainda precisam ser comprovadas no PDF-8.
