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

## Ensaio PDF-6: lote aprovado até versão privada

Somente com lote e parceiro sintéticos aprovados no portal local, o administrador usa **Solicitar relatório** no detalhe da importação. O worker existente reivindica a solicitação vinculada ao lote, confere fotografia e vínculos, gera HTML/PDF pelo contrato minimizado e registra uma versão `validated` com `pdf_batch_id` e chave de revisão. O detalhe do parceiro mostra origem genérica, período, pendências e histórico. Download autenticado confere o hash conjunto dos artefatos; nunca há rota para baixar o PDF-fonte. Repetir a solicitação para a mesma revisão não cria outra versão. `SOURCE_UNAVAILABLE`, `UNSAFE_REPORT`, `PDF_FAILED`, `SOURCE_CHANGED` ou `COMMIT_FAILED` deixam a última versão válida acessível.

Uma versão anterior pode ser restaurada por administrador no detalhe do parceiro. O portal exige CSRF, confirmação, parceiro dentro do escopo configurado e artefatos existentes/íntegros, registra auditoria e marca versões posteriores como `superseded`; a restauração pode ser revertida selecionando novamente a versão posterior. No `private_pilot`, o hash conjunto HTML/PDF é obrigatório e uma divergência recusa a operação. Não restaure uma versão cuja fonte ou política esteja em dúvida. A validação deste fluxo ainda é local; a VPS permanece em `synthetic_only`. Consulte `docs/RELATORIO_PDF6.md` para a chave de revisão e as lacunas de completude.

## Iniciar e operar localmente

No diretório do projeto, com Docker Desktop aberto e `.env` local ignorado pelo Git:

```powershell
docker compose up -d postgres app
docker compose exec -T app alembic upgrade head
docker compose exec -T app seed-portal-demo
docker compose --profile automation up -d worker
docker compose exec -T app python -m partner_reports.jobs.automation_cli status
```

O serviço `worker` é opt-in pelo perfil `automation`: enquanto estiver ativo, verifica o ciclo diário e processa a fila continuamente. Ele ainda é apenas sintético; a composição produtiva da VPS será criada no PDF-8. Para testar sem deixá-lo ligado:

```powershell
docker compose exec -T app python -m partner_reports.jobs.automation_cli run-now --key ensaio_local_001
docker compose exec -T app python -m partner_reports.jobs.automation_cli work-once
docker compose exec -T app python -m partner_reports.jobs.automation_cli status
docker compose exec -T app python -m partner_reports.jobs.automation_cli retry-failed
docker compose exec -T app python -m partner_reports.jobs.automation_cli bump-revision --partner-code SYNTHETIC-ONE
docker compose exec -T app python -m partner_reports.jobs.automation_cli run-now --key ensaio_local_002
```

Repita a **mesma** chave para demonstrar idempotência; use uma chave nova depois de alterar a revisão. `retry-failed` reenfileira somente solicitações `failed` de fontes sintéticas, com o contador reiniciado. Erros transitórios ainda `pending` são reprocessados automaticamente após `available_at`. Não execute `retry-failed` antes de investigar um `COUNT_REGRESSION` ou falha repetida; caso contrário, o mesmo erro voltará.

### Worker de importação no `private_pilot`

No modo privado, `work-once`, `status`, `retry-failed` e `worker-loop` operam primeiro a fila de importações e depois a fila de relatórios, sempre limitadas à allowlist. `run-now` e `bump-revision` continuam exclusivos do ensaio sintético. O worker valida novamente o escopo, usa lease/heartbeat, no máximo três tentativas e códigos de erro catalogados. Uma falha GET depois do parse volta para a fila preservando o manifesto confirmado; um lease abandonado também é recuperado. Relatórios privados usam somente chaves opacas `private/generated/*` no volume protegido e permanecem `validated`, nunca publicados automaticamente.

O token deve existir somente em `deploy/advbox.env`, criado a partir de `deploy/advbox.env.example`, com permissão `600`. O Compose carrega esse arquivo apenas no serviço `worker`; não o copie para `production.env`, não o passe como argumento e não inspecione o ambiente do contêiner em logs ou tickets. A implementação local não autoriza criar esse arquivo na VPS nem ativar `private_pilot` antes dos portões restantes.

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

`disable` também elimina todas as sessões da conta; `revoke-sessions` preserva a conta ativa. A autorrevogação pelo operador em uso é recusada: use outro administrador e preserve o procedimento de recuperação antes de desativar qualquer administrador. `purge-expired` remove sessões vencidas e janelas antigas de falha de login; **não** apaga relatórios, vínculos ou auditoria. Verifique `audit_events` apenas com consultas agregadas/IDs técnicos, sem exportar conteúdo para tickets. Os eventos de segurança no log registram apenas ação, tipo de entidade e ID de correlação; os logs do proxy e do host ainda exigem homologação.

