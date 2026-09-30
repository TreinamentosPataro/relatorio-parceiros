# Preparação para o PDF-8

**Estado:** staging exclusivamente sintético publicado na VPS; HTTPS, autenticação, persistência, backup externo, restauração isolada e primeira execução natural do agendamento validados; piloto real autorizado de forma condicional; backup migrado para novo bucket R2 privado com jurisdição UE

## Portão recebido do PDF-7

- duas fotografias GET-only idênticas usadas na segunda passagem;
- sete fontes e sete lotes privados persistidos localmente;
- 7 correspondências exatas e 4 pendências aceitas sem vínculo;
- zero ambiguidade, duplicidade, vínculo ativo ou versão publicada;
- prévia interna agregada aprovada;
- retenção P-012/P-019 aprovada no ADR-004.

## Informações da VPS a inventariar

Registrar sem copiar senhas, tokens ou chaves privadas para o repositório:

- provedor, plano, região e sistema Linux;
- CPU, RAM, disco disponível e arquitetura x86_64;
- versões do Docker Engine e Docker Compose;
- IP público e forma de acesso administrativo restrito;
- domínio/subdomínio e responsável pelo DNS;
- acesso por VPN/rede privada ou necessidade de exposição HTTPS pública;
- destino externo para backup criptografado;
- modelo de operação e recuperação; neste projeto, operador único sem substituto.

O script `ops/collect-vps-inventory.sh` coleta somente sistema, arquitetura, CPU, memória, disco, versões do Docker, firewall disponível e sincronização de horário. Ele não lê hostname, IP, usuários, variáveis de ambiente, arquivos de configuração, chaves ou credenciais. Execute-o localmente na VPS e revise a saída antes de compartilhá-la.

### Inventário recebido em 28/09/2026

O painel confirmou região nacional, Ubuntu 24.04 LTS, plano KVM 1, 1 vCPU, 4 GB de RAM, 50 GB de disco, 4 TB de transferência e backup semanal do provedor. Hostname, endereço público e conta administrativa exibidos na captura não foram transcritos para o repositório.

A coleta sanitizada no host confirmou Linux 6.8 x86_64, 1 CPU disponível, aproximadamente 3,82 GiB de memória e 39,23 GiB livres no disco raiz. Docker Engine 29.7.1 e Docker Compose 5.4.0 estão disponíveis, o UFW foi detectado e a sincronização NTP estava ativa. O script não alterou a configuração do host.

Uma conta não privilegiada passou a autenticar por chave pública e teve a elevação `sudo` validada. O identificador da conta, a chave e o endereço do host não foram registrados. O login informou reinicialização pendente do sistema; manutenção e retorno do SSH precisam ser validados antes do staging. O acesso administrativo anterior não deve ser desativado antes desse portão.

A VPS já hospeda outro projeto de baixa movimentação. Nenhum identificador ou dado desse projeto foi registrado. O host passa a exigir medição de recursos compartilhados, inventário técnico mínimo das dependências e janela de manutenção; reinicialização, firewall e portas não podem ser alterados presumindo dedicação exclusiva.

Uma fotografia agregada, com o outro projeto em operação, encontrou carga de 0,08/0,02/0,01, aproximadamente 3,12 GiB de memória e 39,22 GiB de disco disponíveis. Dois containers estavam ativos, usando 0% de CPU e 20,07% da memória naquele instante; não havia serviço systemd com falha e o UFW estava ativo. Docker estava ativo e habilitado, os dois containers usavam `unless-stopped` e a regra SSH do firewall foi confirmada. A reinicialização continuava pendente. Essa amostra pontual permite preparar um staging controlado, mas não substitui benchmark concorrente nem o teste real de retorno após reboot.

A reinicialização controlada foi executada. Em aproximadamente dois minutos, o SSH retornou, Docker ficou ativo, os dois containers voltaram, zero serviço systemd estava em falha e o marcador de reboot deixou de existir. O operador confirmou que o outro projeto continuou funcionando. O banner indicou 37 atualizações ainda disponíveis, das quais 3 eram atualizações de segurança padrão; nenhuma foi aplicada nesta validação.

