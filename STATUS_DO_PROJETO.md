# Status do projeto

**Atualizado em:** 23/09/2026  
**Escopo acompanhado:** etapas 0 a 12 do plano original e trilha PDF-0 a PDF-9 do plano revisado  
**Estado geral:** etapas 0 a 10 e PDF-1 implementadas tecnicamente. A etapa 11 original foi redirecionada: a Advbox não autorizará as rotas internas e a equipe aprovou o fluxo de exportação manual do PDF por parceiro. PDF-0 formalizou contrato/ADR e PDF-1 implementou ingestão privada somente com fixtures sintéticas; P-005 foi encerrada/superada sem apagar o histórico. Não há parser, OCR, API real no fluxo, revisão ou publicação.

## Quadro de acompanhamento

| Etapa | Resultado esperado | Status | Evidência de conclusão atual | Pendências | Próxima ação |
|---:|---|---|---|---|---|
| 0 | Inventário da hospedagem e do repositório | Concluída com pendências registradas | Diretório auditado; referências localizadas sem alteração; Vercel Hobby e domínio corporativo registrados; máquina local e ferramentas inspecionadas; decisões atualizadas. | Plano Vercel profissional, host final, DNS, provedores de dados/storage e operação. | Resolver itens de conta/contrato antes das etapas que dependem deles. |
| 1 | Fundação técnica e documentação viva | Concluída | Git inicializado; estrutura modular, `pyproject.toml`, `.gitignore`, `.env.example`, configuração tipada, `/health`, Dockerfile, Compose, entrada Vercel, README e AGENTS criados; 4 testes, lint, formatação, builds e healthchecks aprovados. | Dois avisos de depreciação em dependências de teste, sem falha; primeiro commit aguarda revisão. | Preparar com segurança a etapa 2, sem iniciar banco de domínio ou portal. |
| 2 | Auditoria segura da API real | Concluída | Autenticação confirmada; sete recursos responderam HTTP 200; campos, relações, paginação e totais foram registrados de forma sanitizada. | Manter token somente no `.env` local e reauditar quando o contrato da API mudar. | Usar os contratos observados nas próximas etapas, sem persistir respostas brutas. |
| 3 | Estratégia de vínculo parceiro–carteira | Concluída com carga inicial pendente | Listagem integral validada: 4.210 clientes, 4.350 processos, zero IDs duplicados e zero campos diretos de parceiro; ADR-001 adota mapeamento por IDs; 100% classificados, zero múltiplos e todos ainda sem vínculo. | Resolver 21 referências processo–cliente ausentes; cadastrar/aprovar o mapeamento inicial antes de publicar relatórios. | Na etapa 4, materializar tabela, vigência, auditoria e restrições do ADR-001. |
| 4 | Banco e contratos de dados | Concluída | Modelo normalizado, contratos Pydantic, migration `20260915_0001`, testes de integridade e idempotência; downgrade/upgrade, `alembic check`, 36 testes, Ruff e build Docker aprovados. | Seleção do PostgreSQL externo e aprovação dos prazos jurídicos de retenção antes da produção. | Usar os contratos e constraints na etapa 5. |
| 5 | Sincronização multiparceiro | Implementada; carga real integral pendente | Cliente GET-only, reconciliação paginada, hash, checkpoint transacional, dead-letter, CLI e migration `20260916_0002`; 44 testes passaram. `dry-run` real leu uma página por coleção sem persistir dados. | Aprovar a carga integral na homologação; resolver referências ausentes e vínculos iniciais; ausência de cursor/snapshot na API continua uma limitação. | Preservar o lote técnico e executar carga integral somente no portão de homologação; etapa 6 pode começar com dados sintéticos. |
| 6 | Indicadores e visão canônica do relatório | Implementada tecnicamente; aprovação de negócio pendente | `DICIONARIO_INDICADORES.md`, `ReportViewModel`/visão interna tipados, regras de contagem e portões, 20 testes unitários sintéticos específicos; 64 testes totais após verificação completa. | P-006/P-007: semântica dos KPIs, status jurídico, distribuição, financeiro e campos externos; adaptador de leitura real e homologação. | Usar somente prévia sintética na etapa 7; não publicar dados reais. |
| 7 | HTML/PDF automatizado | Implementada e validada localmente; publicação bloqueada | Projeção externa com allowlist, Jinja2/CSS responsivo e de impressão, Playwright/Chromium; paleta preto/dourado aplicada; três amostras sintéticas A4 inspecionadas (1, 1 e 3 páginas); testes, Ruff e documentação em `docs/RELATORIO.md`/`docs/DESIGN_SYSTEM.md`. | P-006/P-007, storage privado, homologação real e spike de Chromium no runtime Vercel; imagem de produção ainda sem navegador. | Reutilizar a renderização somente após aprovação e integração com armazenamento privado. |
| 8 | Portal multiparceiro | Implementada tecnicamente em ambiente local; produção bloqueada | FastAPI/Jinja2 com login Argon2id, sessão PostgreSQL, CSRF, limite de tentativas e papéis; lista, busca, filtros, paginação, detalhe, histórico, HTML/PDF sintéticos e solicitação de regeneração; 94 testes totais, Ruff, migration sem deriva, capturas 1280/375 px e HTTP local aprovados. | P-005 está superada; permanecem P-006/P-007, decisão SSO/identidade P-013, storage privado P-014, integração do novo fluxo PDF e revisão de segurança. | Reutilizar o portal somente nas etapas PDF posteriores, mantendo dados reais bloqueados. |
| 9 | Agendamento e processamento incremental | Implementada tecnicamente em ambiente local sintético; integração real pendente | Migration `20260917_0004`; ciclo diário idempotente, hash de revisão, worker com lease/heartbeat, retry, exclusão mútua e versão validada após HTML/PDF; 101 testes, quatro jobs sintéticos concluídos, PDF A4 inspecionado. | Executor de produção P-015, storage P-014, plano Vercel adequado, portões de negócio e homologação antes de sincronização/publicação reais. | Manter worker restrito ao desenvolvimento; revisar segurança na etapa 10. |
| 10 | Segurança, LGPD e isolamento | Concluída tecnicamente no ambiente local sintético; produção bloqueada | Modelo de ameaças, matriz de acesso, eventos de auditoria allowlisted, gestão/revogação administrativa, logs mínimos, cabeçalhos de segurança e testes negativos; 105 testes totais, Ruff e `alembic check` aprovados; auditoria de dependências sem vulnerabilidades conhecidas no ambiente verificado. | P-005 está superada; permanecem P-002/P-006/P-007/P-008/P-011/P-012/P-013/P-014/P-015/P-016 e validação no host final; plano Hobby não aprovado para uso profissional. | Submeter regras, papéis, retenção e identidade/storage à aprovação antes de dados reais. |
| 11 | Carga completa e homologação | Redirecionada para o plano de importação PDF | `dry-run` oficial concluído sem persistência; a API contém os processos, mas não a identidade do parceiro. Em 23/09, o responsável informou que a Advbox não autorizará as rotas internas; PDF-0 formalizou o PDF manual como fonte do vínculo. | Homologar ingestão, parser e reconciliação; aprovar P-006/P-007/P-018 a P-022 e autorizar a persistência após novo dry-run. | Obter aceite do contrato/ADR e executar somente PDF-1, sem parser ou API real. |
| 12 | Implantação na Vercel | Não iniciada; bloqueio conhecido | Destino e domínio corporativo definidos; conta atual é Hobby/Free e não é elegível para uso profissional. | Plano Pro ou adequado, host final, projeto Vercel, DNS, PostgreSQL/storage, backup, homologação e autorização explícita. | Resolver o plano antes de preparar a implantação de produção. |