Em suspeita de credencial Advbox exposta: suspenda sincronizações, acione o titular/operador da conta, revogue o token anterior, gere substituto no provedor, atualize somente o gerenciador de segredos ou `.env` local ignorado e reinicie consumidores. Faça um GET mínimo sanitizado de verificação e registre hora/resultado, nunca o valor do token. O procedimento completo e a resposta a vazamento estão em `docs/MODELO_DE_AMEACAS.md`. Backups e eliminação de dados reais permanecem dependentes da política aprovada P-002/P-011/P-012; não execute limpeza manual em massa.

## Limite de implantação na VPS

O `docker-compose.yml` raiz usa bind mount e continua exclusivo de desenvolvimento. A preparação do PDF-8 está em `compose.production.yml`, com a sobreposição sintética `compose.staging.yml`: imagens versionadas, volumes persistentes separados, PostgreSQL em rede interna, Caddy e worker manual de um ciclo. A existência desses arquivos não equivale a deploy nem autoriza dados reais.

No host inventariado, copie `deploy/production.env.example` e `deploy/restic.env.example` para arquivos protegidos fora do Git, substitua os marcadores sem imprimir os valores e forneça `APP_IMAGE`, `CADDY_IMAGE`, `POSTGRES_IMAGE`, `BACKUP_IMAGE`, `RESTIC_CONFIG_DIR`, `RESTIC_ENV_FILE` e, no staging local, `RESTIC_TEST_REPOSITORY_DIR` pelo ambiente do operador. Quando o piloto privado receber GO, `deploy/advbox.env.example` também deverá originar um arquivo `600` exclusivo do worker. Credenciais Restic e Advbox não entram em `production.env`. Valide antes de subir:

Desde 30/09/2026, a VPS opera em `PDF_DATA_SCOPE=private_pilot`, ativado por `ops/set-data-scope.sh` (ver abaixo). Parceiros reais só entram no fluxo depois de cadastrados e liberados no portal (ADR-005).

```sh
docker compose -f compose.production.yml -f compose.staging.yml config --quiet
docker compose -f compose.production.yml -f compose.staging.yml --profile operations run --rm migrate
docker compose -f compose.production.yml -f compose.staging.yml up -d postgres app proxy
```

### Promoção reversível do runtime sintético

Gere o pacote na estação de desenvolvimento com `./ops/build-vps-release.ps1`. O pacote contém somente código, migrations e configuração versionada; arquivos `.env`, segredos, fontes, relatórios e bancos ficam de fora. Transfira o arquivo para `/tmp` no host sem renomeá-lo sobre qualquer arquivo ativo. No servidor, extraia apenas o atualizador e execute:

```sh
tar -xOf /tmp/partner-reports-synthetic-runtime.tar.gz ops/deploy-synthetic-runtime.sh > /tmp/deploy-synthetic-runtime.sh
sudo install -m 0755 /tmp/deploy-synthetic-runtime.sh /opt/partner-reports/ops/deploy-synthetic-runtime.sh
sudo /opt/partner-reports/ops/deploy-synthetic-runtime.sh /tmp/partner-reports-synthetic-runtime.tar.gz
```

O atualizador recusa execução fora de `/opt/partner-reports`, pacotes com caminhos de segredo, backup concorrente e configuração incompleta. Ele constrói e testa a imagem antes da troca, pausa o timer, preserva os arquivos de ambiente, força `APP_ENV=production`, mantém o `PDF_DATA_SCOPE` ativo, aplica migrations, valida saúde interna/pública e reativa o timer. Se uma verificação posterior à troca falhar, restaura arquivos, imagem e ambiente anteriores. O diretório de rollback informado ao final deve ser preservado até a validação funcional do portal. Remova os dois arquivos temporários de `/tmp` somente depois dessa validação.

Desde o ADR-006, o atualizador também pausa `partner-reports-worker.timer`, se instalado, e recusa promover enquanto o worker estiver em execução. Proxy e app compartilham somente a rede interna `ingress` (`INGRESS_SUBNET`, padrão `10.254.18.0/29`); antes da primeira promoção com essa rede, confirme que a sub-rede não colide com redes existentes no host (`docker network inspect` das redes do outro projeto).

### Worker agendado (ADR-006)

