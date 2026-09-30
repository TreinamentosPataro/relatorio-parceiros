# Matriz de conteúdo e minimização — PDF-5

**Data:** 25/09/2026  
**Estado:** opção minimizada aprovada para o MVP pelo ADR-004; campos fora desse subconjunto permanecem restritos ou pendentes.  
**Escopo atual:** prévia sintética, sem dados reais nem publicação. O PDF exportado identifica a carteira; não é fonte de atributos do relatório.

## Convenções

- `PV` = prévia externa sintética existente; `I` = uso interno técnico; `B` = bloqueado; `P` = `pending_validation`; `R` = `restricted`.
- `content_source_gap` é motivo de pendência quando um campo requerido não está confirmado na fonte oficial. Falta de valor dentro de fonte completa usa `not_provided`; zero só é valor quando a fonte completa informa zero ou a contagem de conjunto elegível vazio resulta em zero.
- P-012/P-019 foram aprovadas após o dry-run PDF-7. A persistência continua limitada ao subconjunto autorizado e a produção depende da implementação/teste da expiração no PDF-8.
- Responsáveis: **negócio** = escritório responsável pelo relatório; **privacidade** = controlador/revisor de acesso; **técnico** = responsável pela integração e evidência da API. A aprovação exige registro da regra, versão, período, fonte e responsável.

## Matriz campo a campo