## Trilha revisada — importação de PDF

| Etapa | Resultado esperado | Status | Próxima ação/portão |
|---|---|---|---|
| PDF-0 | Contrato da importação e ADR | Concluída documentalmente; requisitos refinados | Contrato v1.1, ADR-002, prioridades do escritório, precedência das fontes, inspeção sanitizada e pendências registrados; nenhuma alteração de código/banco. |
| PDF-1 | Upload privado, storage e modelo do lote | Concluída em desenvolvimento/teste sintético | Migration `20260923_0005`, formulário admin + CSRF, validação estrutural, hash/deduplicação, lifecycle, auditoria e storage local com recusa em produção. |
| PDF-2 | Parser estrutural versionado | Próxima etapa; aguarda aceite de PDF-1 | Usar somente fixtures sintéticas e manter OCR/API real/publicação fora do escopo. |
| PDF-3 | Reconciliação com a API oficial | Aguardando PDF-2 | Manifesto determinístico e falha segura para layout desconhecido. |
| PDF-4 | Revisão humana auditável | Aguardando PDF-3 | Categorias de correspondência e papéis definidos. |
| PDF-5 | Conteúdo e minimização | Aguardando PDF-4 | P-006/P-007 e matriz campo a campo aprovadas. |
| PDF-6 | Relatório/versionamento ponta a ponta | Aguardando PDF-5 | Lote aprovado produz visão publicável por allowlist. |
| PDF-7 | Homologação privada real | Aguardando PDF-6 | Autorização específica, corpus privado e política de retenção. |
| PDF-8 | Infraestrutura e implantação | Aguardando PDF-7 | GO técnico, plano Vercel adequado, banco/storage/jobs/backup aprovados. |
| PDF-9 | Go-live assistido | Aguardando PDF-8 | Staging, restauração, isolamento e operação aprovados. |