Instale uma vez, depois de a versão com o comando `drain` estar promovida:

```sh
sudo /opt/partner-reports/ops/install-worker-timer.sh
```

O timer dispara o worker 1 minuto depois do término da execução anterior; cada execução processa até 10 itens das filas de importação e de relatório. Conferência diária: `systemctl is-active partner-reports-worker.timer` e `systemctl --failed`. Para pausar o processamento sem desinstalar: `sudo systemctl stop partner-reports-worker.timer`. As saídas no journal contêm somente contagens por resultado.

Os pacotes gerados no Windows não preservam o bit de execução; execute os scripts de `ops/` com `sudo sh <script>`.

### Contas e senhas

Desde 02/10/2026 (D-055), contas são gerenciadas no próprio portal, em **Usuários** (somente administradores): criar a conta gera um link de convite de uso único, válido por 72 horas, que o administrador envia à pessoa; ela mesma define a senha. **Link de nova senha** invalida a senha atual e as sessões da conta e gera um novo link; gerar outro link invalida o anterior. Desativar encerra as sessões na hora; o papel novo vale no próximo login. O portal não deixa a conta desativar ou rebaixar a si mesma e sempre mantém um administrador ativo. Só o SHA-256 do token é guardado; o link aparece uma única vez na tela de quem o gerou e nunca em logs ou na auditoria (eventos `account_created`, `access_link_issued`, `access_link_redeemed`, `account_enabled`, `account_disabled`, `account_role_changed`). Recomenda-se manter pelo menos dois administradores.

Cada usuário troca a própria senha em **Senha**, no cabeçalho do portal: exige a senha atual, usa o mesmo limitador do login e encerra as outras sessões da conta. O comando abaixo fica como acesso de emergência (por exemplo, se nenhum administrador conseguir entrar): na VPS, o operador do host lista contas e recupera uma senha esquecida sem precisar de outro administrador (evento `password_reset`, sessões da conta revogadas):

```sh
PR="sudo docker compose --project-directory /opt/partner-reports --env-file /opt/partner-reports/deploy/compose.env -f /opt/partner-reports/compose.production.yml --profile operations run --rm migrate python -m partner_reports.web.user_cli"
$PR list
$PR reset-password --login <login>
$PR create --admin --login <login> --actor-login <admin>
```

Quem tem `sudo` no host já controla o banco; a recuperação apenas torna essa capacidade auditável. Nenhuma senha aparece em argumento, saída ou log.

### Token do Advbox e troca de escopo

O token é instalado uma única vez, em terminal interativo, sem eco e sem argumento de linha de comando. O instalador grava `deploy/advbox.env` (`600`, lido apenas pelo serviço `worker`) e valida com um único GET de um item em `/lawsuits`, cujo conteúdo é descartado. Se a validação falhar, o arquivo novo é removido e o anterior, se houver, é restaurado:

```sh
sudo sh /opt/partner-reports/ops/install-advbox-token.sh            # primeira instalação
sudo sh /opt/partner-reports/ops/install-advbox-token.sh --replace  # rotação
```

A troca entre `synthetic_only` e `private_pilot` é feita somente por `ops/set-data-scope.sh`. Para `private_pilot`, o script exige o token instalado e a frase `LIBERAR DADOS REAIS`, pausa o worker, valida a configuração candidata num contêiner sem rede, recria o app, confere saúde e escopo e desfaz a troca em caso de falha. A cópia anterior de `production.env` fica em `/opt/partner-reports-releases/scope-*`. O atualizador de versão preserva o escopo ativo e nunca o altera.

```sh
sudo sh /opt/partner-reports/ops/set-data-scope.sh private_pilot
sudo sh /opt/partner-reports/ops/set-data-scope.sh synthetic_only   # retirada imediata dos dados reais do portal
```

Voltar para `synthetic_only` esconde parceiros, lotes e relatórios reais do portal e do worker, mas não apaga dados: a eliminação segue a política de retenção.

### Parceiros do piloto (ADR-005)

Em `private_pilot`, um administrador usa **Gerenciar parceiros** no portal para cadastrar o parceiro (o código técnico é gerado) e liberá-lo quando o PDF da carteira estiver pronto. Suspender retira o parceiro de catálogo, upload, revisão, worker e geração, sem apagar histórico. `PDF_PILOT_PARTNER_IDS` foi aposentada: se ainda estiver preenchida em `production.env`, a aplicação recusa iniciar.

O repositório Restic deve ser criado conscientemente uma única vez; o job de backup falha fechado se o destino estiver ausente ou inacessível e nunca o inicializa por conta própria:

