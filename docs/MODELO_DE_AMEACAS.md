# Modelo de ameaças e controles — etapa 10

**Data:** 23/09/2026. **Escopo efetivamente testado:** portal interno, worker e ingestão PDF locais com dados/arquivos sintéticos. Este documento é uma revisão técnica, não aprova tratamento/publicação de dados reais nem substitui avaliação jurídica de LGPD.

## Fronteiras e ativos

O navegador interno recebe apenas HTML/PDF projetado por allowlist. O servidor FastAPI consulta metadados no PostgreSQL; os artefatos sintéticos ficam em `output/` e só são lidos por chave controlada/rota autenticada em desenvolvimento. Advbox é uma origem separada de leitura, com token em variável de ambiente; a carga integral real não foi executada. Em produção futura, PostgreSQL e objetos privados serão externos à Vercel, ainda sem provedor escolhido.

| Ativo/fronteira | Ameaça | Controle implementado/verificado | Risco ou decisão pendente |
|---|---|---|---|
| Token Advbox | Exposição em código, URL, log, PDF ou redirecionamento; uso indevido após incidente | `.env` ignorado, `SecretStr`, cliente GET-only/HTTPS sem seguir redirecionamento, saída sanitizada; nenhuma chamada real nesta etapa | Cofre de segredos, escopo somente leitura se disponível, inventário de quem pode rotacionar e prova de rotação P-008 |
| PostgreSQL | Leitura/escrita não autorizada, vazamento em backup, recuperação incompleta | UUID/FK/constraints, sessões/auditoria no banco, ausência de payload bruto; banco local isolado no Compose | Provedor, SSL, criptografia em repouso, menor privilégio, backup/restauração e retenção P-002/P-012 |
| HTML/PDF | IDOR, travessia de caminho, arquivo público, conteúdo livre sensível | Autorização no servidor, vínculo versão→parceiro conferido, chave sintética por allowlist/regex, `output/` sem montagem estática, produção recusada, HTML autoescapado e PDF derivado da mesma projeção | Storage privado, revogação, retenção, testes do provedor e homologação P-014 |
| Login/sessão | Adivinhação de senha, fixação, CSRF, sessão roubada | Argon2id, token aleatório só com hash no banco, rotação no login, cookie `__Host-`/Secure/HttpOnly/Strict, CSRF, limite local de falhas, revogação e desativação administrativa | SSO/MFA, recuperação de conta, IP efetivo atrás de proxy e proteção distribuída P-013 |
| Formulários/erros | Corpo grande, entrada malformada, detalhe interno em resposta | Leitura limitada a 4 KiB, limite de campos, validação de UUID/enum, páginas de erro genéricas | Limite de corpo no edge/WAF a confirmar na implantação |
| Upload PDF-fonte | Arquivo falso, excessivo, criptografado, anotado, com formulário/anexo; nome malicioso; duplicação; exposição pública | Admin + sessão + CSRF; assinatura/MIME/extensão; 20 MiB/200 páginas/A4; inspeção de objetos sem texto; hash; chave opaca; nenhuma rota de download; storage local atômico e recusado em produção | Limite no edge, antivírus/sandbox se exigido, storage externo, retenção e limpeza de órfãos P-014/P-019 |
| Logs/trilha | Dados de busca, token, senha, URL completa ou payload persistidos | Eventos de auditoria com ações/motivos permitidos e IDs opacos; log JSON só com ação, tipo e correlação; comando Uvicorn sem access log bruto | Verificar logs da plataforma Vercel, retenção, integridade, alertas e acesso operacional P-011/P-012 |
| Administração/vínculo | Conta privilegiada indevida, mudança de parceiro sem autoria | Rotas administrativas exigem `portal_admin`; CLI de conta exige autenticação administrativa após bootstrap, revoga sessões e registra evento | Não há importação CSV nem tela de mudança de vínculo; quando forem implementadas, exigir validação de tipo/ID/vigência, aprovação e evento `link_changed` antes de ativar |
| Separação entre parceiros | Versão de um parceiro aberta pela URL de outro; acesso externo extrapolado | Rota confere `version.partner_id`, usa UUIDs, testes negativos; não há conta externa por parceiro | Os papéis internos podem ver toda a carteira. Acesso externo exigirá autorização por parceiro em todas as consultas, objetos, jobs e testes de isolamento antes de existir |
| URL compartilhável | Link de PDF enviado/reenviado sem autorização | Não existem URLs assinadas ou públicas. Download exige sessão interna e devolve `attachment`/`no-store` | Se URL assinada for aprovada: prazo curto, escopo parceiro/versão, revogação e auditoria P-014 |
| Backup/incidente | Perda, vazamento ou restauração de dados desatualizados | Runbook abaixo define contenção; nenhuma cópia real foi gerada nesta fase | Plano de backup/restauração testada, operador, canal de alerta, exercício de incidente e responsabilidades P-002/P-011/P-012 |