## Evidências da etapa 0

- Os três documentos-base foram lidos integralmente.
- O diretório não contém repositório Git.
- Não existe código de aplicação ou configuração de execução; o conteúdo técnico auxiliar está restrito a `tmp` e corresponde à análise anterior.
- Os dois materiais de referência indicados foram encontrados por verificação somente leitura.
- Nenhum dado pessoal dos materiais de referência foi transcrito para os documentos criados.
- Nenhuma integração, portal, banco, dependência ou configuração de produção foi implementada.
- A máquina local foi inspecionada sem alteração: hardware, disco e ferramentas disponíveis foram registrados.
- A documentação oficial atual da Vercel foi consultada para runtime Python, limites, filesystem, banco externo, domínio e HTTPS.

## Evidências da etapa 1

- Docker Desktop validado: Engine 29.7.2 e Compose 5.5.0.
- Imagens de desenvolvimento e produção construídas com Python 3.12.
- PostgreSQL 17 e aplicação iniciaram com healthchecks saudáveis.
- Requisição externa ao contêiner retornou somente `{"status":"ok"}` em `/health`.
- `pytest`: 4 testes aprovados; 2 avisos de depreciação originados em Starlette/FastAPI e AnyIO.
- `ruff check .`: aprovado sem ocorrências.
- `ruff format --check .`: 24 arquivos já formatados.
- Compose validado usando `.env.example`; nenhum arquivo `.env` ou segredo real foi criado.
- Nenhuma chamada ao Advbox, implantação Vercel, schema de negócio, portal ou relatório foi implementado.

## Evidências da etapa 2

- Contrato oficial atual do Advbox revisado para autenticação e endpoints GET de configurações, clientes, processos, movimentações, histórico e transações.
- Comando `audit-advbox` isolado da aplicação web e de qualquer sincronizador futuro.
- Cliente não expõe escrita, rejeita métodos diferentes de GET e não segue redirecionamentos de login.
- Ritmo máximo de 20 GET/minuto; timeout e retentativa exponencial limitada com jitter para HTTP 429, 5xx e falhas transitórias.
- Tratamento explícito e sem corpo de resposta para redirecionamento, 401, 403, 404, 429 e 5xx.
- Sanitização reduz respostas a códigos, durações, contagens, paginação e caminhos/tipos/nulos de campos; valores e IDs reais não são persistidos.
- `docs/ADVBOX_API_AUDIT.md` e `docs/VINCULO_PARCEIRO_CARTEIRA.md` criados sem dados pessoais.
- `pytest`: 17 testes sintéticos aprovados; 2 avisos de depreciação de dependências, sem falhas.
- `ruff check .` e `ruff format --check .`: aprovados.
- Configuração Compose validada; o ambiente de desenvolvimento usa explicitamente o código montado em `src`.
- Antes da credencial ser configurada, a execução sem token foi testada e parou antes de qualquer chamada, exibindo apenas instrução segura.
- Em 15/09/2026, o `.env` local ignorado pelo Git foi configurado pelo responsável e a auditoria real foi autorizada e concluída.