Após atualizar somente os índices do APT, a simulação de `upgrade` manteve 37 pacotes e zero remoção. O conjunto inclui Docker Engine/CLI, Compose, Buildx, containerd e componentes rootless; a atualização pode reiniciar o daemon e interromper temporariamente os containers existentes. Nenhum pacote foi instalado e não havia pacote retido. Uma recuperação atual do projeto existente e uma janela com validação posterior permanecem obrigatórias.

Em autorização posterior, os 37 pacotes foram atualizados. Docker Engine passou para 29.8.1 e Compose para 5.5.1; Docker permaneceu ativo, os dois containers retornaram, nenhum serviço systemd falhou e não surgiu novo marcador de reboot. Após reconectar o SSH, havia zero atualização nos repositórios habilitados; uma atualização adicional oferecida por ESM Apps não foi aplicada porque o serviço não está habilitado. As portas TCP 80 e 443 estavam livres. Ainda faltam o teste funcional posterior do projeto existente, domínio/DNS e as demais decisões antes de configurar o staging.

A avaliação permanece condicional: a memória e o disco atendem a referência mínima, mas 1 vCPU fica abaixo da referência de 2 vCPU e precisa de benchmark com Chromium/concorrência unitária. A presença do UFW não comprova que ele esteja ativo ou corretamente configurado. O backup semanal não substitui cópia Restic criptografada fora da VPS com restauração comprovada. Ainda faltam contrato, identidade e acesso por chave, DNS/rede, regras efetivas do firewall, destino externo de backup e responsáveis operacionais.

O subdomínio escolhido é `relatorios.patarotreinamentos.com.br`. O titular confirmou que administra o DNS pela Cloudflare e validou que o registro `A` em modo DNS only resolve para a VPS. O proxy da Cloudflare será reavaliado depois do HTTPS funcional.

O UFW passou a permitir somente as entradas adicionais TCP 80 e 443 para o proxy; a regra SSH previamente validada foi preservada. Ainda não havia processo do novo projeto escutando nessas portas no momento da abertura.

Foi preparado localmente um pacote-fonte explícito para o build do staging, com 127 entradas e cerca de 110 KiB. A verificação de nomes encontrou zero `.env`, storage, output, temporário ou metadado Git; o único modelo de ambiente incluído contém placeholders. O pacote permanece em diretório local ignorado e ainda não foi transferido.

O pacote foi transferido por SSH para `/opt/partner-reports` e extraído pela conta não privilegiada. A presença do Compose produtivo, Dockerfile e diretório do código foi confirmada. Nenhuma imagem foi construída, variável secreta criada, migration executada ou aplicação iniciada nessa transferência.

As imagens `partner-reports:staging` e `partner-reports-backup:staging` foram construídas no host a partir do pacote explícito. A inspeção confirmou os usuários não privilegiados `app` e `backup`. Nenhum container do novo projeto foi iniciado e nenhum dado real foi copiado.

O configurador `ops/configure-vps-staging.sh`, validado sintaticamente em shell Linux, foi transferido separadamente e executado com privilégio apenas para criar a configuração. Ele gerou a senha do banco dentro da VPS sem exibi-la, fixou os digests oficiais de Caddy/PostgreSQL, gravou os dois arquivos de ambiente com modo `600` e criou o diretório privado do Restic. Nenhum e-mail, senha, digest do host ou conteúdo dos arquivos foi registrado no repositório. O destino Restic permanece deliberadamente `UNCONFIGURED` e o perfil de backup não pode ser considerado pronto.

O operador confirmou por metadados que `production.env` e `compose.env` pertencem ao administrador do sistema e usam modo `600`. `docker compose ... config --quiet` aprovou o modelo no host sem imprimir a configuração. Nenhum container havia sido iniciado ao concluir essa validação.

Antes de configurar o destino externo, a preparação local passou a separar `restic.env` do ambiente comum. A migração desse terceiro arquivo protegido na VPS permanece pendente e deverá remover as variáveis `RESTIC_*` de `production.env`; nenhuma credencial externa foi criada durante essa alteração.

O serviço PostgreSQL do staging foi iniciado sozinho. O volume persistente e a rede interna foram criados; o container ficou `healthy`, com política `unless-stopped` e zero binding de porta no host. O banco estava vazio e nenhuma migration havia sido aplicada nessa verificação.

As migrations foram executadas no banco vazio e `alembic check` retornou `No new upgrade operations detected.` A confirmação explícita do head `20260925_0012` ainda será repetida antes de iniciar a aplicação.

