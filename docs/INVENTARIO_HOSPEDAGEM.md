# Inventário dos ambientes

**Situação:** arquitetura, inventários, configuração, HTTPS, reinício e benchmark unitário aprovados; backup externo e responsável substituto pendentes

**Finalidade:** separar desenvolvimento, homologação e produção e registrar somente requisitos verificáveis.
**Regra:** não registrar senhas, tokens, chaves privadas ou outros segredos.

## Ambientes definidos

| Ambiente | Finalidade | Situação |
|---|---|---|
| Máquina Windows atual | Desenvolvimento e testes com dados sintéticos | Docker Desktop, aplicação e PostgreSQL local validados. Não será host permanente. |
| VPS Linux | Homologação e produção interna | Alvo aprovado no ADR-003; painel e host inventariados sem alteração de configuração ou deploy. |
| Vercel Hobby | Nenhuma função produtiva | Destino anterior, superado. O plano não atende ao uso profissional e não será usado. |

## Desenvolvimento confirmado

| Item | Situação |
|---|---|
| Sistema | Windows x64 25H2/build 26200 |
| Hardware observado | Intel Core i5-1334U, 12 processadores lógicos, 7,7 GB de RAM e aproximadamente 369 GB livres na inspeção |
| Docker | Docker Desktop, Engine 29.7.2 e Compose 5.5.0 validados |
| Banco | PostgreSQL 17 em contêiner com healthcheck aprovado |
| Python | Python 3.12 na imagem Docker |
| Ferramentas | Git, Node.js e npm disponíveis |

## Arquitetura produtiva decidida

Uma única VPS Linux executará, por Docker Compose, proxy reverso HTTPS, FastAPI, worker e PostgreSQL. Fontes e relatórios usarão volumes persistentes privados. O banco e os diretórios de arquivos não serão expostos diretamente à internet. O processamento será iniciado manualmente no MVP.

O acesso preferencial é por rede privada/VPN. Exposição pública do portal somente poderá ocorrer após validação de HTTPS, firewall, autenticação, limitação de tentativas, logs mínimos e procedimento de incidente.

## VPS disponível — inventário sanitizado do painel

| Item | Evidência recebida | Avaliação preliminar |
|---|---|---|
| Plano | KVM 1, validade informada até 17/10/2026 | Confirmar continuidade/renovação antes do uso operacional. |
| Região | Brasil, Campinas | Região nacional confirmada; revisar contrato e subprocessadores do provedor. |
| Sistema | Ubuntu 24.04 LTS | Compatível em princípio; confirmar arquitetura e atualizações no host. |
| CPU | 1 vCPU | Abaixo da referência inicial de 2 vCPU; exige medição de PostgreSQL + Chromium com concorrência unitária. |
| Memória | 4 GB | Atende o mínimo de referência, com pouca margem; medir pico e swap sem presumir capacidade produtiva. |
| Disco | 50 GB | Acima da referência inicial de 40 GB; confirmar espaço livre, filesystem e crescimento/alerta. |
| Transferência | 4 TB | Suficiente em princípio para o portal interno; medir uso e confirmar política do plano. |
| Backup do provedor | Periodicidade semanal indicada | Complementar apenas. Não substitui Restic criptografado fora da VPS, retenção aprovada e restauração testada. |
| Tempo ligado observado | Mais de dez dias | Indício de disponibilidade, não evidência de atualização, monitoramento ou SLA. |

Hostname, endereço público e conta administrativa mostrados no painel foram deliberadamente omitidos deste repositório. A captura não comprova Docker, arquitetura, firewall, sincronização de horário, acesso restrito, contrato profissional, criptografia/restore do backup, DNS ou identidade operacional.

## VPS disponível — inventário técnico sanitizado

| Item | Evidência coletada no host | Avaliação |
|---|---|---|
| Kernel/arquitetura | Linux 6.8, x86_64 | Compatível com as imagens previstas. |
| CPU | 1 processador disponível | Confirma o limite do plano; benchmark com PostgreSQL e Chromium continua obrigatório. |
| Memória | Aproximadamente 3,82 GiB | Compatível com os 4 GB nominais, com pouca margem operacional. |
| Disco raiz | Aproximadamente 47,39 GiB totais, 8,15 GiB usados e 39,23 GiB disponíveis | Atende a referência inicial; ainda exige monitoramento e estimativa de crescimento. |
| Docker Engine | 29.8.1 após manutenção | Build e execução do staging sintético validados no host. |
| Docker Compose | 5.5.1 após manutenção | Composição produtiva validada no host com dados exclusivamente sintéticos. |
| Firewall | UFW ativo | SSH preservado e entradas HTTP/HTTPS confirmadas para o proxy; banco permanece sem porta publicada. |
| Horário | Sincronização NTP ativa | Requisito técnico atendido no momento da coleta. |
| Acesso administrativo | Conta não privilegiada autenticada por chave pública, com elevação `sudo` validada | Acesso operacional básico confirmado; endurecimento do SSH e conta substituta ainda pendentes. |
| Manutenção do host | Reinicialização solicitada pelo sistema no login de 28/09/2026 | Investigar atualizações e reiniciar antes do staging. |
| Compartilhamento | A VPS já hospeda outro projeto de baixa movimentação | Medir consumo agregado, mapear dependências e combinar janela de manutenção; a baixa movimentação não comprova capacidade disponível. |

A coleta não leu hostname, IP, usuários, credenciais, variáveis de ambiente ou arquivos privados. Nenhuma configuração do host foi alterada.

### Fotografia agregada do host compartilhado em 28/09/2026