## Matriz mínima de autorização

| Ação | Anônimo | Leitor interno | Administrador interno | Parceiro externo |
|---|---|---|---|---|
| Login e CSS público | Permitido | Permitido | Permitido | Não implementado |
| Lista/detalhe/HTML/PDF sintético | Negado | Permitido | Permitido | Não implementado |
| Solicitar geração quando não há versão | Negado | Permitido | Permitido | Não implementado |
| Regenerar uma versão existente | Negado | Negado | Permitido | Não implementado |
| Criar/desativar conta ou revogar sessões | Negado | Negado | Administrador autenticado no CLI; primeiro bootstrap é exceção | Não implementado |
| Alterar vínculo parceiro–carteira | Não existe rota/importador nesta fase | Não existe | Não existe | Não implementado |
| Enviar PDF-fonte para quarentena | Negado | Negado | Permitido provisoriamente enquanto P-018 estiver pendente | Não implementado |

Ocultar um botão não concede/nega autorização; os testes chamam a rota diretamente. Os UUIDs evitam enumeração sequencial, mas **não** substituem a checagem de autorização. Um leitor interno é autorizado a ver todos os parceiros sintéticos; isso não é um modelo de acesso externo por parceiro.

## Auditoria e redaction

`audit_events` registra ação de catálogo, detalhe, HTML, download, pedido de geração, upload PDF aceito/rejeitado/duplicado/falho, login aceito/negado/limitado, logout, negação de artefato e gestão de conta/sessões. O ator é ID interno quando conhecido; entidade é somente tipo/UUID; correlação é criada no servidor. Motivos são códigos fixos. Não se grava caminho, query string, nome de arquivo, documento, conteúdo do PDF, IP em claro, senha, cookie, corpo de resposta, texto de andamento nem token. O log da aplicação contém somente JSON com ação, tipo e correlação. Falha de escrita da trilha impede a operação correspondente, preservando fail-closed. Não foi criado evento `link_changed` real porque não existe comando de alteração de vínculo; a ação está reservada e deverá ser exigida na futura implementação.

O servidor Docker foi configurado para não emitir access log bruto de URLs. Isso **não comprova** como a Vercel registrará URLs/erros; a configuração de logs do provedor e qualquer coleta de observabilidade precisa de inspeção antes da produção. A [orientação OWASP sobre logs](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html) recomenda não registrar diretamente IDs de sessão, tokens, senhas, dados pessoais sensíveis ou connection strings.

## Dependências e execução de contêiner

A verificação mais recente teve 121 testes aprovados; Ruff e `alembic check` passaram. Após atualização do `pip` da imagem base, `pip-audit` no contêiner de desenvolvimento não encontrou vulnerabilidades conhecidas nas dependências publicadas. O pacote próprio `partner-reports` foi ignorado pela ferramenta porque não está no PyPI; esse resultado **não** é auditoria do código próprio nem prova de ausência de falhas futuras. A imagem de produção foi recompilada com o novo Dockerfile e executou como UID 999, `USER app`; app/worker de desenvolvimento também executaram como UID 999. Continuam necessários escaneamento contínuo das imagens/dependências, atualização controlada e validação no host final.