O início do app foi condicionado à confirmação do head `20260925_0012`. O container ficou `healthy`, sem binding de porta no host, com raiz somente leitura, política `unless-stopped` e usuário `app`. O proxy ainda não estava ativo ao concluir essa verificação.

O proxy foi iniciado e o endpoint público `https://relatorios.patarotreinamentos.com.br/health` respondeu HTTP 200 com certificado aceito pelo cliente. A verificação externa confirmou redirecionamento HTTP 308 para HTTPS, HSTS por um ano, `nosniff`, `DENY`, política de referência restrita e `/docs` em HTTP 404. Nenhum conteúdo privado foi consultado e o portal ainda não recebeu conta de staging.

O benchmark Chromium, com concorrência unitária e carteira sintética de 55 processos, gerou HTML/PDF em 13 segundos e retornou código zero. Os dois artefatos privados estavam presentes; ao final havia aproximadamente 3,03 GiB de memória disponível e carga 0,54/0,31/0,20. O KVM 1 fica condicionalmente aprovado para o fluxo manual do MVP, sem jobs paralelos e com monitoramento de recursos.

O catálogo sintético e a primeira conta administrativa técnica foram criados sem exibir credencial. O operador confirmou o fluxo autenticado e a ausência de dados reais. Após observação visual, os seletores receberam seta, foco, opções, seleção e scrollbar alinhados ao tema escuro, mantendo o `<select>` nativo por acessibilidade e respeitando os limites de renderização do navegador/sistema operacional. O teste visual direcionado passou; Ruff, formatação e `git diff --check` passaram. A imagem foi reconstruída, o app recriado saudável e a verificação externa confirmou as novas regras CSS com `/health` em HTTP 200.

O reinício controlado de PostgreSQL, aplicação e proxy também passou no host. Os três serviços retornaram saudáveis ou em execução; permaneceram um usuário técnico, quatro parceiros e três versões de relatório exclusivamente sintéticos, além dos artefatos privados HTML/PDF do cenário de maior volume. Isso comprova persistência dos volumes nesse reinício, sem introduzir dados reais. O próximo portão é configurar um destino externo para o Restic, executar backup criptografado e provar a restauração em ambiente isolado.

## Ordem de preparação

1. produzir Compose de produção sem bind mount e com imagem versionada;
2. executar staging somente com dados sintéticos;
3. restringir PostgreSQL e volumes à rede interna;
4. configurar proxy HTTPS e firewall;
5. validar app, worker, migrações e reinício sem perda;
6. implementar expiração de 30 dias para fontes e as demais retenções aprovadas;
7. criar backup criptografado fora da VPS e restaurar em ambiente separado;
8. validar isolamento, upload, download, job, rollback e logs mínimos;
9. registrar capacidade, resultado, responsáveis e portão GO/NO-GO;
10. solicitar autorização específica antes de copiar qualquer dado real à VPS.

## Preparação local implementada

- `compose.production.yml` define imagens informadas por tag/digest, processos sem privilégio, filesystem somente leitura, PostgreSQL sem porta publicada, volumes privados separados e perfis operacionais.
- `compose.staging.yml` limita o proxy sintético a `localhost:8443` e usa repositório Restic local apenas para o ensaio.
- PostgreSQL permanece somente em `backend`; o PostgreSQL de restauração permanece somente em `restore`. Apenas worker, backup e cliente de restauração recebem a rede `outbound` necessária. O proxy usa sua rede de borda e a rede interna do app.
- Caddy, storage persistente, marcadores de retenção, rotina de retenção e scripts de backup/restauração foram preparados sem segredo versionado.
- O backup exige repositório Restic previamente inicializado e falha fechado quando o destino está ausente ou inacessível; erro de acesso nunca cria silenciosamente um repositório novo.
- A configuração do backend Restic usa arquivo de ambiente próprio, carregado somente pelos serviços de backup e restauração; credenciais externas não são herdadas pelo app, proxy ou PostgreSQL.
- `ops/collect-vps-inventory.sh` permanece o ponto de entrada para o inventário sanitizado do host.

## Verificação local de 28/09/2026

