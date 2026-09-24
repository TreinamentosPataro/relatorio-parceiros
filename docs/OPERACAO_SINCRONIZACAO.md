# Operação da sincronização Advbox — etapa 5

## Escopo e limites

O comando é isolado da aplicação web e usa somente `GET /customers`, `GET /lawsuits`, `GET /transactions` e `GET /last_movements`, confirmados na auditoria. Um único cliente HTTP percorre as coleções nesta ordem, com páginas de até 100 registros e teto de 20 requisições por minuto **por processo**, inclusive retentativas. Timeout, backoff exponencial com jitter e `Retry-After` numérico ou HTTP-date são respeitados. Não há varredura por parceiro. Os endpoints `movements/{lawsuit_id}` e `history/{lawsuit_id}` não entram nesta carga global: não foi confirmada paginação/cursor global para eles.

A API auditada não ofereceu campo confiável de última atualização nem cursor estável. Por isso `incremental` reconcilia integralmente as quatro coleções, mas só atualiza linhas cujo hash dos campos normalizados mudou; andamentos são deduplicados por fingerprint de processo/data/título. Ausência de um registro em uma varredura **não** é interpretada como exclusão: a paginação por offset sem snapshot não permite provar isso. Se `totalCount` mudar dentro do lote, a execução para e precisa de novo lote; uma reordenação sem mudança de total ainda pode exigir verificação posterior. A conversão de datas/horas sem fuso assume `America/Sao_Paulo`, hipótese pendente de validação com o fornecedor.

Não há publicação de relatórios nesta etapa. Vínculos com parceiros são somente os mapeamentos locais `active` e vigentes da ADR-001. Nenhum cliente ou processo é atribuído automaticamente por origem, pasta ou responsável. As referências a clientes/processos não encontrados geram pendência reprocessável por página, sem expor os IDs na tabela de erros. `sync_changed_partners` guarda apenas o parceiro técnico impactado, para a futura etapa de relatórios.

## Comandos

Executar no diretório do projeto com Docker Desktop aberto e `.env` local configurado. O `.env` é ignorado pelo Git e não deve ser impresso ou copiado para logs.

```powershell
docker compose run --rm app python -m partner_reports.jobs.sync_cli dry-run --max-pages 1
docker compose exec -T app python -m partner_reports.jobs.homologation_cli
docker compose run --rm app python -m partner_reports.jobs.sync_cli initial --batch-key lote_tecnico_001
docker compose run --rm app python -m partner_reports.jobs.sync_cli incremental --batch-key lote_tecnico_002
docker compose run --rm app python -m partner_reports.jobs.sync_cli reprocess --batch-key lote_tecnico_001
```

`--resource customers|lawsuits|transactions` pode ser repetido para uma operação dirigida; manter a ordem de dependência quando for carga inicial. `--max-pages N` limita páginas **por recurso** e deixa uma execução persistida em `partial` para retomada com a mesma chave. O `dry-run` não grava linhas nem checkpoints. Sem `--batch-key`, o CLI gera uma chave técnica e a exibe; guarde-a para retomar. Não execute dois processos simultâneos com a mesma chave. O agendamento e a exclusão mútua distribuída pertencem à etapa 9.

`homologation_cli` percorre integralmente as quatro coleções confirmadas e emite um único JSON com contagens de validação, vínculo, financeiro, idade do último andamento e métricas de transporte. Mantém somente IDs técnicos/datas em memória durante o processo; não grava payload, checkpoint ou entidade. Parceiros `SYNTHETIC-*` são excluídos da governança real. O resultado sanitizado da execução de 21/09/2026 está em `docs/HOMOLOGACAO.md`. A presença do comando não autoriza `initial`.

Para retomar uma falha de página, repita `initial` ou `incremental` com a **mesma** chave. `reprocess` volta ao menor offset com erro não resolvido; também pode reprocessar referências faltantes depois da correção da origem. Uma página só avança o checkpoint depois de validar todos os registros e confirmar upserts, relações, erros de referência e contagens na mesma transação. Falha de página reverte tudo da página e registra um erro sanitizado em transação separada. `sync_runs` mostra início/fim, status, total esperado, offset e contagens; `sync_errors` guarda código, offset e resolução, sem resposta bruta.

Se o total da API mudar entre a execução interrompida e sua retomada, não force o offset antigo: abra novo lote com outra chave para reconciliar desde zero. Lotes repetidos não duplicam entidades porque clientes, processos e transações usam ID técnico Advbox único e as relações têm unicidade própria. Um novo lote é necessário para uma nova reconciliação; repetir uma chave `succeeded` apenas retorna o resumo existente.

## Validação desta etapa

- Migration reversível `20260916_0002` aplicada ao PostgreSQL local.
- Testes somente com dados sintéticos cobrem três páginas, limite compartilhado, 429/`Retry-After`, timeout, resposta inválida, dead-letter/reprocessamento, retomada, repetição idempotente, relações e valor financeiro zero preservado como `Decimal`.
- Leitura real **limitada**, em modo `dry-run`, de uma página por coleção em 16/09/2026: 100 clientes (total informado 4.213), 100 processos (total 4.353), 100 transações (total 12.721) e 100 últimos andamentos (total 4.302). Nenhum registro real foi persistido nesta validação.
- A carga real integral permanece para a etapa de homologação autorizada, junto da resolução das referências ausentes e aprovação dos vínculos de parceiros. Não executar publicação ou cálculo financeiro com carteira sem vínculo único.
