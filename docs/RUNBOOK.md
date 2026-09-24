# Runbook de automação e segurança — etapas 9–10

**Situação em 17/09/2026:** implementação e operação demonstradas apenas em desenvolvimento local, com fontes `SYNTHETIC-*`. O worker e o leitor de artefatos recusam produção. Nenhuma rotina desta etapa faz chamada ao Advbox, grava dados reais, publica relatórios reais ou envia e-mail.

## Fluxo e garantias locais

1. O ciclo diário usa a data de `America/Sao_Paulo` como chave idempotente. Uma trava consultiva transacional no PostgreSQL impede dois scans simultâneos. Um `sync_run` sintético guarda início, fim e contagens; `sync_changed_partners` guarda somente IDs técnicos dos parceiros cujo hash mudou.
2. A fonte de demonstração é `synthetic_portfolios` (cenário e revisão). Cada fonte ativa é examinada uma vez; apenas hash diferente da última versão validada gera solicitação. O portal também pode criar solicitação manual; o índice único parcial impede duas solicitações ativas para o mesmo parceiro.
3. O worker reivindica uma solicitação com `FOR UPDATE SKIP LOCKED`, token de lease e vencimento de 90 segundos. O heartbeat renova a cada 15 segundos. Job abandonado retorna à fila com backoff; após três tentativas fica `failed`. O PDF tem timeout de 240 segundos. Um worker antigo não consegue concluir depois de perder o token.
4. O relatório passa pelo contrato externo e pela allowlist já existentes. Queda de contagem conhecida de clientes/processos bloqueia a nova versão para revisão, pois ainda não existe explicação aprovada para perda de cobertura.
5. HTML e PDF são preparados em chaves sintéticas novas. Só então uma transação única grava a versão `validated` e conclui a solicitação. Se renderização, armazenamento, fonte ou commit falharem, a versão anterior não é modificada e os artefatos parciais da tentativa são removidos. Essa é uma publicação **local de prévia validada**, não publicação de produção.
6. Erros persistidos são apenas códigos como `PDF_FAILED`, `SOURCE_CHANGED`, `COUNT_REGRESSION` e `WORKER_ABANDONED`, sem texto de exceção, payload de API ou dados pessoais. O status operacional mostra somente contagens.

O hash por revisão é um simulador técnico de mudança de fonte: incrementar a revisão força recálculo, mas **não** simula uma mudança jurídica/financeira real. O `SyncRunner` Advbox paginado da etapa 5 continua separado e sem acionamento pelo worker nesta fase. Isso evita fazer a carga integral real antes do portão da etapa 11.

Uma queda abrupta do processo entre a escrita dos arquivos e o commit pode deixar arquivos locais órfãos, mas sem chave visível no banco. A política de limpeza/retensão de objetos precisa ser definida junto do storage privado de produção; não apague arquivos locais em massa sem confrontar as chaves referenciadas em `report_versions`.

## Iniciar e operar localmente

No diretório do projeto, com Docker Desktop aberto e `.env` local ignorado pelo Git:

```powershell
docker compose up -d postgres app
docker compose exec -T app alembic upgrade head
docker compose exec -T app seed-portal-demo
docker compose --profile automation up -d worker
docker compose exec -T app python -m partner_reports.jobs.automation_cli status
```

O serviço `worker` é opt-in pelo perfil `automation`: enquanto estiver ativo, verifica o ciclo diário e processa a fila continuamente. Ele é apenas local; não é o modelo de deploy Vercel. Para testar sem deixá-lo ligado:

```powershell
docker compose exec -T app python -m partner_reports.jobs.automation_cli run-now --key ensaio_local_001
docker compose exec -T app python -m partner_reports.jobs.automation_cli work-once
docker compose exec -T app python -m partner_reports.jobs.automation_cli status
docker compose exec -T app python -m partner_reports.jobs.automation_cli retry-failed
docker compose exec -T app python -m partner_reports.jobs.automation_cli bump-revision --partner-code SYNTHETIC-ONE
docker compose exec -T app python -m partner_reports.jobs.automation_cli run-now --key ensaio_local_002
```

Repita a **mesma** chave para demonstrar idempotência; use uma chave nova depois de alterar a revisão. `retry-failed` reenfileira somente solicitações `failed` de fontes sintéticas, com o contador reiniciado. Erros transitórios ainda `pending` são reprocessados automaticamente após `available_at`. Não execute `retry-failed` antes de investigar um `COUNT_REGRESSION` ou falha repetida; caso contrário, o mesmo erro voltará.

## Incidentes e recuperação