- `docker compose ... config --quiet`: aprovado com Compose 5.5.0; a inspeção do modelo confirmou ausência de porta publicada no PostgreSQL e redes separadas.
- imagens `partner-reports:staging`, `partner-reports:test` e `partner-reports-backup:staging`: construídas com sucesso; app executado como UID 10001, raiz somente leitura e volumes privados graváveis.
- PostgreSQL, app e proxy foram recriados sem remover volumes; após o reinício, o banco permaneceu no head `20260925_0012`, sem deriva, com os registros sintéticos esperados.
- `https://localhost:8443/health`: HTTP 200 via Caddy com TLS interno e cabeçalhos de segurança; `/docs`: HTTP 404 em staging; Chromium iniciou dentro da imagem.
- migration completa aplicada do zero em banco de teste isolado; `alembic check`: sem novas operações.
- suíte completa: 167 testes aprovados e um aviso de depreciação de dependência. Uma primeira passagem teve três falhas exclusivamente por permissão de screenshots no bind mount do Windows; a repetição em volume Docker gravável pelo UID 10001 passou integralmente.
- backup Restic sintético: dump PostgreSQL e volumes privados gravados, política aplicada e `restic check --read-data-subset=5%` sem erro.
- restauração em PostgreSQL e rede isolados: aprovada, com uma migration e seis objetos de relatório recuperados; zero fonte no corpus sintético do staging.
- retenção operacional: dry-run e execução retornaram zero fontes, relatórios ou eventos elegíveis; o teste automatizado de expiração/remoção idempotente também passou na suíte.
- worker manual: estado vazio e `work-once` retornou `job: empty`, sem processo permanente.
- `ruff check .`, `ruff format --check .` e `git diff --check`: aprovados ao final.
- recursos descartáveis da verificação — banco `partner_reports_test`, volume de screenshots e PostgreSQL de restauração — foram removidos. App, proxy, PostgreSQL principal e repositório de backup sintético permaneceram disponíveis.

## Estado dos bloqueios

O staging sintético está publicado na VPS com HTTPS, firewall, autenticação, benchmark unitário e persistência após reinício validados. O Cloudflare R2 foi escolhido como destino externo; bucket privado e token permanente de leitura/gravação limitado exclusivamente a esse bucket foram criados pelo responsável em 29/09/2026, sem registrar identificadores ou credenciais. O primeiro backup externo terminou verificado e a restauração isolada recuperou uma migration e seis artefatos sintéticos, sem fontes. O timer diário está habilitado e ativo; sua unidade `oneshot` foi executada manualmente e a primeira execução natural no novo destino também terminou com `Result=success` e código zero. Os arquivos temporários usados na transferência foram removidos. O projeto terá operador único, sem substituto disponível; o procedimento de continuidade foi formalizado no runbook, mas o operador ainda precisa confirmar que o kit recuperável existe fora da VPS. Para o piloto real, o backup foi migrado em 29/09/2026 para o novo bucket R2 com jurisdição `EU`: inicialização, backup, restauração isolada, troca da configuração ativa, reativação do timer e primeira execução natural foram verificadas. Dados reais continuam bloqueados até os portões operacionais restantes e um GO explícito.

## Runtime produtivo com escopo sintético

Para validar o ambiente antes da primeira execução natural do backup, o runtime passou a separar ambiente de implantação e escopo de dados. `APP_ENV=production` pode agora validar storage persistente, revisão, geração, worker e Chromium, mas `PDF_DATA_SCOPE` aceita somente `synthetic_only`. Parceiros fora do prefixo técnico `SYNTHETIC-*` não aparecem no catálogo ou no seletor de upload, não podem receber lote e são recusados nas rotas diretas, reconciliação, revisão e geração. Não existe nesta versão uma opção de configuração que habilite dados reais.

O worker implantado passou a usar `REPORT_STORAGE_ROOT`, em vez do diretório local padrão, para gravar no volume privado permitido pelo Compose. A imagem `partner-reports:production-validation` foi construída localmente; a configuração interna retornou `app_env=production`, `data_scope=synthetic_only` e `deployed=true`. Os modelos Compose produtivo e de staging foram validados silenciosamente. O Chromium da imagem produtiva gerou um PDF sintético válido em memória.