## Evidências da etapa 3

- Auditoria amostral real concluída: `settings`, `customers`, `lawsuits`, `last_movements`, `transactions`, `movements` e `history` responderam HTTP 200.
- Varredura integral GET-only percorreu 43 páginas de clientes e 44 páginas de processos no teto de 20 requisições/minuto.
- Foram observados 4.210 clientes e 4.350 processos, sem IDs duplicados e sem campo direto de parceiro.
- Origem tem cobertura nos clientes, porém 4.167 processos reúnem múltiplas origens e somente 183 possuem origem única; a alternativa foi rejeitada.
- Pasta está ausente em 150 processos; responsável técnico não equivale a parceiro; ambos foram rejeitados como regras automáticas.
- Foram contados 8.957 relacionamentos processo–cliente e 21 IDs relacionados ausentes da coleção de clientes.
- `ADR-001-vinculo-parceiro-carteira.md` decidiu por mapeamento administrável com ID técnico, vigência, fonte, status e auditoria.
- Validador determinístico implementado com saída exclusiva de contagens; nomes e textos livres não participam da chave.
- Resultado atual: clientes 0 vinculados/4.210 sem vínculo/0 múltiplos; processos 0 vinculados/4.350 sem vínculo/0 múltiplos; referências inexistentes no mapeamento 0.
- `pytest`: 22 testes sintéticos aprovados; 2 avisos de depreciação de dependências, sem falhas.
- `ruff check .` e `ruff format --check .`: aprovados antes da documentação final.
- Nenhum valor de campo, nome, token, cabeçalho, resposta bruta ou identificador real foi incluído nos relatórios ou logs.

## Evidências da etapa 4

- `docs/MODELO_DE_DADOS.md` documenta diagrama, dicionário, sensibilidade, retenção e pendências.
- Modelos SQLAlchemy normalizados e contratos Pydantic implementados; não há coluna de payload bruto da API.
- A migration `20260915_0001` foi aplicada no PostgreSQL 17 local, revertida e reaplicada após confirmar zero registros nas tabelas da aplicação.
- `alembic check` na imagem reconstruída: nenhuma operação pendente ou deriva entre modelos e banco.
- Constraint de exclusão impede períodos ativos sobrepostos para a mesma entidade; FKs compostas vinculam ID interno e ID Advbox correspondente.
- Testes de integridade, unicidade, idempotência, Decimal/zero/ausência, vigência e contratos passaram: 36 testes no total, com dois avisos de depreciação de dependências.
- `ruff check .` e `ruff format --check .` aprovados; build da imagem de desenvolvimento aprovado com migrations incluídas.
- Nenhuma sincronização de produção, carga de dados reais, portal ou publicação foi iniciada.

## Evidências da etapa 5