| Campo | Fonte oficial | Finalidade | Interna | Externa | Transformação/precedência | Ausência ou bloqueio | Sensibilidade | Retenção | Dono da aprovação |
|---|---|---|---|---|---|---|---|---|---|
| ID técnico de cliente | `/customers.id`, relação `/lawsuits[].customers` | Vínculo e contagem | I | B; apenas referência pseudonimizada | `COUNT DISTINCT` por carteira aprovada; nunca nome como chave | `pending_validation` se vínculo/fotografia incompletos | Identificador | P-012/P-019 | técnico + privacidade |
| Referência pseudonimizada de cliente | ID técnico e vínculo aprovado | Navegação na prévia | I | PV | Código local sem ID original | `pending_validation` sem vínculo aprovado | Baixa, ainda reidentificável por contexto | P-012/P-019 | privacidade P-007 |
| Nome da parte/cliente | `/customers` (campo nominal) | Identificação operacional | R até papel/acesso definidos | B | Nunca chave; sem extração do PDF | `restricted`; se fonte oficial não confirmada, `content_source_gap` | Pessoal | P-012/P-019 | negócio + privacidade P-007/P-023 |
| Papel da parte / cliente principal | Relação processo–cliente; sem semântica de polo aprovada | Definir quem mostrar | P | B | Não inferir cliente principal pela ordem | `content_source_gap` ou `pending_validation` | Pessoal/contextual | P-012/P-019 | negócio + técnico P-023 |
| Contagem de clientes únicos | IDs de clientes + vínculos aprovados | Tamanho da carteira | I | PV | `COUNT DISTINCT customer.id`; independente de processos | `pending_validation` se varredura/vínculo incompleto; zero se conjunto completo vazio | Agregada | P-012/P-019 | técnico; publicação P-007 |
| ID técnico de processo | `/lawsuits.id` | Vínculo e deduplicação | I | B; apenas referência pseudonimizada | `COUNT DISTINCT lawsuit.id` | `pending_validation` se fonte incompleta | Identificador | P-012/P-019 | técnico + privacidade |
| Referência pseudonimizada de processo | ID técnico e vínculo aprovado | Navegação na prévia | I | PV | Código local sem número CNJ | `pending_validation` sem vínculo aprovado | Baixa, contextual | P-012/P-019 | privacidade P-007 |
| Contagem de processos | IDs de processos + vínculos aprovados | Tamanho da carteira | I | PV | `COUNT DISTINCT lawsuit.id`; independente de clientes | `pending_validation` se varredura/vínculo incompleto; zero se conjunto completo vazio | Agregada | P-012/P-019 | técnico; publicação P-007 |
| Tipo/grupo de ação | `/lawsuits` tipo/grupo ID; `/settings.lawsuit_types` | Classificação operacional | P | B | Resolver ID pelo catálogo versionado; rótulo/granularidade por aprovar | `content_source_gap` para ID/catálogo ausente; `pending_validation` para mapa | Contextual | P-012/P-019 | negócio + técnico P-023 |
| Tipo de benefício | Sem campo inequívoco confirmado | Classificação de benefício | P | B | Não derivar de título ou tipo de ação | `content_source_gap` | Contextual | P-012/P-019 | negócio + técnico P-006/P-023 |
| Fase/etapa operacional | `/lawsuits` stage/step IDs; `/settings.stages` | Acompanhamento operacional | P | B | Catálogo versionado; não equivale a status jurídico | `content_source_gap` se ID/catálogo ausente; senão `pending_validation` | Contextual | P-012/P-019 | negócio + técnico P-023 |
| Status jurídico/executivo | Regra de negócio ainda ausente | Síntese jurídica | P | B | Não inferir da fase, ação ou movimento | `pending_validation` | Contextual/sensível | P-012/P-019 | negócio P-006/P-007 |
| Tipo de entrada/saída | `/transactions.entry_type` | Detalhe financeiro por processo | P | B | Sem atribuir receita/repasse por aproximação | `not_provided` se valor ausente; regra `pending_validation` | Financeiro | P-012/P-019 | financeiro + privacidade P-006/P-007 |
| Vencimento | `/transactions.date_due` | Cronologia financeira | P | B | Data oficial, sem inferir atraso | `not_provided` se nulo | Financeiro | P-012/P-019 | financeiro + privacidade |
| Pagamento | `/transactions.date_payment` | Cronologia financeira | P | B | Data oficial; nulo não implica não pagamento | `not_provided` se nulo | Financeiro | P-012/P-019 | financeiro + privacidade |
| Competência | `/transactions.competence` | Recorte financeiro | P | B | Período e interpretação por aprovar | `not_provided` se nulo | Financeiro | P-012/P-019 | financeiro P-006 |
| Categoria | `/transactions.category` | Agrupamento financeiro | P | B | Catálogo/granularidade por aprovar | `not_provided` se nulo; classificação `pending_validation` | Financeiro | P-012/P-019 | financeiro P-006 |
| ID técnico de lançamento/parcela | `/transactions.id`; parcela específica não confirmada | Deduplicação, eventual detalhe | I para ID; parcela P | B | ID não é número público nem prova parcelamento | Parcela `content_source_gap` | Identificador financeiro | P-012/P-019 | financeiro + técnico P-023 |
| Valor e sinal | `/transactions.amount` e `entry_type` | Detalhe financeiro | P | B | `Decimal`; zero explícito só se fornecido; sinal/regra pendentes | `not_provided` se nulo; `pending_validation` sem regra | Financeiro | P-012/P-019 | financeiro P-006 |
| Registro interno | `/transactions.is_internal` | Segregar visibilidade | I técnico | B sempre por herança | Tratar `true` como interno; `false` não concede publicação | `pending_validation` se nulo | Financeiro restrito | P-012/P-019 | financeiro + privacidade P-007 |
| Total por processo / devido ao parceiro | Transações oficiais + regra não aprovada | Síntese financeira | P | B | Sem soma, rateio ou saldo até fórmula/recorte/autor aprovados | `pending_validation`, valor nulo; nunca zero por falta de regra | Financeiro | P-012/P-019 | financeiro + negócio P-006/P-007 |
| Data do último movimento cronológico | `/last_movements.date` | Recência informativa | I | PV | Maior data até `as_of`; não define relevância | `not_provided` sem movimento em fonte completa | Contextual | P-012/P-019 | técnico; publicação P-007 |
| Data do movimento relevante/manual | Endpoints `/last_movements`, `/movements`, `/history`; origem manual não definida | Destaque jurídico | P | B | Exige critério e fonte aprovados; não substituir pelo cronológico | `content_source_gap` para origem; `pending_validation` para relevância | Contextual | P-012/P-019 | negócio + técnico P-023 |
| Título/texto do movimento | `/last_movements.title`; demais textos livres não aprovados | Contexto jurídico | R | B | Sem texto livre no modelo externo; futuro resumo exige regra, limite e revisão | `restricted` | Pessoal e potencialmente sensível | P-012/P-019 | negócio + privacidade P-007/P-023 |
| CPF completo, contatos, saúde, credenciais, notas internas | Fontes diversas; sem finalidade aprovada | Nenhuma na prévia | R | B | Bloqueio por allowlist, inclusive HTML/PDF | `restricted` | Alto risco | Sem nova persistência | privacidade P-007 |
| Divergência PDF/API | PDF só indica composição; API fornece atributos | Alerta de qualidade | I como contagem/estado | B até revisão | Nunca resolver divergência copiando valor do PDF | `pending_validation`; impede publicação | Técnico/contextual | Contrato de importação | técnico + revisor |

## Portão de publicação e decisões

`publication_ready` permanece falso. Sua futura liberação exige lote aprovado, fotografia completa, nenhuma ambiguidade, matriz de conteúdo aprovada com regra/versão/responsável, P-006/P-007/P-023 resolvidas para os campos exibidos e revisão de qualquer divergência PDF/API. Um campo sem fonte oficial fica nulo com motivo `content_source_gap`; ele não é preenchido a partir do PDF.

Perguntas objetivas ainda abertas: (1) qual papel processual identifica a parte exibida e quem pode ver nome; (2) qual catálogo/agrupamento de ação e benefício; (3) fase operacional bruta ou mapa versionado e quem aprova status jurídico; (4) quais transações, sinais, categorias, períodos, parcelas, `is_internal`, fórmulas e papéis; (5) qual endpoint/origem, critério de relevância e política de texto para movimentos; (6) período de retenção e responsável por P-012/P-019. As respostas devem atualizar esta matriz antes de qualquer nova exposição de valor.
