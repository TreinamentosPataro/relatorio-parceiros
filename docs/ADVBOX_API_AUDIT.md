# Auditoria segura da API Advbox

**Execução UTC:** 2026-09-21T14:43:34.195691+00:00 a 2026-09-21T14:43:52.444915+00:00  
**Modo:** somente leitura (`GET`), amostra mínima e sem persistência de respostas brutas  
**Teto aplicado:** 20 requisições/minuto, com timeout e retentativa limitada

## Resultado sanitizado por recurso

| Recurso | Endpoint | HTTP | Duração (ms) | Itens na amostra | Paginação/erro seguro |
|---|---|---:|---:|---:|---|
| settings | `/settings` | 200 | 878 | 1 | não detectada na amostra |
| customers | `/customers` | 200 | 321 | 1 | offset/limit; total=4228; limit=1; offset=0 |
| lawsuits | `/lawsuits` | 200 | 514 | 1 | offset/limit; total=4365; limit=1; offset=0 |
| last_movements | `/last_movements` | 200 | 396 | 1 | offset/limit; total=4320; limit=1; offset=0 |
| transactions | `/transactions` | 200 | 679 | 1 | offset/limit; total=12899; limit=1; offset=0 |
| movements | `/movements/{lawsuit_id}` | 200 | 292 | 109 | não detectada na amostra |
| history | `/history/{lawsuit_id}` | 200 | 244 | 20 | não detectada na amostra |

## Esquema observado

Somente caminhos de campos, tipos e contagens de nulos são registrados. Valores, identificadores e conteúdo textual não são gravados.

### settings

| Campo | Tipos | Observações | Nulos |
|---|---|---:|---:|
| `financial` | object | 1 | 0 |
| `financial.banks` | array | 1 | 0 |
| `financial.banks[]` | object | 8 | 0 |
| `financial.banks[].id` | integer | 8 | 0 |
| `financial.banks[].institution` | null, string | 8 | 5 |
| `financial.banks[].name` | string | 8 | 0 |
| `financial.categories` | array | 1 | 0 |
| `financial.categories[]` | object | 20 | 0 |
| `financial.categories[].category` | string | 20 | 0 |
| `financial.categories[].id` | integer | 20 | 0 |
| `financial.categories[].type` | string | 20 | 0 |
| `financial.cost_centers` | array | 1 | 0 |
| `financial.cost_centers[]` | object | 20 | 0 |
| `financial.cost_centers[].cost_center` | string | 20 | 0 |
| `financial.cost_centers[].id` | integer | 20 | 0 |
| `financial.departments` | array | 1 | 0 |
| `financial.departments[]` | object | 4 | 0 |
| `financial.departments[].id` | integer | 4 | 0 |
| `financial.departments[].sector` | string | 4 | 0 |
| `lawsuit_types` | array | 1 | 0 |
| `lawsuit_types[]` | object | 20 | 0 |
| `lawsuit_types[].group` | string | 20 | 0 |
| `lawsuit_types[].id` | integer | 20 | 0 |
| `lawsuit_types[].type` | string | 20 | 0 |
| `origins` | array | 1 | 0 |
| `origins[]` | object | 20 | 0 |
| `origins[].id` | integer | 20 | 0 |
| `origins[].origin` | string | 20 | 0 |
| `stages` | array | 1 | 0 |
| `stages[]` | object | 20 | 0 |
| `stages[].id` | integer | 20 | 0 |
| `stages[].stage` | string | 20 | 0 |
| `stages[].step` | string | 20 | 0 |
| `tasks` | array | 1 | 0 |
| `tasks[]` | object | 20 | 0 |
| `tasks[].id` | integer | 20 | 0 |
| `tasks[].reward` | integer | 20 | 0 |
| `tasks[].task` | string | 20 | 0 |
| `users` | array | 1 | 0 |
| `users[]` | object | 20 | 0 |
| `users[].cellphone` | null, string | 20 | 1 |
| `users[].email` | string | 20 | 0 |
| `users[].id` | integer | 20 | 0 |
| `users[].name` | string | 20 | 0 |

IDs candidatos: `financial.banks[].id`, `financial.categories[].id`, `financial.cost_centers[].id`, `financial.departments[].id`, `lawsuit_types[].id`, `origins[].id`, `stages[].id`, `tasks[].id`, `users[].id`.

Campos semanticamente candidatos ao vínculo: `origins`, `origins[]`, `origins[].id`, `origins[].origin`, `stages`, `stages[]`, `stages[].id`, `stages[].stage`, `stages[].step`.

### customers