Na verificação local anterior à promoção, 178 testes foram aprovados, com um aviso de depreciação de dependência sem falha; Ruff lint/formatação, `alembic check` e `git diff --check` também passaram. Naquele momento nenhuma alteração havia sido implantada na VPS, e a promoção foi mantida como portão separado e reversível. Nenhum dado real foi processado.

Para esse portão, `ops/build-vps-release.ps1` passou a criar um pacote allowlisted sem segredos ou dados, e `ops/deploy-synthetic-runtime.sh` implementa promoção com imagem versionada, pausa curta do timer, atualização atômica dos dois campos de ambiente, migration, saúde interna/pública e rollback automático. O pacote preparado em 29/09/2026 teve 227 entradas, inspeção negativa para `.env`, diretórios de segredos, fontes e relatórios, e a suíte completa teve 180 testes aprovados.

A promoção foi concluída na VPS em 29/09/2026. Duas tentativas anteriores falharam de forma segura antes da conclusão: a primeira encontrou arquivos opcionais ausentes no snapshot da versão antiga; a segunda testou o HTTPS antes de o proxy recriado voltar a escutar. Ambas retornaram `deployment_status=rolled_back`, sem troca persistente de configuração. O atualizador passou a arquivar apenas caminhos existentes, exigir timer ativo e aguardar por até 60 segundos o proxy público.

A tentativa final retornou `deployed_scope=synthetic_only`, `deployment_status=verified`, `app_environment=production`, `data_scope=synthetic_only`, `public_health=ok` e `backup_timer=active`. O rollback desta promoção foi preservado em diretório protegido fora da árvore ativa. Uma verificação externa independente confirmou HTTP 200 em `/health`, HTTP 200 na tela de login e HTTP 404 em `/docs`, sem autenticação, dados privados ou uso de PDFs reais.

## Verificação local de 29/09/2026

- a configuração do backend Restic foi separada de `production.env` e passou a ser carregada somente por `backup` e `restore-test`;
- o instalador `ops/configure-restic-r2.sh` prepara a migração na VPS com entrada sem eco, recusa de sobrescrita, modos `600` e validação silenciosa do Compose;
- a primeira inicialização externa revelou que o arquivo de senha protegido não era legível pelo UID/GID `10001` do contêiner; nenhum segredo foi exibido nem repositório criado. O instalador passou a atribuir somente o diretório/arquivo da senha a esse usuário técnico, preservando modos `700/600`;
- após corrigir a permissão, o TLS público funcionou no host/contêiner, mas o endpoint R2 rejeitou o handshake porque outro identificador de 32 caracteres foi informado no lugar do Account ID da conta. Nenhum repositório foi criado; `ops/update-restic-r2-account.sh` corrige apenas esse componente sem exibi-lo;
- com o endpoint corrigido, R2 respondeu `InvalidArgument`; a inspeção exclusiva de comprimentos confirmou 64 caracteres em `AWS_ACCESS_KEY_ID`, onde o R2 exige 32, e 64 no segredo. Nenhum valor foi exibido. `ops/update-restic-r2-access-key.sh` valida e troca somente o identificador de acesso;
- após trocar somente o Access Key ID pelo valor S3 de 32 caracteres, o teste S3 listou zero objeto, o repositório foi inicializado uma única vez e o primeiro backup retornou `backup_status=verified`;
- a restauração externa em PostgreSQL/rede isolados retornou `restore_status=verified`, uma migration, zero fonte e seis objetos de relatório sintéticos;
- o contêiner e o volume descartáveis de restauração foram removidos após validação; o volume isolado ficou ausente e o backup R2 permaneceu disponível;
- a verificação posterior confirmou `app`, `postgres` e `proxy` em execução, saúde HTTPS pública aprovada e preservação de 1 usuário técnico, 4 parceiros e 3 versões exclusivamente sintéticos;
- a versão corrigida de `ops/configure-restic-r2.sh`, incluindo propriedade `10001:10001` para o segredo montado no contêiner, foi sincronizada na VPS e aprovada por validação sintática/assinatura esperada; o instalador não foi reexecutado sobre a configuração existente;
- o responsável aprovou backup diário às 03:30 em `America/Sao_Paulo`, com atraso aleatório de até 15 minutos; as unidades systemd foram instaladas, e o timer retornou `enabled` e `active`, com próxima execução dentro da janela esperada;
- a unidade `partner-reports-backup.service` foi acionada manualmente após a instalação e terminou com `Result=success`, `ExecMainStatus=0` e `backup_status=verified`; `ActiveState=inactive` é o estado esperado após a conclusão de uma unidade `oneshot`;
- os sete arquivos temporários usados para transferir o Compose, os scripts e as unidades systemd foram removidos de `/tmp`; a verificação posterior retornou `temporary_cleanup=completed`;
- o responsável informou que não existe operador substituto; o MVP será operado por uma única pessoa, sem registrar identidade pessoal na documentação;
- para o piloto interno, cada advogado deverá receber conta individual `portal_admin`, com permissão para enviar PDFs, revisar/aprovar vínculos e solicitar relatórios; contas compartilhadas não serão usadas, e as contas serão validadas primeiro no staging sintético;
- o responsável autorizou em 29/09/2026 um primeiro piloto privado com dados reais, mas a execução permanece condicionada ao fechamento do PDF-8, à implementação explícita do modo produtivo e ao portão de transferência internacional; a autorização não permite contornar os bloqueios sintéticos atuais;
- `deploy/restic.env` foi excluído do Git e do contexto de build; o repositório contém apenas um modelo sem credenciais;
- teste automatizado novo confirma que app, proxy, PostgreSQL, worker, migration e retenção não recebem variáveis `RESTIC_*`;
- `sh -n` aprovou o configurador, e `docker compose ... config --quiet` aprovou o modelo com os arquivos de exemplo;
- suíte completa: 169 testes aprovados, com um aviso de depreciação de dependência sem falha;
- Ruff lint/formatação e `git diff --check` aprovados;
- somente scripts e unidades versionados foram sincronizados com a VPS; credenciais permaneceram nos arquivos protegidos do host, sem serem registradas na documentação ou no repositório, e nenhum dado real foi copiado.