| Métrica | Resultado sanitizado | Avaliação |
|---|---|---|
| Carga de 1/5/15 minutos | 0,08 / 0,02 / 0,01 | Baixa no instante da coleta; não representa pico. |
| Memória disponível | Aproximadamente 3,12 GiB de 3,82 GiB | Há margem no instante da coleta. |
| Disco raiz disponível | Aproximadamente 39,22 GiB | Compatível com o staging, sujeito a retenção e alerta. |
| Containers existentes | 2 ativos de 2 | Ambos usam política `unless-stopped`; Docker está ativo e habilitado no boot. |
| Uso agregado dos containers | 0% de CPU e 20,07% da memória no instante da coleta | Ocioso no instante medido; não substitui benchmark concorrente. |
| Serviços com falha | 0 | Sem falha registrada pelo systemd no instante da coleta. |
| UFW | Ativo | Regra de entrada para SSH confirmada sem registrar endereços. |
| Reinicialização | Concluída de forma controlada | SSH, Docker e os 2 containers retornaram; zero serviço systemd falhou, o marcador de reboot desapareceu e o operador confirmou o funcionamento do projeto existente. |

Os números são uma fotografia pontual e não autorizam dimensionamento definitivo. Nenhum nome de container, serviço, projeto, usuário ou endereço foi registrado. Após o reboot, o banner informou 37 atualizações disponíveis, incluindo 3 atualizações de segurança padrão; elas não foram aplicadas e exigem revisão e nova janela controlada. O operador confirmou o teste funcional do projeto existente.

Com PostgreSQL, app e proxy do staging ativos, uma renderização Chromium sintética de 55 processos terminou em 13 segundos, com saída HTML/PDF íntegra, aproximadamente 3,03 GiB de memória ainda disponível e carga 0,54/0,31/0,20 após a execução. O resultado aprova apenas concorrência unitária e processamento manual; não autoriza jobs paralelos nem elimina a necessidade de monitoramento.

Depois de reiniciar os três serviços do novo projeto, PostgreSQL e aplicação retornaram saudáveis e o proxy voltou em execução. As contagens exclusivamente sintéticas permaneceram em um usuário técnico, quatro parceiros e três versões de relatório; os artefatos privados HTML/PDF também permaneceram. O teste comprova persistência nesse reinício, não substitui backup externo nem recuperação de desastre.

### Manutenção do host em 28/09/2026

Os 37 pacotes simulados foram atualizados com zero remoção e zero pacote previamente retido. Docker Engine passou para 29.8.1 e Docker Compose para 5.5.1. Ao final, Docker estava ativo, os dois containers existentes permaneciam ativos, zero serviço systemd estava em falha e não havia novo marcador de reboot. Após reconectar o SSH, havia zero atualização disponível nos repositórios habilitados. O banner ainda oferecia uma atualização adicional via ESM Apps, serviço não habilitado; ela não foi aplicada. As portas TCP 80 e 443 estavam livres. O teste funcional posterior do projeto existente ainda deve ser confirmado pelo operador.

## Requisitos para selecionar a VPS

| Item | Requisito inicial | Validação no PDF-8 |
|---|---|---|
| Contrato | Permitir uso profissional e tratamento dos dados envolvidos | Revisar termos atuais do provedor |
| Sistema | Linux x86_64 mantido pelo provedor | Registrar distribuição e versão LTS |
| Capacidade | Referência de 2 vCPU, 4 GB RAM e 40 GB de disco persistente | Medir app, PostgreSQL e Chromium com cenário sintético |
| Docker | Engine e Compose suportados | Build, subida, reinício e healthchecks |
| Rede | IP estável, firewall e DNS configuráveis | Expor somente HTTPS e administração restrita |
| HTTPS | Certificado automático e renovável | Testar emissão e renovação |
| Persistência | Volumes separados para PostgreSQL, fontes e relatórios | Reiniciar/recriar contêineres sem perda |
| Backup | Cópia criptografada fora da VPS | Restaurar banco e objetos em ambiente separado |
| Segredos | Arquivo protegido fora do Git e das imagens | Conferir permissões e ausência em logs |
| Operação | Responsável e substituto definidos | Testar atualização, rollback e incidente |
| Região | Localização e termos compatíveis com a política aprovada | Registrar região e transferência aplicável |

## Custo

A stack usa software sem licença paga. Uma franquia gratuita de VPS só poderá ser adotada se aceitar uso profissional, oferecer persistência e suportar a carga medida. Gratuidade e capacidade não são presumidas nem garantidas. Se nenhuma oferta atender, a produção dependerá de uma VPS paga ou continuará bloqueada.

## Informações ainda pendentes

- provedor e condições contratuais para uso profissional e tratamento dos dados envolvidos;
- capacidade efetiva e pico de CPU/RAM durante PostgreSQL e Chromium;
- consumo e requisitos do outro projeto hospedado, sem registrar seu conteúdo ou credenciais;
- janela operacional recorrente para manutenção dos dois projetos;
- responsável operacional substituto para a conta administrada pelo titular;
- forma de acesso privado/VPN ou justificativa para exposição pública;
- Cloudflare R2 escolhido para o backup externo; bucket privado, credencial restrita, termos/localização e restauração ainda precisam ser validados;
- criptografia, localização, retenção e restauração do backup semanal do provedor;
- restauração do backup externo em ambiente isolado; a retenção local já foi implementada e testada com corpus sintético;
- responsável operacional e substituto.

Nenhum desses itens autoriza contratação, criação de recurso ou implantação. Eles serão tratados no PDF-8 após a homologação PDF-7.