- `AdvboxClient` expõe somente as quatro coleções paginadas confirmadas e reutiliza timeout, retry, `Retry-After` e limitador de 20 GET/minuto em um único processo.
- `SyncRunner` confirma upserts, relações processo–cliente, hashes, parceiros impactados e checkpoint na mesma transação por página. Erros guardam apenas código e offset para retomada/reprocessamento.
- Sem `updated_at` confirmado, `incremental` usa reconciliação paginada e hashes; mudanças de `totalCount` durante um lote interrompem a execução.
- Migration `20260916_0002` aplicada; 44 testes sintéticos, Ruff e formatação aprovados. Dois avisos de depreciação de dependências permanecem sem falha.
- `dry-run` real limitado a uma página de cada coleção: 100 itens por recurso; totais informados pela API: 4.213 clientes, 4.353 processos, 12.721 transações e 4.302 últimos andamentos. Nenhum item real foi gravado.
- Operação, retomada e limites estão em `docs/OPERACAO_SINCRONIZACAO.md`. Não foram gerados relatórios, portal ou publicação.

## Evidências da etapa 6

- `docs/DICIONARIO_INDICADORES.md` registra fonte, fórmula ou pendência, período, inclusão/exclusão, nulos e exemplo sintético por indicador.
- `ReportValue` exige valor para `available` (inclusive zero) e proíbe valor para estados indisponíveis; cada valor de negócio informa fonte, corte e validação quando aplicável.
- Visões interna e externa têm contratos separados. A externa não contém nome de cliente, documento, contato, número processual, título de andamento ou observação livre; nenhum endpoint ou publicação foi criado.
- Clientes únicos e processos distintos são derivados de vínculos ativos/vigentes e IDs estáveis. Conflitos, vínculos para entidade inexistente, fonte incompleta ou ausência de aprovação bloqueiam a prévia externa.
- Último andamento registrado é cronológico; relevância jurídica, status executivo, benefícios concedidos, em financeiro, em judicial, distribuições e repasse permanecem `pending_validation`.
- P-017 e cenários inspirados em P-004/P-026/P-030 foram reconciliados conceitualmente com dados sintéticos; divergências legadas não foram forçadas a coincidir.
- Testes específicos de fórmulas, sobreposição, nulidade, zero, vigência, corte, isolamento e privacidade passaram; verificação completa registrada abaixo.

## Evidências da etapa 7

- O mesmo `ReportViewModel` alimenta HTML e PDF. O template não recebe IDs internos, payload bruto, nomes, documentos, contato, observações livres ou texto de andamento.
- A allowlist e a validação de formatos controlados rejeitam dados não classificados; testes sintéticos cobrem documentos, segredos, saúde, HTML/script e escape.
- Seções financeiras e distribuições não aparecem sem fonte e regra validadas; ausência não é exibida como zero. PDF é gerado em bytes, sem persistência na função.
- Chromium foi instalado na imagem local de desenvolvimento; três amostras sintéticas foram renderizadas, convertidas em imagens e inspecionadas página a página em A4: 0 casos = 1 página, 1 caso = 1 página, 55 casos = 3 páginas. Cabeçalhos de tabela repetem e linhas permanecem inteiras.
- `docs/RELATORIO.md` registra layout, execução, portão de privacidade e limitações. Nenhum PDF foi publicado ou alimentado com dados reais.
- Paleta definida pelo responsável aplicada ao HTML e às três prévias PDF; capturas desktop/celular e páginas A4 foram inspecionadas. A tabela vira cartões na tela estreita; `#FFC14D` fica somente no hover do botão principal. A identidade futura do portal está em `docs/DESIGN_SYSTEM.md`, sem iniciar a etapa 8.
- Verificação final: 87 testes aprovados (incluindo geração real dos três PDFs, larguras HTML de 375/1280 px e aplicação da paleta no navegador), dois avisos de depreciação de dependências sem falha; Ruff lint/formatação aprovados, `alembic check` sem deriva. A imagem de produção foi construída e contém template/CSS, mas não o binário Chromium.

## Evidências da etapa 8