## Revisão oficial do destino externo em 29/09/2026

- a documentação oficial do R2 informa que a localização `Automatic` escolhe uma região disponível próxima da origem da criação, sem garantir residência no Brasil;
- `Location Hints` são apenas melhor esforço, não garantia; as restrições jurisdicionais disponíveis são UE, EUA e FedRAMP, e não podem ser alteradas depois da criação do bucket;
- o DPA da Cloudflare prevê que o serviço e subprocessadores podem tratar dados fora do país de origem;
- a Resolução CD/ANPD nº 19/2024 exige hipótese legal e mecanismo válido para transferência internacional, além de minimização;
- antes da decisão D-046, as opções eram aprovar o mecanismo contratual do bucket automático ou escolher outro destino. O responsável decidiu permanecer no R2 e adotar a jurisdição `EU`, reconhecida como adequada pela ANPD; a criptografia Restic continua obrigatória e os termos do controlador ainda devem ser preservados/revisados.
- o responsável decidiu permanecer na Cloudflare e usar um novo bucket R2 com jurisdição `EU` para o piloto real. O bucket `Automatic` atual continuará restrito ao corpus sintético e não receberá dados reais;
- a ANPD reconheceu a União Europeia como organismo internacional adequado pela Resolução CD/ANPD nº 32/2026. A decisão reduz o portão de transferência, mas não elimina a obrigação de finalidade, minimização, segurança, transparência e revisão dos termos aplicáveis ao controlador;
- a migração somente poderia ser concluída depois que o repositório Restic do novo bucket recebesse backup criptografado e passasse por restauração isolada. Essa comprovação ocorreu em 29/09/2026; a credencial e o bucket antigos foram preservados como contingência enquanto se aguardava a primeira execução natural no novo destino.
- o novo bucket foi criado em 29/09/2026 com jurisdição `EU`, classe Standard, acesso público desabilitado e zero objeto inicial. Nenhum identificador de conta, credencial ou dado real foi registrado. A credencial exclusiva foi usada somente no host protegido.
- `ops/migrate-restic-r2-eu.sh` pausou o timer, recusou backup concorrente, usou o endpoint jurisdicional `.eu.`, validou a configuração, inicializou o novo repositório, executou backup e restauração em projeto Compose isolado e só então trocou os arquivos ativos. O host retornou `repository_initialization=verified`, `backup_status=verified`, `restore_status=verified`, `active_configuration=updated` e `backup_timer=active`; o bucket antigo não foi apagado.
- a validação local do migrador aprovou sintaxe POSIX `sh -n`, oito testes específicos de implantação, Ruff lint/formatação e `git diff --check`; nenhuma conexão ao R2 ou alteração na VPS foi feita nessa validação.

