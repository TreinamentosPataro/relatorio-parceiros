# Portal interno multiparceiro — etapa 8

**Estado:** implementação e demonstração local com parceiros e arquivos exclusivamente sintéticos. Nenhum relatório real foi publicado. Produção continua bloqueada pelos portões de negócio, privacidade, hospedagem e armazenamento.

## Decisão de identidade

O inventário não confirmou SSO corporativo nem proxy de autenticação. Para validar o fluxo local sem assumir um provedor externo, a etapa 8 usa credenciais internas próprias: usuário `active`, papel `portal_viewer` ou `portal_admin`, senha com Argon2id, sessão opaca aleatória armazenada apenas como SHA-256 no PostgreSQL e cookie `__Host-` com `HttpOnly`, `Secure`, `SameSite=Strict` e `Path=/`. Não há usuário ou senha padrão. O provisionamento é manual via comando interativo; senhas não passam por argumentos, logs ou respostas. Antes da produção, o escritório deve confirmar se adotará SSO/proxy; se sim, as credenciais locais deverão ser desativadas ou substituídas por um adaptador de identidade com o mesmo contrato de papéis.

O login tem limite de cinco falhas por janela de 15 minutos por endereço técnico de origem, com chave hash no banco. Sessões de login anônimas expiram em 20 minutos; autenticadas, em oito horas. O token é renovado no login, revogado no logout e nunca guardado em claro no banco. Formulários POST exigem CSRF associado à sessão. A etapa 10 acrescentou CLI autenticado para desativar contas e revogar sessões, limpeza de sessões vencidas e trilha de auditoria. O IP efetivo atrás do proxy da VPS, SSO/MFA, recuperação de conta, retenção e defesa contra abuso ainda precisam de homologação produtiva.

## Fluxo de uso diário (F1, ADR-007)

Desde 01/10/2026, a advogada (conta `portal_admin` individual) usa um único caminho:

1. **Novo relatório** (`/portal/imports/new`, opcionalmente `?parceiro=<id>`): escolhe o parceiro, o **mês de referência** e o PDF exportado do módulo Parceiros. O período vai do dia 1 ao fim do mês; no mês corrente, termina hoje (D-053). Mês futuro é recusado. Reenviar o mesmo arquivo leva ao envio já existente, sem erro.
2. **Página do envio** (`/portal/imports/{id}`): mostra as etapas *Envio recebido → Conferência no Advbox → Aprovação → Relatório pronto* e se atualiza sozinha a cada 15 segundos enquanto o worker trabalha. Cada situação tem uma ação:
   - pendências: tabela com página do PDF, número/pasta, problema e o que fazer; botões **Conferir de novo** (relê o Advbox depois da correção) e **Descartar envio**;
   - tudo encontrado: botão único **Aprovar e gerar relatório**, que aprova, substitui um envio já aprovado do mesmo período, se houver só um, e enfileira a geração;
   - falha do processamento automático: **Tentar novamente**, que zera as tentativas (o mesmo PDF não pode ser reenviado);
   - relatório pronto: **Ver relatório** e **Baixar PDF**.
3. **Página do parceiro**: relatório atual com **Ver relatório** e **Baixar PDF**, últimos envios, histórico de versões e restauração de versão anterior recolhida.

Os botões "Solicitar geração" e "Regenerar apenas este parceiro" e as rotas `/open` e `/regenerate` foram removidos: no fluxo com PDF, a geração nasce da aprovação do envio. Identificadores, contagens da conferência e histórico de decisões ficam em **Detalhes técnicos**, recolhidos. A auditoria continua registrando cada ação.

## Fluxo implementado (histórico das etapas 8 a PDF-6)

1. `/portal/login` autentica usuário interno; demais rotas exigem sessão e papel de leitura.
2. `/portal/partners` lista parceiros ativos, busca por nome/código, filtra situação e pagina dez por página. Exibe a última sincronização global registrada, sem inferir que cada parceiro mudou nesse instante.
3. `/portal/partners/{id}` mostra situação, versão mais recente e até vinte versões de histórico.
4. HTML/PDF são lidos de uma versão persistida. A rota verifica que a versão pertence ao parceiro solicitado; não chama a API do Advbox.
5. Se não há versão pronta, “Solicitar geração” cria uma `report_generation_request` pendente, deduplicada por parceiro mediante bloqueio transacional e índice único parcial. O worker da etapa 9 consome apenas solicitações de fontes sintéticas em desenvolvimento; não processa carteiras reais. Apenas `portal_admin` pode solicitar regeneração específica; não há recarga completa da origem nessa ação.
6. Erros do portal recebem uma página genérica, sem stack trace ou detalhes internos.
7. A etapa PDF-1 acrescenta `/portal/imports/new` somente para `portal_admin`: recebe um PDF sintético/original não anotado, valida estrutura e limites sem extrair texto, deduplica por SHA-256 e mantém o lote em quarentena. A confirmação técnica não permite baixar o documento-fonte.
8. PDF-4 acrescenta `/portal/imports` e `/portal/imports/{id}` para lista, filtro, classificação por item e decisões auditadas. Somente `portal_admin` acessa essas rotas. Aprovar, rejeitar, substituir, corrigir por ID técnico e solicitar reprocessamento exigem CSRF, confirmação e revisão atual. A aprovação e os vínculos ficam restritos a parceiros `SYNTHETIC-*` fora de produção. Reprocessamento registra solicitação, sem execução automática. Nenhum relatório é publicado por essas ações.
9. PDF-6 permite ao administrador solicitar uma prévia sintética de lote aprovado. O worker cria uma versão privada `validated` somente após HTML/PDF completos; a origem do lote e as pendências de conteúdo aparecem no histórico sem expor o documento-fonte. Download exige sessão, parceiro correto e integridade dos dois artefatos. A restauração de versão anterior exige administrador, CSRF, confirmação e arquivos íntegros; permanece restrita ao ambiente local. Consulte `docs/RELATORIO_PDF6.md`.