- Migration aditiva `20260916_0003` aplicada no PostgreSQL local; `alembic check` sem operações pendentes.
- Credenciais locais usam Argon2id e provisionamento interativo, sem usuário/senha padrão. Sessões opacas e tentativas de login são persistidas no PostgreSQL; cookie `__Host-`/Secure/HttpOnly/SameSite, CSRF, rate limit e papel administrativo testados.
- Quatro parceiros `SYNTHETIC-*` e três versões `validated` foram adicionados ao banco de desenvolvimento; nenhum dado real foi carregado. Artefatos só são servidos por chaves sintéticas fixas em desenvolvimento/teste e são recusados em produção.
- Busca, filtro, paginação, detalhe, histórico, abertura HTML, download PDF, isolamento entre parceiros e solicitação idempotente de geração passaram em sete testes específicos.
- Capturas sintéticas de login, lista e detalhe em desktop 1280 px e celular 375 px foram inspecionadas visualmente, sem rolagem horizontal. A paleta e a cor de hover final foram verificadas no Chromium.
- Verificação final: 94 testes aprovados, dois avisos de depreciação de dependências sem falha; Ruff lint e formatação aprovados. `/portal/login` e `/health` responderam HTTP 200 no app local.
- O serviço local ficou iniciado. Nenhuma credencial de usuário foi criada automaticamente; o responsável deve usar o comando interativo documentado em `docs/PORTAL.md` para entrar. Nenhum relatório real foi publicado.
- O Chromium acessou `http://localhost:8000/portal/login` diretamente, confirmou o título da página e aceitou um cookie de sessão `Secure` no `localhost`.

## Evidências da etapa 9

- Migration aditiva `20260917_0004` aplicada ao PostgreSQL local; `alembic check` sem deriva.
- `synthetic_portfolios` fornece apenas cenário e revisão de demonstração; nenhuma rotina nova acessa o Advbox real. Um ciclo cria `sync_run` sintético, registra IDs de parceiros alterados e enfileira apenas diferenças de hash.
- `worker-loop` opt-in no perfil Compose `automation` ou comandos `run-now`, `work-once`, `status` e `retry-failed`. O contêiner `worker` iniciou e permaneceu em execução junto do app/postgres saudáveis. Exclusão mútua de ciclo no banco, índice único parcial por parceiro, reivindicação com `SKIP LOCKED`, lease/heartbeat, timeout, retry limitado, backoff e recuperação de abandono foram implementados.
- HTML/PDF novos só ficam visíveis após validação e commit de `report_versions`; falha no PDF, mudança de fonte ou regressão de contagens preserva a versão anterior. O storage local e o próprio worker recusam produção.
- Verificação operacional em 17/09/2026: quatro fontes sintéticas examinadas, quatro mudanças enfileiradas, quatro jobs concluídos e repetição da mesma chave sem novos jobs. PDF sintético de 55 processos inspecionado nas três páginas A4.
- Verificação da etapa 9: 101 testes aprovados (dois avisos de depreciação de dependências), Ruff lint/formatação e `alembic check` aprovados. `docs/RUNBOOK.md` registra operação e recuperação.
- Sem e-mail, carga integral real, cron Vercel ou publicação profissional. A arquitetura produtiva dos jobs permanece P-015.

## Evidências da etapa 10

- `docs/MODELO_DE_AMEACAS.md` cobre credencial Advbox, banco, artefatos, autenticação, logs, backups, administração, URLs, isolamento e incidente. Não foi criado acesso externo por parceiro nem importador CSV, que não estão no escopo aprovado.
- Eventos de login, visualização, download, geração, negação e gestão de contas são gravados em `audit_events` com ação/motivo permitidos, IDs técnicos e correlação criada no servidor. A inexistente alteração de vínculo tem ação reservada, não uma trilha fictícia.
- CLI interativo exige administrador autenticado depois do primeiro bootstrap, permite desativar conta/revogar sessões e limpar metadados de segurança vencidos. O portal ganhou limite de 4 KiB para formulários e cabeçalhos adicionais; Uvicorn não emite access log bruto da aplicação.
- Testes negativos cobrem download anônimo, versão de outro parceiro, travessia de caminho, erro com segredo sintético, conteúdo proibido na projeção HTML/PDF e ausência desse segredo em resposta/log/auditoria. PDF sintético foi extraído e inspecionado em memória; nenhum artefato real foi publicado.
- Verificação final: **105 testes aprovados**, dois avisos de depreciação de dependências; Ruff lint/formatação, `alembic check` e validação do Compose aprovados. Auditoria no contêiner de desenvolvimento com pip atualizado encontrou **zero vulnerabilidades conhecidas**; o pacote local `partner-reports` não existe no PyPI e foi excluído automaticamente dessa consulta. App e worker executam como UID 999. `.env` permanece ignorado pelo Git.
- A imagem de produção foi reconstruída com sucesso com `pip 26.2.1`; sua configuração é `USER app` e a execução confirmou UID 999. Durante o build, o Docker Desktop reiniciou; PostgreSQL e app locais foram religados, ambos ficaram saudáveis, o worker permaneceu ativo e `/health` voltou a responder HTTP 200. Isso não valida a execução na Vercel. Logs/backup/limites reais da Vercel e a geração PDF no runtime de produção continuam sem homologação. Nenhuma carga real, e-mail ou implantação foi executada.