```sh
docker compose -f compose.production.yml -f compose.staging.yml --profile backup run --rm --entrypoint restic backup init
docker compose -f compose.production.yml -f compose.staging.yml --profile backup run --rm backup
docker compose -f compose.production.yml -f compose.staging.yml --profile restore-test run --rm restore-test
```

### Destino externo Cloudflare R2

O bucket deve permanecer privado, em classe Standard, sem domínio público e sem regra de lifecycle que apague objetos do repositório por idade. A retenção de snapshots é aplicada por `restic forget --keep-within 30d --prune`; uma expiração independente no R2 pode remover packs ainda referenciados e corromper o repositório.

Crie uma credencial R2 **Object Read & Write** limitada exclusivamente ao bucket de backup. Registre em `restic.env`, nunca em `production.env`, apenas o endpoint jurisdicional apropriado, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION=auto` e o caminho do arquivo de senha. Para a jurisdição europeia, o endpoint é `s3:https://<ACCOUNT_ID>.eu.r2.cloudflarestorage.com/<BUCKET>/restic`. O segredo R2 e a senha Restic devem ser diferentes e guardados em recuperação separada da VPS.

Depois de criar o bucket e guardar uma cópia recuperável da senha Restic fora da VPS, transfira apenas o script versionado e execute no terminal interativo do host. Os quatro valores secretos são lidos sem eco; o script recusa sobrescrever configuração existente, migra `RESTIC_*` para o arquivo dedicado e valida o Compose sem mostrar valores:

```sh
sudo ./ops/configure-restic-r2.sh <BUCKET>
```

O ensaio externo usa somente `compose.production.yml`; a sobreposição `compose.staging.yml` força deliberadamente um repositório local e não deve participar deste teste:

```sh
docker compose -f compose.production.yml --profile backup run --rm --entrypoint restic backup init
docker compose -f compose.production.yml --profile backup run --rm backup
docker compose -f compose.production.yml --profile restore-test run --rm restore-test
```

Se já houver um repositório ativo e a troca for para o bucket jurisdicional `EU`, não edite `restic.env` nem substitua a senha manualmente. Guarde primeiro a **nova** senha Restic fora da VPS e execute o migrador versionado:

```sh
sudo ./ops/migrate-restic-r2-eu.sh <BUCKET-EU>
```

O migrador exige o timer instalado e ativo, pausa o agendamento, recusa concorrência com o serviço de backup, lê as quatro credenciais sem eco e usa o endpoint `.eu.`. Ele inicializa o novo repositório, executa backup e restauração em um projeto Compose isolado e remove apenas os recursos descartáveis desse projeto. A configuração ativa só é trocada depois dessas verificações; em falha, os arquivos anteriores são restaurados e o timer é reativado. A rotina não apaga nem altera o bucket antigo. Não revogue a credencial anterior até a migração retornar todos os estados `verified`, o timer voltar a `active` e a primeira execução natural no novo destino ser observada.

O backup recorrente aprovado usa `partner-reports-backup.timer`: diariamente às 03:30 em `America/Sao_Paulo`, com atraso aleatório de até 15 minutos, persistência após indisponibilidade do host e prioridade reduzida de CPU/I/O. Instale uma única vez com `sudo ./ops/install-backup-timer.sh`. Confira sem imprimir ambiente:

```sh
systemctl status partner-reports-backup.timer --no-pager
systemctl list-timers partner-reports-backup.timer --no-pager
journalctl -u partner-reports-backup.service -n 50 --no-pager
```

O log esperado contém somente progresso técnico do Restic e `backup_status=verified`. Falha do serviço bloqueia novas cargas reais até diagnóstico e novo backup/restauração aprovados. Não coloque credenciais nas unidades systemd.

Antes do primeiro comando, confirme por metadados que `restic.env` pertence ao administrador e tem modo `600`; o diretório da senha deve ter modo `700` e o arquivo `password`, modo `600`, ambos pertencentes ao UID/GID técnico `10001:10001` usado exclusivamente pelo contêiner de backup. Nenhum valor pode aparecer no processo, histórico ou saída. Registre somente estados, duração e contagens. O bucket do piloto usa a jurisdição `EU`; finalidade, minimização, segurança, transparência e os termos aplicáveis ao controlador continuam obrigatórios.

### Continuidade e recuperação com operador único

Como não existe operador substituto, o MVP depende de um kit de recuperação mantido **fora da VPS, fora do Git e separado do backup Restic**. O kit não deve ser anexado a tickets, chats ou documentos do projeto. Ele precisa conter, em um cofre de senhas ou mídia criptografada sob controle do escritório:

