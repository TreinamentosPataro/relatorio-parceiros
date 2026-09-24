# ADR-001 — Vínculo parceiro–carteira

- **Status:** aceito
- **Data:** 15/09/2026
- **Escopo:** associação multiparceiro de clientes e processos do Advbox

## Contexto

A API real foi auditada em modo somente leitura. A amostra autenticada e a varredura integral não encontraram `partner_id` nem relacionamento oficial equivalente em nenhum dos 4.210 clientes ou 4.350 processos disponíveis. Os IDs técnicos das duas coleções não apresentaram duplicidade.

Os campos indiretos não atendem ao contrato necessário:

- `origin` existe nos 4.210 clientes, mas 4.167 dos 4.350 processos reúnem clientes com múltiplas origens; somente 183 processos possuem uma origem única;
- `folder` está preenchido em 4.200 processos e ausente em 150, além de ser texto sem semântica de parceiro aprovada;
- `responsible_id` cobre os 4.350 processos, mas referencia responsável operacional, não parceiro;
- 21 IDs de clientes citados por processos não aparecem na coleção atual de clientes;
- uma única fotografia da API não prova estabilidade temporal de origem, pasta ou responsável.

Valores de campos, nomes e identificadores reais não foram persistidos nos relatórios. As evidências completas em contagens estão em `docs/VINCULO_PARCEIRO_CARTEIRA_VALIDACAO.md`.

## Alternativas consideradas

### 1. Relacionamento oficial da API

Usar `partner_id` ou relação oficial seria a alternativa preferencial. Foi rejeitada para o contrato atual porque a varredura integral encontrou zero ocorrências de campo direto nos clientes e processos.

### 2. Inferência por origem

Foi rejeitada como regra automática. Embora tenha cobertura total nos clientes, produz múltiplos candidatos em 4.167 processos e não há aprovação funcional de que origem represente parceiro.

### 3. Inferência por pasta ou responsável

Foi rejeitada. Pasta é texto livre e não cobre toda a carteira; responsável representa usuário operacional. Nenhum dos dois possui contrato funcional ou técnico que prove parceiro, unicidade e estabilidade.

### 4. Inferência por nome ou outro texto livre

Foi rejeitada por construção. Nome de pessoa não será chave técnica e texto livre não determinará vínculo sem regra formal, fonte governada e testes de conflito.

### 5. Mapeamento administrável por IDs estáveis

Foi aceita. É a única alternativa que permite representar ausência, vigência, origem da decisão, correções e auditoria sem fabricar equivalência entre campos do Advbox.

## Decisão

Adotar uma tabela governada de mapeamento com, no mínimo:

| Campo | Regra |
|---|---|
| `partner_external_id` | Identificador técnico estável do parceiro; obrigatório e nunca derivado exclusivamente do nome |
| `partner_name` | Nome de exibição; não participa da chave nem da decisão de vínculo |
| `advbox_entity_type` | Enumeração `customer` ou `lawsuit` |
| `advbox_entity_id` | ID técnico estável observado na API |
| `valid_from` | Início inclusivo da vigência |
| `valid_to` | Fim inclusivo ou nulo para vigência aberta |
| `source` | Origem governada, como `manual_csv`, `admin` ou futura `advbox_official` |
| `status` | `active`, `inactive` ou `pending` |
| `created_at`, `created_by` | Auditoria de criação |
| `updated_at`, `updated_by` | Auditoria da última alteração |

A migration da etapa 4 deverá impedir períodos ativos sobrepostos para a mesma entidade quando apontarem para parceiros diferentes. Importação por CSV validado e tela administrativa ficam para fases posteriores, conforme o plano; nenhuma delas aceitará nomes como chave.

## Regra determinística

Para uma data de referência:

1. selecionar somente mapeamentos `active` cuja vigência contenha a data;
2. para cada cliente, reunir os `partner_external_id` associados ao seu `customer.id`;
3. para cada processo, reunir os parceiros associados ao seu `lawsuit.id` e aos `customer_id` relacionados;
4. zero parceiros distintos resulta em `sem vínculo`;
5. exatamente um parceiro distinto resulta em `vinculado`;
6. mais de um parceiro distinto resulta em `múltiplos vínculos`, bloqueia publicação e exige correção;
7. um mapeamento cujo `advbox_entity_id` não existe resulta em `referência inexistente` e não produz vínculo;
8. não existe precedência silenciosa entre vínculo de processo e de cliente: divergência deve aparecer como ambiguidade.

O validador retorna exclusivamente as contagens `vinculados`, `sem vínculo`, `múltiplos vínculos` e `referências inexistentes`. Ele não retorna nomes, IDs ou detalhes das entidades.

## Resultado da validação atual

Sem uma carga inicial de mapeamento, a regra classificou:

| Entidade | Total | Vinculados | Sem vínculo | Múltiplos vínculos |
|---|---:|---:|---:|---:|
| Clientes | 4.210 | 0 | 4.210 | 0 |
| Processos | 4.350 | 0 | 4.350 | 0 |

Referências inexistentes no mapeamento: 0. Todos os registros foram classificados uma única vez e não existe associação ambígua, mas a carteira ainda não está apta a publicar relatórios porque permanece integralmente sem vínculo.

## Consequências

- O vínculo deixa de depender de convenções frágeis do cadastro do Advbox.
- A carga inicial e as correções passam a exigir governança operacional.
- Relatórios só podem ser publicados para processos com exatamente um parceiro.
- Registros sem vínculo continuam visíveis em contagens de qualidade, nunca como zero silencioso.
- Uma futura relação oficial do Advbox poderá ser incorporada como fonte, após auditoria e reconciliação, sem trocar a chave interna.
- A etapa 4 deverá materializar integridade, vigência e auditoria no PostgreSQL.

## Plano de correção de exceções

1. Resolver as 21 referências processo–cliente ausentes antes de usá-las em mapeamento.
2. Preparar carga inicial governada com IDs técnicos e responsável pela aprovação.
3. Rejeitar importações com entidade inexistente, intervalo inválido ou sobreposição conflitante.
4. Bloquear publicação quando o validador encontrar qualquer múltiplo vínculo.
5. Manter itens sem vínculo em fila explícita de correção, com contagens por execução.
6. Após uma correção, revalidar e reprocessar apenas as entidades afetadas, preservando os campos de auditoria.

## Critério operacional para avançar

A regra e o validador estão definidos, e 100% da listagem atual foi classificada sem ambiguidade. A implementação do banco pode prosseguir, mas sincronização e publicação permanecem bloqueadas até a carga inicial produzir vínculos únicos para a carteira elegível ou exceções sem vínculo formalmente aceitas.
