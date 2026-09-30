# Cobertura sanitizada da API oficial para PDF-3

**Data:** 25/09/2026  
**Fonte:** caminhos de campos observados em `docs/ADVBOX_API_AUDIT.md`; nenhum valor, nome, número processual ou payload foi copiado.  
**Estado:** contrato técnico para reconciliação; conteúdo e visibilidade dependem de P-006/P-007/P-023 e da etapa PDF-5.

| Prioridade | Endpoint e campos oficiais confirmados | Disponibilidade técnica | Lacuna e decisão posterior |
|---|---|---|---|
| Parte/cliente | `/lawsuits`: `data[].customers[].customer_id`; `/customers`: `data[].id`, `data[].name` | Relação por ID e campo nominal observados; o coletor PDF-3 usa somente IDs e contagens | Papel processual, cliente principal, acesso nominal e visibilidade externa dependem de P-007/P-023. Nome não é chave de reconciliação. |
| Tipo de ação/benefício | `/lawsuits`: `data[].type_lawsuit_id`, `data[].group_id`, `data[].type`, `data[].group`; `/settings`: `lawsuit_types[].id`, `type`, `group` | ID e catálogo observados | Campo oficial específico de benefício e agrupamento de negócio não confirmados. Rótulo publicável depende de catálogo aprovado. |
| Fase | `/lawsuits`: `data[].stages_id`, `data[].stage`, `data[].steps_id`, `data[].step`; `/settings`: `stages[].id`, `stage`, `step` | Fase/etapa operacionais observadas | Não há equivalência aprovada com status jurídico. P-006/P-023 definem semântica e mapa. |
| Financeiro por processo | `/transactions`: `data[].id`, `data[].lawsuit_id`, `data[].amount`, `data[].entry_type`, `data[].category`, `data[].competence`, `data[].date_due`, `data[].date_payment`, `data[].is_internal` | Lançamento e vínculo técnico observados; PDF-3 conta apenas registros ligados a IDs reconciliados | Fórmula, sinal, parcela, rateio, visibilidade e tratamento de registro interno aguardam P-006/P-007/P-023. `description` e `name` não entram na projeção. |
| Andamento | `/last_movements`: `data[].lawsuit_id`, `data[].date`, `data[].title`; `/movements/{lawsuit_id}` e `/history/{lawsuit_id}` confirmados apenas para leitura individual | Último movimento global tem paginação confirmada; PDF-3 conta apenas registros ligados a IDs reconciliados | “Manual”, “mais recente” e “relevante” não são equivalentes comprovados. Texto `title` permanece restrito; sem resumo publicável aprovado. |

## Uso na reconciliação

`/lawsuits` é a única origem de candidatos. O coletor conserva em memória apenas ID técnico, número processual canônico, pasta exata, IDs de clientes e hash dos campos normalizados. `/customers`, `/transactions` e `/last_movements` são percorridos pelo cliente GET-only compartilhado para contagens técnicas de cobertura dos itens já conciliados. Campos nominais, descrição, valor e título não são retornados pelo objeto de cobertura nem gravados pelo fluxo PDF-3.

O transporte existente limita o processo a 20 GET/min, inclusive retentativas, valida paginação e trata 429, timeout e `Retry-After`. Duas leituras completas e idênticas de `/lawsuits` são exigidas antes da classificação. A API usa offset/limit e não ofereceu cursor ou snapshot transacional: as duas leituras detectam mudança observável, mas não provam isolamento temporal absoluto. Uma mudança detectada invalida o processamento e exige reinício da fotografia. No `private_pilot`, a fotografia global permanece em memória; a persistência seleciona somente candidatos `matched` e guarda ID, número canônico, pasta e IDs técnicos de clientes. Todo candidato não conciliado e os demais campos são descartados.

Nenhum dry-run real do novo fluxo PDF foi executado nesta etapa. O dry-run implementado em código retorna exclusivamente as cinco contagens de resultado. A persistência de propostas está bloqueada em produção e para parceiros sem ID técnico `SYNTHETIC-*`; não cria vínculo ativo nem relatório. P-022 continua necessária para tratamento de exceções reais.