## Procedimento de rotação/revogação do Advbox

Somente o responsável da conta Advbox, fora do portal, deve revogar o token anterior e gerar um novo conforme a interface/documentação oficial. Registrar internamente hora, operador e serviços afetados **sem copiar o valor**. Atualizar o segredo no `.env` local ou futuro cofre de segredos, reiniciar o processo que lê a credencial, executar uma auditoria GET mínima e sanitizada, confirmar HTTP/autorização e revogar o token antigo. Se a plataforma não permitir dois tokens em sobreposição, programar janela curta de indisponibilidade e usar o último relatório válido; não colar o token em ticket, chat, comando de shell, URL ou repositório. Em suspeita de vazamento, suspender sincronizações antes da rotação e avaliar o alcance do acesso com o fornecedor.

## Retenção, exclusão e backup

- Sessões expiram em 20 minutos (anônimas) ou 8 horas (autenticadas); o CLI `portal-user purge-expired --actor-login ...` elimina registros expirados. Falhas de login com janela encerrada há mais de 15 dias também podem ser purgadas. A desativação/revogação de uma conta elimina imediatamente suas sessões ativas.
- Execuções/erros de sync têm referência técnica preliminar de 90 dias em `docs/MODELO_DE_DADOS.md`; não há limpeza automática. Carteira, vínculos, financeiro, relatórios, objetos e auditoria aguardam política jurídica/operacional aprovada (P-012). **Não presumir retenção indefinida nem apagar em massa antes de mapear obrigações e backups.**
- Para produção, exigir backup criptografado e protegido do PostgreSQL e dos objetos, retenção definida, controle de acesso e restauração testada em ambiente separado. Rollback de código não restaura dados.

## Resposta a incidente

1. Preservar evidência técnica mínima (IDs de execução/evento e horários, sem copiar payload pessoal para chat/ticket); acionar imediatamente o responsável operacional e privacidade. Se necessário, bloquear downloads, desativar contas/revogar sessões e suspender a sincronização.
2. Contenção: revogar/rotacionar token afetado, isolar credenciais de banco/storage, impedir novos jobs e manter a última versão íntegra somente se seu acesso for seguro. Não apagar logs antes de preservação controlada.
3. Determinar escopo: ambientes, períodos, parceiros, tipos de dados e acesso efetivo. Validar integridade das versões e dos backups; corrigir a causa e testar restauração em ambiente separado.
4. A decisão sobre comunicação à ANPD e titulares é do controlador/encarregado e depende da avaliação de risco e enquadramento aplicável. Consultar a [página oficial de comunicação de incidentes da ANPD](https://www.gov.br/anpd/pt-br/canais_atendimento/agente-de-tratamento/comunicado-de-incidente-de-seguranca-cis) e a regra vigente imediatamente; não esperar a investigação técnica terminar para escalar internamente.
5. Reabrir acesso por aprovação documentada, com monitoramento reforçado, rotação completa e registro das ações. Conduzir revisão pós-incidente e teste de não regressão.

## Pendências que impedem produção

P-005 foi superada pelo ADR-002. P-001/P-002/P-006/P-007/P-008/P-011/P-012/P-013/P-014/P-015/P-016/P-018/P-019/P-020/P-023 permanecem abertas. Em especial, faltam SSO/MFA ou decisão formal de identidade, isolamento externo por parceiro, papéis definitivos, retenção do PDF-fonte, storage privado, classificação/aprovação do conteúdo, provedor/backup/restauração, logs/alertas do host final e revisão contratual. O [guia de segurança da ANPD](https://www.gov.br/anpd/pt-br/centrais-de-conteudo/materiais-educativos-e-publicacoes/processo-guia-orientativo-sobre-seguranca-da-informacao-para-agentes-de-tratamento-de-pequeno-porte.pdf) orienta medidas técnicas e administrativas; os controles locais aqui demonstrados são apenas parte dessa governança.