## Primeira execução natural e recuperação do operador em 30/09/2026

- o timer disparou naturalmente em 30/09/2026 às 03:41:04 em `America/Sao_Paulo`, dentro da janela aprovada de 03:30 a 03:45;
- a unidade terminou às 03:41:29, com duração de 25 segundos, `Result=success` e `ExecMainStatus=0`; como o script usa `set -eu`, esse resultado exige conclusão do backup, retenção Restic e `restic check --read-data-subset=5%`;
- o timer permaneceu `enabled` e `active`, com nova execução calculada para 01/10/2026 dentro da mesma janela; zero unidade systemd estava em falha;
- a verificação pública posterior retornou HTTP 200 em `/health`, HTTP 200 no login e HTTP 404 em `/docs`, sem autenticação ou acesso a dados;
- a contingência do bucket anterior não foi apagada nem sua credencial foi revogada automaticamente. A observação exigida por D-046 foi atendida; a retirada da contingência deve ser uma ação manual separada, depois de o operador confirmar o kit de recuperação;
- `docs/RUNBOOK.md` passou a definir o conteúdo mínimo do kit externo, a rotina diária/mensal/trimestral e a ordem de recuperação. Nenhum segredo, endereço, login pessoal ou identificador de conta foi registrado.

O responsável encerrou o portão de continuidade em 30/09/2026, confirmando o kit externo e aceitando a conferência diária manual do systemd durante o piloto assistido. A ausência de alerta externo automático é risco residual aceito somente enquanto o primeiro ciclo permanecer acompanhado; não vale como aprovação para operação rotineira desacompanhada.

## Pendências objetivas antes do primeiro teste real

O PDF-8 de infraestrutura está substancialmente atendido, mas o runtime implantado ainda não aceita dados reais. O primeiro teste real permanece **NO-GO** até os itens técnicos 1 a 4 e os controles 5 a 7 abaixo serem concluídos:

1. **Escopo produtivo explícito — implementação local concluída, promoção pendente:** `PDF_DATA_SCOPE=private_pilot` e `PDF_PILOT_PARTNER_IDS` usam validação fail-closed e allowlist exata de identificadores opacos. Catálogo, detalhe, upload, processamento, revisão, vínculo, geração, download, restauração e retenção aplicam esse escopo. A promoção operacional permanece bloqueada; a VPS continua em `synthetic_only`.
2. **Processamento do upload produtivo — implementação local concluída, implantação pendente:** lotes admitidos pelo escopo recebem fila durável no próprio registro, lease renovável, recuperação de abandono, três tentativas e backoff. O worker retoma de `quarantined` ou `parsed`, executa parser e duas leituras GET-only idênticas da API, persiste somente manifesto/propostas técnicas e termina em `needs_review`. Falha da API preserva o manifesto já confirmado e não duplica itens na retomada. O token Advbox fica em arquivo separado, carregado somente pelo worker. A VPS continua na versão anterior e nenhum dado real foi processado.
3. **Fotografia oficial e dados normalizados — implementação mínima local concluída, execução real pendente:** após duas leituras GET-only idênticas, somente processos efetivamente conciliados são persistidos. Para eles entram apenas ID técnico, número canônico, pasta exata e IDs técnicos relacionados; processos não correspondentes, nomes, protocolo, responsável, grupo/fase, contatos, financeiro, movimentos e texto livre são descartados. A proposta de reconciliação referencia a linha local criada. Ainda faltam configurar o segredo no host protegido, executar a primeira fotografia real assistida e adaptar revisão/relatório, portanto não há autorização para dados reais.
4. **Relatório real minimizado — implementação local concluída, homologação pendente:** lote allowlisted aprovado cria vínculos auditados e pode gerar HTML/PDF privado `validated`, com chave opaca, hash conjunto, versão anterior preservada e somente as contagens do ADR-004. Teste ponta a ponta confirmou ausência de número processual, pasta e campos proibidos. Restauração administrativa foi liberada localmente apenas para parceiro allowlisted e artefatos íntegros, com auditoria; a versão não é publicada e nenhum dado real foi usado.
5. **Identidade e ensaio funcional:** provisionar contas individuais `portal_admin` em sessão interativa, validar login/logout/CSRF/revogação e executar no staging um fluxo sintético completo com cada perfil que participará do piloto. Senhas não podem aparecer em comando, chat ou documentação.
6. **Segurança operacional:** confirmar a rotação da credencial exposta nos materiais originais (P-008), validar o endereço efetivo usado pelo limitador de login atrás do Caddy, inspecionar/redigir logs do proxy/host e executar retenção programada ou uma rotina manual formal durante o piloto.
7. **Liberação e recuperação da versão:** reconstruir a suíte completa, Ruff, Alembic e Compose; promover com rollback; repetir health/login/docs, isolamento, upload, revisão, worker, download e restauração do backup já contendo um corpus real minimizado. Somente então registrar GO para um parceiro e um período no PDF-9.