| Campo | Tipos | Observações | Nulos |
|---|---|---:|---:|
| `data` | array | 1 | 0 |
| `data[]` | object | 1 | 0 |
| `data[].birthdate` | string | 1 | 0 |
| `data[].cellphone` | null | 1 | 1 |
| `data[].city` | null | 1 | 1 |
| `data[].civil_status` | null | 1 | 1 |
| `data[].country` | string | 1 | 0 |
| `data[].created_at` | string | 1 | 0 |
| `data[].document` | null | 1 | 1 |
| `data[].email` | string | 1 | 0 |
| `data[].gender` | null | 1 | 1 |
| `data[].id` | integer | 1 | 0 |
| `data[].identification` | string | 1 | 0 |
| `data[].lawsuits` | array | 1 | 0 |
| `data[].name` | string | 1 | 0 |
| `data[].notes` | null | 1 | 1 |
| `data[].number_cid` | null | 1 | 1 |
| `data[].number_ctps` | null | 1 | 1 |
| `data[].number_pis` | null | 1 | 1 |
| `data[].occupation` | null | 1 | 1 |
| `data[].origin` | string | 1 | 0 |
| `data[].phone` | null | 1 | 1 |
| `data[].postalcode` | null | 1 | 1 |
| `data[].region` | null | 1 | 1 |
| `data[].state` | null | 1 | 1 |
| `data[].street` | null | 1 | 1 |
| `limit` | integer | 1 | 0 |
| `offset` | integer | 1 | 0 |
| `query` | object | 1 | 0 |
| `query.limit` | string | 1 | 0 |
| `query.offset` | string | 1 | 0 |
| `totalCount` | integer | 1 | 0 |

IDs candidatos: `data[].id`.

Datas candidatas: `data[].birthdate`, `data[].created_at`.

Campos semanticamente candidatos ao vínculo: `data[].origin`.

### lawsuits

| Campo | Tipos | Observações | Nulos |
|---|---|---:|---:|
| `data` | array | 1 | 0 |
| `data[]` | object | 1 | 0 |
| `data[].contingency` | null | 1 | 1 |
| `data[].created_at` | string | 1 | 0 |
| `data[].customers` | array | 1 | 0 |
| `data[].customers[]` | object | 2 | 0 |
| `data[].customers[].customer_id` | integer | 2 | 0 |
| `data[].customers[].identification` | null, string | 2 | 1 |
| `data[].customers[].name` | string | 2 | 0 |
| `data[].customers[].origin` | string | 2 | 0 |
| `data[].exit_execution` | string | 1 | 0 |
| `data[].exit_production` | string | 1 | 0 |
| `data[].fees_expec` | null | 1 | 1 |
| `data[].fees_money` | null | 1 | 1 |
| `data[].folder` | string | 1 | 0 |
| `data[].group` | string | 1 | 0 |
| `data[].group_id` | integer | 1 | 0 |
| `data[].id` | integer | 1 | 0 |
| `data[].notes` | string | 1 | 0 |
| `data[].process_date` | string | 1 | 0 |
| `data[].process_number` | string | 1 | 0 |
| `data[].protocol_number` | string | 1 | 0 |
| `data[].responsible` | string | 1 | 0 |
| `data[].responsible_id` | integer | 1 | 0 |
| `data[].stage` | string | 1 | 0 |
| `data[].stages_id` | integer | 1 | 0 |
| `data[].status_closure` | string | 1 | 0 |
| `data[].step` | string | 1 | 0 |
| `data[].steps_id` | integer | 1 | 0 |
| `data[].type` | string | 1 | 0 |
| `data[].type_lawsuit_id` | integer | 1 | 0 |
| `limit` | integer | 1 | 0 |
| `offset` | integer | 1 | 0 |
| `query` | object | 1 | 0 |
| `query.limit` | string | 1 | 0 |
| `query.offset` | string | 1 | 0 |
| `totalCount` | integer | 1 | 0 |

IDs candidatos: `data[].customers[].customer_id`, `data[].group_id`, `data[].id`, `data[].responsible_id`, `data[].stages_id`, `data[].steps_id`, `data[].type_lawsuit_id`.

Datas candidatas: `data[].created_at`, `data[].process_date`.

Campos semanticamente candidatos ao vínculo: `data[].customers[].origin`, `data[].folder`, `data[].responsible`, `data[].responsible_id`, `data[].stage`, `data[].stages_id`.

### last_movements