- acesso recuperável à conta do provedor da VPS, incluindo segundo fator e códigos de recuperação;
- acesso recuperável à conta Cloudflare que administra DNS e R2, incluindo segundo fator e códigos de recuperação;
- chave SSH ou caminho de recuperação pelo console do provedor, com instrução para obter privilégio administrativo;
- senha do repositório Restic; sem ela, os snapshots não podem ser restaurados;
- identificação do bucket/endpoint ativo e credencial R2 limitada ao bucket, ou instrução testada para emitir uma credencial substituta;
- credencial de uma conta `portal_admin` individual guardada no cofre até existirem pelo menos duas contas administrativas verificadas;
- referência à revisão implantada, ao pacote de release preservado e a este runbook.

Não registre no checklist os valores desses itens. Registre somente `confirmado`, data da conferência e uma referência opaca à localização do cofre. A confirmação inicial e qualquer rotação devem ser feitas pelo operador em sessão privada.

Rotina mínima enquanto houver um único operador:

1. diariamente, conferir `Result`, `ExecMainStatus`, último disparo e próxima execução do timer; falha bloqueia novas cargas;
2. mensalmente, confirmar acesso à VPS, Cloudflare e ao cofre, sem revelar credenciais;
3. trimestralmente e após mudança de senha, chave, bucket ou imagem, executar restauração isolada e registrar apenas estados/contagens;
4. antes de desativar conta administrativa, revogar chave ou apagar contingência, comprovar outro caminho de acesso;
5. após incidente ou indisponibilidade prolongada, restaurar primeiro em ambiente isolado, validar migration e contagens e somente então promover o ambiente recuperado.

Ordem de recuperação de desastre: recuperar as contas dos provedores e o acesso administrativo; preparar uma VPS limpa; instalar Docker/Compose; obter o código/release versionado; recriar somente os arquivos protegidos a partir do cofre; restaurar PostgreSQL e objetos em rede isolada; validar migration, integridade e contagens; configurar DNS/HTTPS; criar ou validar as contas individuais; e abrir o portal somente após `/health`, autenticação, download autorizado e timer de backup passarem. A indisponibilidade do cofre, da senha Restic ou da conta do provedor é um bloqueio operacional, não um motivo para contornar autenticação ou criar credenciais em texto aberto.

Em 30/09/2026, o responsável encerrou este portão confirmando o kit externo e aceitando, para o piloto assistido, a conferência diária das propriedades do timer/unidade como mecanismo inicial de detecção. Não há alerta externo automático nesta fase; essa limitação é risco residual aceito apenas para o piloto acompanhado. Antes de operação rotineira sem acompanhamento, configurar um canal externo de alerta e testar a entrega de uma falha sintética, sem incluir logs integrais ou dados pessoais.

Depois da migration `20260925_0012`, a retenção pode ser conferida por contagens e só então executada. Fontes de lotes aprovados/superseded vencem em 30 dias; versões superseded, em 12 meses; auditoria, em 24 meses. O comando não deve ser agendado antes de backup e restauração terem passado:

```sh
docker compose -f compose.production.yml --profile operations run --rm retention
docker compose -f compose.production.yml --profile operations run --rm retention python -m partner_reports.retention
```

O primeiro comando aplica a retenção (`--execute`) conforme a definição do serviço; o segundo sobrescreve o comando para dry-run. Registre apenas as contagens retornadas. O bloqueio, a idempotência e a retomada no banco continuam obrigatórios.

Antes de ligar o Advbox real: aplicar o escopo minimizado do ADR-004, definir volumes e identidade produtivos (P-013/P-014), aprovar retenção P-012/P-019, executar homologação controlada, validar a VPS e comprovar backup/restauração. SMTP não foi confirmado nem aprovado; nenhum e-mail é enviado.

## Evidência técnica local

Migration `20260917_0004` aplicada sem deriva. Testes da automação cobrem idempotência, trava distribuída entre conexões, reivindicação/lease, falha no PDF, retomada de lease abandonado, fencing de token/fonte, preservação da versão anterior, regressão de contagens e bloqueio em produção. Em 17/09/2026, `run-now` examinou quatro fontes sintéticas, enfileirou quatro mudanças e concluiu quatro jobs; a repetição da mesma chave não gerou outros jobs. O PDF de 55 casos foi inspecionado em três páginas A4, sem corte de linhas ou falha de layout. A suíte total teve 101 testes aprovados; dois avisos de depreciação vêm de dependências de teste.