| Sintoma | Verificação segura | Ação |
|---|---|---|
| `busy` no ciclo | Outro worker detém a trava do PostgreSQL. | Não force uma segunda carga; aguarde e consulte o status. |
| Solicitação `running` sem progresso | Compare `heartbeat_at` e `lease_expires_at` no banco, sem consultar payload. | Deixe o worker recuperar após o lease; após três tentativas, investigue e use `retry-failed` apenas após corrigir a causa. |
| `PDF_FAILED` ou `JOB_FAILED` | Verifique saúde/recursos do Chromium local e contagens agregadas; não imprima exceções com dados. | Corrija o ambiente e aguarde backoff ou reenfileire a falha final. A versão anterior continua acessível. |
| `SOURCE_CHANGED` | A revisão da fonte mudou durante a renderização. | Novo ciclo com chave nova captura o hash mais recente; a tentativa antiga não publica. |
| `COUNT_REGRESSION` | A nova carteira perdeu clientes/processos em relação à última versão com contagem conhecida. | Validar a causa e regra de negócio; não contornar automaticamente. |
| Sem artefato novo | Consulte solicitação e última versão. | A falha não invalida a versão anterior. `output/` é apenas local e não tem backup de produção. |

Evite logs verbosos do banco, da API ou do navegador. Não copie `.env` para tickets. O responsável operacional, canal de alerta, retenção e restauração ainda dependem de P-011/P-012.

## Contas, sessões e trilha de segurança

O primeiro usuário deve ser criado como administrador via comando interativo, sem senha na linha de comando. Depois do bootstrap, criação, desativação, revogação de sessões e limpeza exigem autenticação de um administrador ativo com `--actor-login`; o comando pede sua senha sem eco. Execute no contêiner `app` local, apenas em terminal controlado:

```powershell
docker compose exec -it app portal-user create --login operador-demo --admin
docker compose exec -it app portal-user create --login leitor-demo --actor-login operador-demo
docker compose exec -it app portal-user revoke-sessions --login leitor-demo --actor-login operador-demo
docker compose exec -it app portal-user disable --login leitor-demo --actor-login operador-demo
docker compose exec -it app portal-user purge-expired --actor-login operador-demo
```

`disable` também elimina todas as sessões da conta; `revoke-sessions` preserva a conta ativa. A autorrevogação pelo operador em uso é recusada: use outro administrador e preserve o procedimento de recuperação antes de desativar qualquer administrador. `purge-expired` remove sessões vencidas e janelas antigas de falha de login; **não** apaga relatórios, vínculos ou auditoria. Verifique `audit_events` apenas com consultas agregadas/IDs técnicos, sem exportar conteúdo para tickets. Os eventos de segurança no log registram apenas ação, tipo de entidade e ID de correlação; a configuração de logs da Vercel ainda exige homologação.

Em suspeita de credencial Advbox exposta: suspenda sincronizações, acione o titular/operador da conta, revogue o token anterior, gere substituto no provedor, atualize somente o gerenciador de segredos ou `.env` local ignorado e reinicie consumidores. Faça um GET mínimo sanitizado de verificação e registre hora/resultado, nunca o valor do token. O procedimento completo e a resposta a vazamento estão em `docs/MODELO_DE_AMEACAS.md`. Backups e eliminação de dados reais permanecem dependentes da política aprovada P-002/P-011/P-012; não execute limpeza manual em massa.

## Limite de implantação na Vercel

O perfil Docker e os arquivos locais não podem ser usados como persistência da função Vercel. Um futuro executor de produção precisará de PostgreSQL externo, storage privado, fila/job particionado por página e uma identidade protegida para disparo. O [Cron da Vercel](https://vercel.com/docs/cron-jobs/manage-cron-jobs) pode entregar invocações duplicadas ou sobrepostas; o bloqueio e a idempotência no banco seguem obrigatórios. No [Hobby, a frequência mínima é diária e a execução pode variar dentro da hora](https://vercel.com/docs/cron-jobs/usage-and-pricing), além de o plano não estar aprovado para uso profissional. Os [limites de duração das funções](https://vercel.com/docs/functions/limitations) não permitem presumir que uma reconciliação completa e geração de todos os PDFs caberão em uma única invocação. Não há `vercel.json` de cron nem implantação configurada nesta etapa.

Antes de ligar o Advbox real: aprovar vínculos, classificações e campos externos (P-005/P-006/P-007), definir storage e identidade produtivos (P-013/P-014), aplicar as pendências produtivas da revisão de segurança da etapa 10, executar homologação controlada da etapa 11 e contratar plano Vercel adequado. SMTP não foi confirmado nem aprovado; nenhum e-mail é enviado.

## Evidência técnica local

Migration `20260917_0004` aplicada sem deriva. Testes da automação cobrem idempotência, trava distribuída entre conexões, reivindicação/lease, falha no PDF, retomada de lease abandonado, fencing de token/fonte, preservação da versão anterior, regressão de contagens e bloqueio em produção. Em 17/09/2026, `run-now` examinou quatro fontes sintéticas, enfileirou quatro mudanças e concluiu quatro jobs; a repetição da mesma chave não gerou outros jobs. O PDF de 55 casos foi inspecionado em três páginas A4, sem corte de linhas ou falha de layout. A suíte total teve 101 testes aprovados; dois avisos de depreciação vêm de dependências de teste.