O estado `desatualizado` é calculado quando há um registro de mudança daquele parceiro posterior à versão. `gerando` significa solicitação pendente/em execução ou versão ainda não validada; a etapa 8 **não** executa o job. `erro` vem de solicitação/versão falha. A lista não divulga detalhes de erros internos.

## Artefatos sintéticos e limite de produção

O adaptador local só reconhece as chaves fixas `synthetic/zero`, `synthetic/one` e `synthetic/many` e chaves opacas de versões sintéticas geradas pelo worker da etapa 9, com arquivos em `output/html` e `output/pdf`. Ele rejeita qualquer outra chave e todo acesso quando `APP_ENV=production`. Mesmo uma linha de banco marcada como `published` não é servida em produção nesta fase. `output/` está ignorado pelo Git e não é montado como pasta pública. A rota de download exige sessão e confere o vínculo versão–parceiro. A interface deverá ser adaptada para volumes privados persistentes da VPS e política de autorização/retirada na etapa apropriada.

O comando de seed é apenas para `APP_ENV=development` e cria quatro parceiros com códigos `SYNTHETIC-*`; três recebem versão sintética `validated` e um fica sem relatório. Ele é idempotente, mas **não** deve ser usado em banco com dados reais. O relatório em si continua submetido à allowlist da etapa 7; esta demonstração não aprova P-006/P-007 nem conteúdo jurídico/financeiro real.

O storage de ingestão local usa `PDF_STORAGE_ROOT=storage/pdf-imports`, pasta ignorada pelo Git. Ele aceita somente chaves opacas criadas pelo servidor e recusa operação em `APP_ENV=production`. O nome original não é armazenado ou logado. O adaptador deverá ser substituído por um provedor privado antes da produção; detalhes e limites estão em `docs/IMPORTACAO_PDF.md`.

## Execução local

Com Docker Desktop e `.env` local configurado, na raiz do projeto:

```text
docker compose up -d postgres
docker compose run --rm app alembic upgrade head
docker compose run --rm app python -m partner_reports.reports.preview_cli --output-root output
docker compose run --rm app seed-portal-demo
docker compose run --rm -it app portal-user create --login operador-demo --admin
docker compose up -d app
```

A senha do comando é digitada interativamente, sem eco. Acesse `http://localhost:8000/portal/login`. O cookie `Secure` exige `localhost` ou HTTPS; não use um hostname HTTP remoto para este teste. Não exponha a porta local à internet. Para uso sem direitos administrativos, crie outro usuário sem `--admin`.

No fluxo PDF-4, `PDF_FOUR_EYES=true` exige revisor diferente do autor do upload. `PDF_SYNTHETIC_CORRECTIONS=false` mantém exceções manuais bloqueadas por padrão. Essas opções existem para ensaios sintéticos; P-018/P-022 ainda precisam de decisão formal antes de uso real. A interface mostra apenas IDs e códigos técnicos dos itens, sem campos livres da origem. As capturas de lista e revisão sintéticas em 1280 e 375 px ficam em `output/preview/pdf4_*`, ignoradas pelo Git.

## Verificação e pendências

Os testes da etapa cobrem rotas, credencial correta/incorreta, cookie, CSRF, limite de login, papéis, paginação, busca, filtro, geração pendente idempotente e tentativa de acessar versão de outro parceiro. Login, lista e detalhe foram inspecionados em 1280 e 375 px, com capturas sintéticas em `output/preview/`; não houve rolagem horizontal. No fechamento da etapa em 17/09/2026, 94 testes passaram (dois avisos de depreciação de dependências), Ruff lint/formatação e `alembic check` passaram. O seed sintético foi aplicado ao banco de desenvolvimento e `/portal/login` e `/health` responderam HTTP 200 localmente. O Chromium aceitou a sessão `Secure` no `localhost`.

A fase 9 acrescentou um worker local com lease, heartbeat e versão sintética validada somente após HTML/PDF completos. A fase 10 registrou o modelo de ameaças, auditoria, revogação administrativa, logs estruturados/redigidos, cabeçalhos de segurança e testes de negação/vazamento; veja `docs/RUNBOOK.md` e `docs/MODELO_DE_AMEACAS.md`. Não usar este portal para dados reais antes de P-006/P-007, volumes privados, autenticação/segurança da VPS homologadas e carga de homologação autorizada.