## Evidências da etapa 11 — `dry-run`

- O coletor `homologation_cli` percorreu somente os quatro endpoints globais GET confirmados, reteve apenas projeções técnicas/count-only em memória e não persistiu payload, entidades, checkpoint ou relatório.
- Execução de 21/09/2026: 260 requisições em 13min02s, com zero HTTP 429, HTTP 5xx e erros de transporte. Totais estáveis: 4.226 clientes, 4.363 processos, 12.845 transações e 4.320 últimos andamentos; zero registros rejeitados e zero IDs duplicados.
- O banco contém quatro parceiros de demonstração `SYNTHETIC-*`, zero parceiro real e zero vínculo. As sete versões existentes também são sintéticas e foram excluídas do relatório de homologação. Consequentemente, 4.363 processos estão explicitamente sem vínculo e nenhum relatório real foi gerado.
- Qualidade registrada sem dados pessoais: 2.733 processos sem número, 659 clientes em múltiplos processos, 3.320 processos sem registro financeiro, 943 com múltiplos registros, 2.205 registros financeiros órfãos/sem processo válido, 44 processos sem último andamento e uma data futura. Financeiro e indicadores permanecem sem regra aprovada.
- `docs/HOMOLOGACAO.md` contém contagens, matriz de cenários, exceções e tratamento. O critério final da etapa 11 ainda não está atendido; a execução parou no portão anterior à carga persistente.
- Verificação após o ensaio: 108 testes aprovados, dois avisos de depreciação de dependências; Ruff lint/formatação, `alembic check` e validação do Compose aprovados. O banco confirmou zero clientes, processos, transações, andamentos e vínculos persistidos pelo ensaio.
- O responsável definiu o módulo Parceiros como fonte oficial. A API pública não documenta o recurso, mas duas capturas higienizadas da interface confirmaram `/content/partners` e `/content/friendship` com paginação, IDs técnicos e filtro numérico parceiro–processos. O filtro reduziu 19 compartilhamentos globais para 5 do parceiro escolhido; `account_id`, rota de edição e campo técnico `id` coincidem. Nenhum valor, nome, ID ou credencial foi transcrito, e os analisadores temporários foram removidos.
- O suporte confirmou que processos de parceiros constam nas requisições de processos e não há rota específica de parceiros. A verificação GET-only encontrou os 19 compartilhados entre 4.369 processos oficiais (19/19), mas nenhum campo de atribuição a parceiro. Foram 44 GETs, zero 429 e zero duplicidade; nenhuma resposta foi persistida e o comparador temporário foi removido.

## Evidências da etapa PDF-0