| Campo | Tipos | Observações | Nulos |
|---|---|---:|---:|
| `data` | array | 1 | 0 |
| `data[]` | object | 1 | 0 |
| `data[].customers` | string | 1 | 0 |
| `data[].date` | string | 1 | 0 |
| `data[].lawsuit_id` | integer | 1 | 0 |
| `data[].process_number` | null | 1 | 1 |
| `data[].protocol_number` | null | 1 | 1 |
| `data[].title` | string | 1 | 0 |
| `limit` | integer | 1 | 0 |
| `offset` | integer | 1 | 0 |
| `totalCount` | integer | 1 | 0 |

IDs candidatos: `data[].lawsuit_id`.

Datas candidatas: `data[].date`.

### transactions

| Campo | Tipos | Observações | Nulos |
|---|---|---:|---:|
| `data` | array | 1 | 0 |
| `data[]` | object | 1 | 0 |
| `data[].amount` | number | 1 | 0 |
| `data[].category` | string | 1 | 0 |
| `data[].competence` | string | 1 | 0 |
| `data[].cost_center` | string | 1 | 0 |
| `data[].credit_bank` | null | 1 | 1 |
| `data[].date_due` | string | 1 | 0 |
| `data[].date_payment` | string | 1 | 0 |
| `data[].debit_bank` | string | 1 | 0 |
| `data[].description` | string | 1 | 0 |
| `data[].entry_type` | string | 1 | 0 |
| `data[].id` | integer | 1 | 0 |
| `data[].identification` | string | 1 | 0 |
| `data[].is_internal` | boolean | 1 | 0 |
| `data[].is_recurrent` | boolean | 1 | 0 |
| `data[].lawsuit_id` | integer | 1 | 0 |
| `data[].name` | string | 1 | 0 |
| `data[].process_number` | null | 1 | 1 |
| `data[].protocol_number` | string | 1 | 0 |
| `data[].responsible` | string | 1 | 0 |
| `limit` | integer | 1 | 0 |
| `offset` | integer | 1 | 0 |
| `query` | object | 1 | 0 |
| `query.limit` | string | 1 | 0 |
| `query.offset` | string | 1 | 0 |
| `totalCount` | integer | 1 | 0 |

IDs candidatos: `data[].id`, `data[].lawsuit_id`.

Datas candidatas: `data[].date_due`, `data[].date_payment`.

Campos semanticamente candidatos ao vínculo: `data[].responsible`.

### movements

| Campo | Tipos | Observações | Nulos |
|---|---|---:|---:|
| `data` | array | 1 | 0 |
| `data[]` | object | 20 | 0 |
| `data[].customers` | string | 20 | 0 |
| `data[].date` | string | 20 | 0 |
| `data[].header` | null | 20 | 20 |
| `data[].lawsuit_id` | integer | 20 | 0 |
| `data[].process_number` | string | 20 | 0 |
| `data[].protocol_number` | string | 20 | 0 |
| `data[].title` | string | 20 | 0 |
| `query` | array | 1 | 0 |

IDs candidatos: `data[].lawsuit_id`.

Datas candidatas: `data[].date`.

### history

| Campo | Tipos | Observações | Nulos |
|---|---|---:|---:|
| `data` | array | 1 | 0 |
| `data[]` | object | 20 | 0 |
| `data[].author` | string | 20 | 0 |
| `data[].comments` | null, string | 20 | 7 |
| `data[].created_at` | string | 20 | 0 |
| `data[].customers` | string | 20 | 0 |
| `data[].date_deadline` | null, string | 20 | 18 |
| `data[].local` | null, string | 20 | 15 |
| `data[].process_number` | string | 20 | 0 |
| `data[].protocol_number` | string | 20 | 0 |
| `data[].responsible` | string | 20 | 0 |
| `data[].reward` | integer | 20 | 0 |
| `data[].start` | string | 20 | 0 |
| `data[].task` | string | 20 | 0 |
| `status` | string | 1 | 0 |

Datas candidatas: `data[].created_at`, `data[].date_deadline`.

Campos semanticamente candidatos ao vínculo: `data[].responsible`.

## Como percorrer coleções

Quando `data`, `limit`, `offset` e `totalCount` forem observados, percorrer por `offset += limit` até alcançar `totalCount`, mantendo IDs estáveis e deduplicação. Esta auditoria não executa a carga integral.

## Segurança aplicada

- Nenhum método mutável é exposto pelo auditor.
- Redirecionamentos de login e HTTP 401 são falhas de autenticação.
- HTTP 403/404 são classificados explicitamente; HTTP 429 e 5xx usam retentativa limitada.
- O relatório não contém token, cabeçalhos, URLs com IDs, valores de campos ou respostas brutas.