O endereço usado pelo limitador de login (item 6) foi corrigido localmente em 30/09/2026. Antes, o Uvicorn só confiava em `X-Forwarded-For` vindo de `127.0.0.1`; atrás do Caddy, todas as tentativas caíam no mesmo bucket do IP do proxy, e um único cliente poderia bloquear o login de todos os advogados. Proxy e app passaram a compartilhar somente a rede interna `ingress` (sub-rede fixa `INGRESS_SUBNET`, padrão `10.254.18.0/29`); o proxy saiu da rede `backend`, e o app confia em cabeçalhos encaminhados apenas dessa sub-rede via `FORWARDED_ALLOW_IPS`. No staging local, o bucket gravado correspondeu ao endereço real do cliente, e não ao do proxy; um `X-Forwarded-For` forjado pelo cliente foi descartado pelo Caddy. A suíte completa aprovou 193 testes. A VPS não foi alterada: a promoção precisa confirmar que a sub-rede não colide com redes do outro projeto do host e, se o proxy da Cloudflare for ativado, configurar `trusted_proxies` do Caddy com as faixas oficiais da Cloudflare antes de ativá-lo. Rotação P-008, logs do proxy/host e retenção programada continuam pendentes no item 6.

Ainda em 30/09/2026, o responsável confirmou a rotação da credencial P-008 e a revogação da credencial do bucket R2 anterior (o repositório de contingência não foi apagado). Também decidiu testar com a carteira de parceiros, liberados aos poucos, e indicou duas advogadas como usuárias do piloto; seus nomes não são registrados no repositório. O ADR-005 substituiu a allowlist por variável de ambiente por cadastro e liberação auditados no portal. A migration `20260930_0014`, a página administrativa e os testes foram implementados localmente; 194 testes passaram. Na mesma rodada, foi corrigido um vazamento anterior: um `DATABASE_URL` malformado aparecia com a senha na mensagem de erro da configuração. A VPS não foi alterada.

A restauração privada do item 4 foi fechada localmente em 30/09/2026: teste com parceiro allowlisted restaurou uma versão íntegra, marcou a posterior como `superseded` e confirmou a auditoria; uma segunda tentativa com hash adulterado foi recusada. A suíte completa no contêiner aprovou 192 testes, com um aviso de depreciação sem falha. A VPS não foi alterada.

Ações manuais paralelas que não exigem mudança de código: preservar o aceite dos termos aplicáveis à VPS/R2; revogar a credencial do bucket anterior sem apagar o repositório de contingência até a política de descarte ser aprovada; escolher um parceiro piloto com exportação corrigida ou tratar explicitamente qualquer `invalid_identifier`; e definir a janela acompanhada do teste. Nenhuma dessas ações autoriza antecipar os itens técnicos acima.

Fontes oficiais: [localização do R2](https://developers.cloudflare.com/r2/reference/data-location/), [DPA da Cloudflare](https://www.cloudflare.com/cloudflare-customer-dpa/), [Resolução CD/ANPD nº 19/2024](https://www.gov.br/anpd/pt-br/acesso-a-informacao/institucional/atos-normativos/regulamentacoes_anpd/resolucao-cd-anpd-no-19-de-23-de-agosto-de-2024) e [decisão de adequação da União Europeia](https://www.gov.br/anpd/pt-br/assuntos/assuntos-internacionais/transferencia-internacional-de-dados).