- `docs/CONTRATO_IMPORTACAO_PDF.md` define formato, pré-condições, precedência das fontes, metadados/manifesto mínimos, estados/transições, correspondência, rejeições e portões de revisão/publicação.
- `docs/ADR/ADR-002-fonte-carteira-pdf.md` compara rota interna, CSV, PDF e digitação manual e aceita o PDF como manifesto privado, preservando a API oficial para dados estruturados.
- P-005 foi marcada como encerrada/superada pela estratégia PDF, mantendo seu registro histórico; não será criado adaptador para as rotas internas.
- A inspeção estrutural sanitizada cobriu sete PDFs do mesmo gerador e 22 páginas no total: A4, camada de texto em todas as páginas, 1 a 5 páginas por arquivo, cabeçalho repetido nos multipágina, sem tabela nativa confiável e com continuação possível entre páginas.
- Nenhum nome de arquivo, texto extraído, nome, identificador, hash ou dado pessoal foi transcrito para documentação, teste ou log. Nenhum PDF original foi alterado.
- Nenhum código, migration, banco, upload, parser, OCR, chamada à API, persistência ou interface foi alterado/implementado nesta etapa.
- Permanecem decisões humanas P-018/P-019/P-020/P-006/P-007/P-022/P-023, com opção segura e ponto de bloqueio registrados no contrato.

## Evidência adicional — prioridades do escritório

- Um PDF real de 55 páginas foi analisado somente como artefato privado de requisitos. Ele possui camada de texto e 13 destaques amarelos nas páginas 1, 2 e 4.
- Somente categorias foram registradas: parte/cliente, tipo de ação/benefício, fase, financeiro detalhado, registro interno e andamento manual recente. Nenhum valor, nome, número, narrativa ou identificador foi transcrito.
- `docs/PRIORIDADES_CONTEUDO_ESCRITORIO.md` separa fonte oficial, uso interno, visão externa e perguntas de homologação para cada prioridade.
- O PDF anotado não será aceito como fonte de importação, fixture ou screenshot versionada. PDF-1 deverá rejeitar edição pós-exportação com `PDF_ANNOTATED_SOURCE`.
- O plano e os prompts PDF-1, PDF-2, PDF-3, PDF-5, PDF-6 e PDF-7 foram ajustados. A precedência permanece: PDF compõe carteira; API fornece dados estruturados; regras aprovadas definem projeção.
- P-023 foi aberta para homologar semântica e visibilidade com os usuários do escritório. Nomes, texto de andamento e registros financeiros internos continuam restritos enquanto P-006/P-007/P-023 estiverem pendentes.

## Evidências da etapa PDF-1

- `PrivatePdfStorage` e o adaptador local atômico usam chave opaca; o adaptador recusa operação em produção. O caminho padrão fica em `storage/pdf-imports`, ignorado pelo Git.
- O portal exige sessão, `portal_admin` e CSRF. Nome original não é persistido/logado e não existe download do PDF-fonte.
- Validação sintética cobre assinatura, MIME/extensão, 20 MiB, 200 páginas, A4 retrato, criptografia/estrutura, anotações/formulários/anexos e links classificados separadamente. Nenhuma extração de texto ocorre.
- Migration `20260923_0005` cria documento-fonte, lote, eventos e estrutura de revisão; o lote aceito termina em `quarantined` com histórico `uploaded -> quarantined`.
- SHA-256 torna reenvio idempotente. Auditoria usa ações/motivos catalogados e nunca grava conteúdo, caminho ou nome do arquivo.
- O PDF real anotado do escritório não foi usado como fixture nem enviado ao fluxo.
- Verificação final: 121 testes aprovados, Ruff lint/formatação e `alembic check` sem deriva; imagem de desenvolvimento reconstruída com `pypdf`/`python-multipart`. Permanece um aviso de depreciação do `TestClient` em dependência, sem falha.

## Próxima ação objetiva

Submeter PDF-1 e `docs/IMPORTACAO_PDF.md` à revisão técnica. Decidir P-018/P-019/P-020 antes dos respectivos portões e preparar P-023 para PDF-5. Após o aceite, executar somente PDF-2 com fixtures sintéticas, sem OCR, API real, implantação ou publicação.

## Observação de escopo

O Prompt 13 do plano original permanece apenas como histórico. O go-live agora é a etapa PDF-9 e só entra em execução após a homologação PDF-7 e a infraestrutura PDF-8.
