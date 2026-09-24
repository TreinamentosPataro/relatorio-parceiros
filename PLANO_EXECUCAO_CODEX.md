# Plano de execução no Codex — Plataforma de Relatórios de Parceiros

> **Adendo de 23/09/2026:** este documento preserva o histórico do plano original. As etapas 0 a 10 continuam válidas; o caminho da etapa 11 que dependia do cadastro interno de parceiros foi substituído por `PLANO_EXECUCAO_IMPORTACAO_PDF.md`, pois a Advbox não autorizará aquelas rotas. Não implemente o adaptador interno descrito neste histórico.

**Data:** 11/09/2026  
**Documentos de referência:** `ANALISE_TECNICA_AUTOMACAO_RELATORIO_PARCEIROS.md` e `ANALISE_VARIABILIDADE_MULTIPARCEIRO.md`  
**Objetivo:** construir, de forma incremental, uma plataforma multiparceiro que sincronize dados do Advbox, calcule indicadores, gere relatórios HTML/PDF e os disponibilize com controle de acesso.

## 1. Decisões já tomadas

1. A solução será **multiparceiro desde o primeiro fluxo completo**. P-017 será apenas um caso de reconciliação.
2. A API ADVBOX está ativada na assinatura, conforme a tela fornecida. O token deve ser tratado como segredo.
3. O portal web será a interface principal. O PDF será uma versão fechada, compartilhável e auditável do relatório.
4. A extração será feita em lote e armazenada localmente. Ao clicar no parceiro, o sistema servirá um relatório já gerado ou uma versão em cache; não fará uma extração completa do Advbox naquele momento.
5. A primeira versão será um portal interno autenticado. Acesso direto por parceiros externos será uma fase posterior, pois exige isolamento rigoroso por parceiro, recuperação de senha, política de sessão e suporte operacional.
6. A solução evitará serviços pagos obrigatórios e usará o servidor que o escritório já possui.
7. Integração com o Advbox será somente leitura até que o escritório aprove explicitamente qualquer operação de escrita.
8. Dados sensíveis serão incluídos por lista de campos permitidos. Observações livres, senhas, CPF completo, dados de saúde e anotações internas não poderão chegar ao relatório por padrão.
9. Cliente e processo serão entidades distintas. A plataforma exibirá separadamente clientes únicos e processos/pastas.
10. O relatório será composto por seções condicionais. Cada campo ou seção poderá estar disponível, não informado, não aplicável, pendente de validação ou restrito.
11. Regras financeiras poderão variar por parceiro, processo, tipo de receita e período de vigência. Nenhum percentual será presumido como regra global do parceiro.
12. A visão interna e a visão destinada ao parceiro serão contratos diferentes. A visão externa nunca receberá campos livres por herança.

### Revisão após a amostra multiparceiro

A análise de sete pares de arquivos confirmou 11 processos, relatórios de 1 a 5 páginas e combinações diferentes de dados jurídicos, operacionais e financeiros. Também revelou fórmulas quebradas, números salvos em cache, resíduos de templates e distinção incorreta entre clientes e processos. Antes do desenvolvimento dos indicadores, devem ser respondidas as pendências registradas em `ANALISE_VARIABILIDADE_MULTIPARCEIRO.md`.

## 2. Arquitetura-alvo de baixo custo

```text
Advbox (API oficial, somente leitura)
                │
                ▼
Sincronizador em lote + limitador de requisições
                │
                ▼
PostgreSQL no servidor existente
  ├─ dados normalizados
  ├─ vínculo parceiro ↔ carteira
  ├─ execuções e erros
  └─ versões dos relatórios
                │
                ▼
Motor de indicadores e validação
                │
                ├─────────────► Portal web autenticado
                │                    ├─ lista/pesquisa de parceiros
                ▼                    ├─ situação da sincronização
HTML/CSS versionado                  └─ abrir/baixar relatório
                │
                ▼
Chromium/Playwright → PDF versionado
                │
                ▼
Disco protegido no servidor + backup existente
```

### Stack recomendada

- Python 3.12;
- FastAPI;
- Jinja2 e HTML/CSS, com HTMX apenas se necessário;
- SQLAlchemy 2 e Alembic;
- PostgreSQL;
- `httpx` para a API do Advbox;
- Playwright/Chromium para PDF;
- `pytest`, `respx` e testes de integração;
- Docker Compose, se a hospedagem aceitar contêineres;
- agendador do próprio servidor ou um processo worker simples baseado em tabela de jobs;
- arquivos no disco do servidor na primeira versão, com uma interface de armazenamento que permita migrar para S3 compatível no futuro.

Não é necessário começar com React, Redis, Celery, Kubernetes, microserviços ou serviços SaaS pagos. Para o volume descrito, eles aumentariam custo e manutenção sem benefício comprovado.

## 3. Como executar este plano no Codex

1. Abra o diretório `C:\Users\Henrique Norman\Desktop\relatorio-parceiros` no Codex.
2. Use preferencialmente a mesma tarefa do Codex durante a construção. Se abrir outra tarefa, mande-a ler este plano, a análise técnica, o `AGENTS.md` e o status do projeto antes de alterar qualquer arquivo.
3. Cole **um prompt por vez**, na ordem abaixo.
4. Só avance quando o Codex demonstrar que os critérios de aceite da etapa foram atendidos.
5. Revise o resumo e os arquivos alterados ao final de cada etapa.
6. Não cole o token do Advbox na conversa. Antes do teste real, coloque-o localmente em `.env`, depois que o projeto já tiver `.env` no `.gitignore`, ou no gerenciador de segredos da hospedagem.
7. Não autorize o Codex a imprimir o token, cabeçalhos de autorização ou respostas integrais contendo dados pessoais.

Cada prompt foi escrito com objetivo, restrições, entregáveis e testes explícitos. Isso reduz decisões implícitas e torna o trabalho retomável.

## 4. Sequência e portões de decisão

| Etapa | Resultado | Portão para avançar |
|---|---|---|
| 0 | Inventário da hospedagem e do repositório | Ambiente conhecido e pendências registradas |
| 1 | Fundação técnica e documentação viva | Aplicação sobe localmente e testes básicos passam |
| 2 | Auditoria segura da API real | Autenticação, paginação e campos reais conhecidos |
| 3 | Estratégia de vínculo parceiro-carteira | Cada processo pode ser associado de modo determinístico |
| 4 | Banco e contratos de dados | Migrações e testes de integridade passam |
| 5 | Sincronização multiparceiro | Carga repetível, idempotente e retomável |
| 6 | Indicadores e visão de relatório | Totais reconciliados e ausências não viram zero |
| 7 | HTML/PDF automatizado | PDF legível, estável e sem campos proibidos |
| 8 | Portal multiparceiro | Busca, abertura e download funcionam com autenticação |
| 9 | Agendamento e processamento incremental | Só parceiros alterados são reprocessados |
| 10 | Segurança e privacidade | Testes de isolamento e vazamento passam |
| 11 | Carga completa e homologação | Todos os parceiros elegíveis têm relatório ou erro explicado |
| 12 | Implantação | Produção monitorada, com backup e rollback |

---

## PROMPT 0 — Diagnóstico do ambiente e preparação do trabalho

**Quando usar:** agora, antes de criar a aplicação.

```text
Atue como arquiteto e responsável técnico deste projeto. Trabalhe no diretório atual e comece lendo integralmente:

- ANALISE_TECNICA_AUTOMACAO_RELATORIO_PARCEIROS.md
- ANALISE_VARIABILIDADE_MULTIPARCEIRO.md
- PLANO_EXECUCAO_CODEX.md

Também confirme, sem alterar os arquivos originais, a existência destes materiais de referência:

- C:\Users\Henrique Norman\Downloads\P-017 - Cláudia Albino.pdf
- C:\Users\Henrique Norman\Downloads\Dashboard_Acompanhamento_P-017_Claudia Albino (1).xlsx

Objetivo desta etapa: auditar o repositório e transformar as informações da hospedagem em requisitos de implantação. Ainda não implemente integrações nem o portal.

Faça o seguinte:

1. Inspecione o conteúdo atual do diretório e verifique se já existe repositório Git, código ou arquivos de configuração.
2. Crie docs/INVENTARIO_HOSPEDAGEM.md com uma tabela que eu possa preencher contendo: sistema operacional, CPU/RAM/disco, suporte a Docker, acesso SSH, proxy reverso, domínio/subdomínio, HTTPS, PostgreSQL disponível, política de backup, servidor SMTP, monitoramento e responsável operacional.
3. Crie docs/REQUISITOS_E_DECISOES.md separando fatos, hipóteses, pendências e decisões.
4. Crie STATUS_DO_PROJETO.md com as etapas 0 a 12, status, evidência de conclusão, pendências e próxima ação.
5. Identifique conflitos ou dúvidas que bloqueiem apenas a próxima etapa. Não invente respostas sobre a hospedagem.
6. Não copie dados pessoais dos arquivos de referência para os documentos criados.

Entregue: arquivos criados, resumo do que já está confirmado e a lista mínima de informações da hospedagem que eu preciso fornecer. Pare ao final desta etapa. Não programe a aplicação ainda.
```

**Critério de aceite:** inventário preenchível, decisões separadas de hipóteses e próxima ação objetiva.

---

## PROMPT 1 — Fundação do projeto e regras permanentes

```text
Continue o projeto lendo PLANO_EXECUCAO_CODEX.md, ANALISE_TECNICA_AUTOMACAO_RELATORIO_PARCEIROS.md, ANALISE_VARIABILIDADE_MULTIPARCEIRO.md, STATUS_DO_PROJETO.md e os documentos em docs/. Considere as respostas já registradas sobre a hospedagem.

Objetivo: criar a fundação executável e testável da plataforma, ainda sem chamar a API real do Advbox.

Restrições:

- software sem licença paga;
- aplicação modular monolítica em Python 3.12;
- FastAPI, Jinja2, SQLAlchemy 2, Alembic, PostgreSQL, httpx, Playwright e pytest;
- sem React, Redis, Celery, microserviços ou Kubernetes nesta fase;
- segredos somente por variáveis de ambiente;
- nunca versionar .env;
- integração Advbox somente leitura;
- preserve os arquivos existentes e não altere os dois arquivos originais em Downloads.

Implemente:

1. Estrutura organizada para app web, domínio, integração Advbox, persistência, relatórios, jobs e testes.
2. pyproject.toml com dependências separadas entre produção e desenvolvimento e versões compatíveis.
3. .gitignore contendo .env, bancos locais, relatórios gerados, caches e artefatos temporários.
4. .env.example sem nenhum segredo real.
5. Configuração tipada, com falha clara quando variável obrigatória estiver ausente.
6. Endpoint /health que não exponha configurações ou segredos.
7. Dockerfile e docker-compose.yml somente se o inventário confirmar suporte a contêineres; caso contrário, documente a execução nativa.
8. README.md com instalação, execução, testes e estrutura.
9. AGENTS.md com as regras permanentes do projeto: privacidade, API somente leitura, redaction por allowlist, não imprimir segredos, testar antes de concluir, atualizar STATUS_DO_PROJETO.md e documentar decisões relevantes.
10. Pelo menos um teste automatizado do carregamento de configuração e um do /health.

Execute instalação/checagens permitidas, lint e testes. Se algo não puder ser executado, registre exatamente a causa e não alegue que passou. Atualize STATUS_DO_PROJETO.md e pare.
```

**Critério de aceite:** aplicação sobe, `/health` responde, testes passam e nenhum segredo foi criado ou versionado.

---

## PROMPT 2 — Auditoria segura da API real do Advbox

**Preparação manual anterior:** confirme que `.env` está ignorado e coloque o token em `ADVBOX_API_TOKEN` sem enviá-lo pela conversa. Use a URL-base confirmada na documentação oficial ou na tela da conta; não a invente.

```text
Leia AGENTS.md, PLANO_EXECUCAO_CODEX.md, STATUS_DO_PROJETO.md, a seção sobre a API em ANALISE_TECNICA_AUTOMACAO_RELATORIO_PARCEIROS.md e as decisões de dados flexíveis em ANALISE_VARIABILIDADE_MULTIPARCEIRO.md.

Objetivo: descobrir o contrato real da API disponível para esta conta e, sobretudo, se existe um vínculo utilizável entre parceiro e clientes/processos. Esta é uma investigação de leitura; não crie, altere ou exclua nada no Advbox.

Regras de segurança:

- não leia nem mostre o conteúdo do arquivo .env;
- nunca imprima token, cabeçalho Authorization, CPF, e-mail, telefone, nomes completos, observações livres ou documentos;
- não salve respostas brutas da produção;
- gere somente inventário sanitizado de nomes de campos, tipos, paginação, códigos HTTP e contagens;
- use no máximo 20 requisições GET por minuto até confirmar o limite aplicável;
- implemente timeout, retry exponencial com jitter e tratamento explícito de 401, 403, 404, 429 e 5xx;
- interrompa imediatamente se houver indicação de endpoint mutável ou método diferente de GET.

Implemente um comando de auditoria separado da sincronização de produção que:

1. valide a autenticação sem revelar dados;
2. consulte amostras mínimas dos recursos oficialmente disponíveis para contatos/clientes, processos, movimentações/histórico, transações e configurações;
3. detecte e documente paginação, identificadores estáveis, datas de criação/atualização, relacionamentos e campos nulos;
4. procure campos relacionados a parceiro, origem, indicação, responsável, tags, pasta ou carteira sem assumir nomes;
5. informe se a API retorna a coleção completa e como percorrê-la;
6. produza docs/ADVBOX_API_AUDIT.md e docs/VINCULO_PARCEIRO_CARTEIRA.md sem dados pessoais;
7. crie testes usando respostas artificiais/sanitizadas; não transforme dados reais em fixtures.

Ao executar contra a API real, mostre apenas código HTTP, duração, quantidade de itens e esquema sanitizado. Ao final, classifique o vínculo parceiro-carteira como CONFIRMADO, AUSENTE ou INCONCLUSIVO e cite a evidência técnica. Atualize STATUS_DO_PROJETO.md e pare. Não comece o banco nem o portal.
```

**Portão crítico:** não avançar sem saber como associar cada processo a um parceiro.

---

## PROMPT 3 — Resolver o vínculo parceiro ↔ carteira

```text
Leia integralmente docs/ADVBOX_API_AUDIT.md e docs/VINCULO_PARCEIRO_CARTEIRA.md, além de AGENTS.md e STATUS_DO_PROJETO.md.

Objetivo: definir e provar uma regra determinística de associação entre parceiro e processos/clientes para toda a carteira, não apenas para P-017.

Siga esta ordem:

1. Se a API expuser um partner_id ou relacionamento oficial equivalente, use identificadores estáveis e documente o contrato.
2. Se o relacionamento estiver em tags, pasta, origem, indicação ou outro campo, prove unicidade, cobertura e estabilidade com contagens sanitizadas.
3. Se a API não expuser a relação, projete uma tabela de mapeamento administrável: partner_external_id, partner_name, advbox_entity_type, advbox_entity_id, valid_from, valid_to, source, status e audit fields. Implemente importação por CSV validado e uma tela administrativa simples somente numa fase posterior.
4. Não use nome de pessoa como chave técnica única.
5. Não infira o parceiro por texto livre sem uma regra aprovada e testes de conflito.

Crie docs/ADR/ADR-001-vinculo-parceiro-carteira.md com alternativas, decisão, consequências e plano de correção de exceções. Crie um validador que produza apenas contagens: vinculados, sem vínculo, múltiplos vínculos e referências inexistentes.

Teste a regra em uma amostra representativa e depois em toda a listagem disponível, sem registrar dados pessoais nos logs. O critério mínimo é: nenhuma associação ambígua; itens sem vínculo podem existir somente se forem explicitamente reportados para correção. Atualize STATUS_DO_PROJETO.md e pare.
```

**Critério de aceite:** 100% dos registros ficam vinculados uma única vez ou classificados explicitamente como “sem vínculo”; nenhum vínculo ambíguo é aceito.

---

## PROMPT 4 — Modelo de dados, migrations e contratos

```text
Leia os documentos do projeto, especialmente a auditoria da API e o ADR do vínculo parceiro-carteira.

Objetivo: implementar o banco relacional e os contratos internos que desacoplem o relatório do formato bruto da API.

Modele, no mínimo, entidades equivalentes a:

- partners;
- customers/contacts;
- lawsuits/cases;
- partner_case_links;
- movements;
- transactions, somente se confirmadas e autorizadas;
- sync_runs e sync_errors;
- report_versions;
- data_availability/section_status;
- partner_financial_agreements, com processo, tipo de receita, percentual, vigência, deduções e regra de arredondamento;
- users/roles apenas com os campos indispensáveis;
- audit_events.

Requisitos:

- usar IDs internos e guardar IDs externos do Advbox com restrições de unicidade;
- datas com timezone;
- valores monetários em Decimal, nunca float;
- separação entre dado ausente, zero e não aplicável;
- identificadores processuais opcionais, sem usá-los como chave única;
- soft-delete/status quando necessário para refletir remoções sem perder auditoria;
- chaves, índices e constraints para evitar duplicidade;
- payload bruto somente se estritamente necessário, criptografado/protegido e com política de retenção documentada; prefira campos normalizados;
- migrations Alembic reversíveis;
- modelos Pydantic para contratos entre ingestão, domínio e relatório;
- factory/fixtures exclusivamente sintéticas.

Crie docs/MODELO_DE_DADOS.md com diagrama Mermaid, dicionário de dados, classificação de sensibilidade e retenção. Implemente migrations e testes de integridade, unicidade, idempotência e valores monetários. Execute os testes, atualize STATUS_DO_PROJETO.md e pare.
```

---

## PROMPT 5 — Conector e sincronização multiparceiro

```text
Continue a partir do modelo de dados aprovado.

Objetivo: sincronizar a carteira completa de forma eficiente, idempotente, retomável e respeitando os limites da API. Não faça uma varredura completa separada para cada parceiro.

Implemente:

1. AdvboxClient isolado, somente com métodos GET confirmados na auditoria.
2. Paginação completa e limitador global conservador de requisições.
3. Timeouts, retry exponencial com jitter e respeito a Retry-After.
4. Carga inicial por recurso: buscar cada coleção uma vez, fazer upsert e associar localmente aos parceiros.
5. Checkpoint por recurso/página para retomar execução interrompida.
6. Sincronização incremental baseada em campo confirmado de atualização ou estratégia de janela temporal; se a API não oferecer isso, documente e implemente reconciliação paginada segura.
7. Hash dos dados relevantes ao relatório para identificar parceiros alterados.
8. Registro de sync_runs com início, fim, contagens, falhas e status, sem payload sensível.
9. Dead-letter/reprocessamento simples para páginas ou registros que falharem.
10. Comandos CLI para dry-run, carga inicial, incremental e reprocessamento.

Não gere relatórios ainda. Use testes com API falsa cobrindo múltiplas páginas, 429, timeout, resposta inválida, repetição da mesma carga e retomada após falha. Depois faça uma execução real controlada e apresente somente contagens agregadas. Atualize docs/OPERACAO_SINCRONIZACAO.md e STATUS_DO_PROJETO.md. Pare.
```

**Critério de aceite:** rodar duas vezes não duplica registros; uma falha intermediária pode ser retomada; todas as páginas são percorridas respeitando o limite.

---

## PROMPT 6 — Regras de indicadores e visão canônica do relatório

```text
Leia a análise dos arquivos atuais e o modelo de dados implementado.

Objetivo: criar visões canônicas, testáveis e multiparceiro que alimentem tanto o HTML quanto o PDF, com contratos separados para uso interno e para o parceiro.

Antes de codificar, crie docs/DICIONARIO_INDICADORES.md. Para cada indicador, registre: nome, finalidade, fonte, fórmula, período, inclusão/exclusão, tratamento de nulos, exemplo sintético e situação CONFIRMADO/PENDENTE.

Implemente uma camada de domínio que produza um ReportViewModel tipado com:

- identificação segura do parceiro;
- data/hora da atualização e período coberto;
- resumo executivo;
- clientes únicos e processos/pastas como indicadores separados;
- total de processos por fase/status/área quando confirmado;
- clientes e processos associados;
- último andamento relevante e data;
- alertas de dados desatualizados ou incompletos;
- resumo financeiro apenas se fonte e regra de rateio estiverem aprovadas;
- metadados de versão e origem.

Cada campo ou seção deve informar `available`, `not_provided`, `not_applicable`, `pending_validation` ou `restricted`, além de fonte e data de validação quando aplicável.

Regras obrigatórias:

- não transformar ausência de dado financeiro em R$ 0,00;
- não usar texto generativo/IA para decidir status jurídico;
- status executivo deve ser derivado de regra determinística e versionada ou ficar como pendente de revisão;
- os KPIs Benefícios concedidos, Em financeiro e Em judicial podem se sobrepor; não trate a soma como total da carteira;
- observações livres ficam fora do modelo por padrão;
- números do PDF e da planilha antigos são referência de reconciliação, não fonte de produção.

Crie testes de unidade para todas as fórmulas, limites e casos nulos. Reconcile P-017 e pelo menos mais dois cenários sintéticos diferentes, mas mantenha a implementação genérica para todos os parceiros. Liste divergências sem forçar igualdade. Atualize STATUS_DO_PROJETO.md e pare.
```

**Portão:** cada número exibido deve ter uma fórmula, uma fonte e um teste.

---

## PROMPT 7 — Relatório HTML e PDF automatizado

```text
Continue a partir do ReportViewModel aprovado.

Objetivo: criar um relatório profissional em HTML responsivo e gerar uma versão PDF estável, sem copiar visualmente o PDF atual.

Estruture o relatório com:

1. cabeçalho: parceiro, período, data da atualização e versão;
2. resumo executivo e alertas de qualidade;
3. cartões de indicadores;
4. distribuição por status/fase/área quando sustentada pelos dados;
5. tabela de processos com identificação suficiente, mas sem excesso de dados pessoais;
6. último andamento por processo e opção de detalhes no HTML;
7. seção financeira somente quando habilitada e validada;
8. metodologia, fontes e aviso de data de corte;
9. rodapé com identificação da versão do relatório.

Monte as seções por componentes condicionais. Não deixe quadros vazios e não mostre zero quando o estado for ausência, restrição, pendência ou não aplicabilidade.

Implemente templates Jinja2, CSS próprio para tela e impressão, e geração de PDF com Playwright/Chromium. O mesmo ReportViewModel deve alimentar HTML e PDF.

Requisitos de privacidade:

- aplique allowlist explícita na conversão de `InternalReportViewModel` para `PartnerReportViewModel`, antes do template;
- bloqueie CPF completo, senhas, tokens, dados de saúde, observações internas e campos não classificados;
- acrescente teste automático com padrões de segredo e documentos brasileiros em fixtures sintéticas;
- escape texto para impedir HTML/script injetado por dados do Advbox.

Requisitos de qualidade:

- A4, margens consistentes, repetição de cabeçalho de tabela quando útil e ausência de cortes ilegíveis;
- gráficos apenas quando houver informação suficiente; use SVG/CSS local, sem CDN;
- fontes locais ou do sistema, sem dependência de internet;
- testes de renderização e geração de PDF;
- gere amostras sintéticas com 0, 1 e muitos processos e faça inspeção visual das páginas renderizadas.

Documente o layout em docs/RELATORIO.md, registre limitações e atualize STATUS_DO_PROJETO.md. Pare.
```

---

## PROMPT 8 — Portal web multiparceiro

```text
Objetivo: criar o portal interno em que um usuário autorizado encontra qualquer parceiro e abre ou baixa seu relatório.

Implemente com FastAPI + Jinja2 e JavaScript mínimo:

- login seguro;
- lista paginada de parceiros;
- busca por nome/código e filtros de situação;
- data da última sincronização;
- situação do relatório: atualizado, desatualizado, gerando ou com erro;
- botão para visualizar HTML;
- botão para baixar PDF;
- ação administrativa para regenerar apenas um relatório sem refazer toda a extração;
- página de detalhe com resumo e histórico de versões;
- páginas de erro sem stack trace ou detalhes internos.

O clique no parceiro não deve chamar o Advbox em tempo real. Deve ler os dados persistidos e servir a versão vigente. Se não existir versão, crie um job e mostre o estado de processamento.

Use sessão segura, hash de senha com algoritmo moderno, proteção CSRF onde aplicável, cookie HttpOnly/Secure/SameSite e rate limit no login. Se a hospedagem já possuir SSO ou proxy de autenticação, implemente um adaptador e documente a decisão antes de criar autenticação própria.

Inclua testes de rotas, autenticação, paginação, busca, autorização e estados sem relatório. Use somente dados sintéticos. Faça uma inspeção visual das telas e corrija problemas de responsividade e acessibilidade. Atualize README, docs/PORTAL.md e STATUS_DO_PROJETO.md. Pare.
```

**Critério de aceite:** usuário interno autorizado consegue localizar parceiros diferentes e abrir seus relatórios sem acessar o Advbox diretamente.

---

## PROMPT 9 — Jobs, agendamento e atualização incremental

```text
Objetivo: retirar o acionamento manual da rotina, sem adicionar Redis ou um serviço pago.

Implemente um mecanismo simples e robusto de jobs persistidos no PostgreSQL ou use o agendador nativo do servidor conforme o inventário. O fluxo automático deve ser:

1. iniciar sync_run;
2. sincronizar recursos do Advbox em lote;
3. validar e associar dados;
4. calcular quais parceiros mudaram pelo hash relevante;
5. recalcular somente esses parceiros;
6. gerar nova versão HTML/PDF;
7. publicar a versão apenas após geração completa e validação;
8. manter a versão anterior se a nova falhar;
9. registrar métricas e erros sanitizados;
10. permitir reprocessar apenas falhas.

Garanta exclusão mútua para impedir duas cargas simultâneas, timeout por job, heartbeat, retry limitado e detecção de job abandonado. Crie comandos operacionais para executar agora, consultar situação e reprocessar falhas.

Não envie e-mails nesta fase a menos que o inventário confirme SMTP já contratado e o escritório tenha aprovado destinatários e conteúdo. Teste concorrência, falha durante PDF, retomada e publicação atômica. Crie docs/RUNBOOK.md e atualize STATUS_DO_PROJETO.md. Pare.
```

---

## PROMPT 10 — Segurança, LGPD e isolamento

```text
Faça uma revisão de segurança focada em dados jurídicos e pessoais. Não implemente funcionalidades novas fora das correções encontradas.

Produza docs/MODELO_DE_AMEACAS.md cobrindo: token do Advbox, banco, PDFs, autenticação, logs, backup, acesso administrativo, URLs compartilháveis, dados entre parceiros e incidente de vazamento.

Implemente e teste:

- papéis mínimos: administrador e leitor interno;
- deny-by-default em rotas e arquivos;
- autorização no servidor, nunca apenas ocultação na interface;
- IDs não sequenciais ou identificadores opacos nas URLs públicas;
- PDFs fora da pasta pública do servidor;
- download autenticado ou URL assinada curta somente se necessário;
- cabeçalhos de segurança;
- validação de upload, caso o mapeamento CSV exista;
- logs estruturados com redaction;
- rotação e procedimento de revogação do token;
- política de retenção e exclusão;
- trilha de auditoria para login, visualização, download, geração e alteração de vínculo;
- dependências auditadas e imagens de contêiner sem usuário root, se aplicável.

Crie testes provando que um usuário sem permissão não baixa relatório, que path traversal falha, que dados proibidos não aparecem no HTML/PDF/log e que erros não revelam segredo. Se acesso externo por parceiro ainda não estiver no escopo aprovado, não o implemente; registre os requisitos adicionais. Atualize o runbook e STATUS_DO_PROJETO.md. Pare.
```

---

## PROMPT 11 — Carga de todos os parceiros e homologação

```text
Objetivo: comprovar o produto em escala real. Esta etapa não é um piloto de um único parceiro.

Execute primeiro em dry-run e depois, com minha autorização explícita, faça a carga somente leitura de todos os registros elegíveis disponíveis na API e do mapeamento aprovado.

Produza um relatório de qualidade apenas com identificadores internos/códigos e contagens:

- total de parceiros;
- parceiros com e sem processos;
- processos vinculados, sem vínculo e com conflito;
- registros rejeitados por validação;
- relatórios gerados, sem dados, desatualizados ou com erro;
- duração, número de requisições e ocorrências de 429/5xx;
- dados financeiros disponíveis, ausentes ou sem regra aprovada;
- idade do último andamento por faixas.

Gere relatórios para todos os parceiros elegíveis, não apenas P-017. Use os cenários registrados em ANALISE_VARIABILIDADE_MULTIPARCEIRO.md: processo sem financeiro, histórico longo, vários processos para o mesmo cliente, carteira com financeiro parcial, financeiro parcelado, número/valor ausente, dado financeiro órfão, indicadores sobrepostos e campo livre sensível. Não exponha nomes ou dados pessoais no resumo de execução.

Corrija bugs de generalização encontrados. Não silencie divergências e não force registros incompletos a parecerem válidos. Registre cada exceção e seu tratamento em docs/HOMOLOGACAO.md. Execute toda a suíte de testes e atualize STATUS_DO_PROJETO.md. Pare antes de implantar em produção.
```

**Critério de aceite:** todo parceiro elegível possui relatório válido ou um erro identificável e reprocessável; nenhuma falha fica silenciosa.

---

## PROMPT 12 — Implantação na hospedagem existente

```text
Leia docs/INVENTARIO_HOSPEDAGEM.md e não presuma Docker, PostgreSQL, proxy, SMTP ou backup quando não estiverem confirmados.

Objetivo: preparar e executar uma implantação reproduzível, segura e reversível na hospedagem já disponível.

Crie um plano de mudança antes de executar qualquer ação remota. Inclua:

- pré-requisitos e portas;
- variáveis/segredos necessários sem valores;
- banco, usuário de serviço e permissões mínimas;
- migrations;
- instalação do Chromium para PDF;
- serviço da aplicação e worker/agendamento;
- proxy reverso e HTTPS;
- diretórios de relatórios sem acesso público direto;
- backup do banco e PDFs, com teste de restauração;
- healthcheck e coleta de logs;
- implantação com indisponibilidade mínima;
- rollback de aplicação e banco;
- responsáveis e janela de mudança.

Implemente scripts/configurações idempotentes compatíveis com o ambiente confirmado. Não grave segredo em Git nem em imagem. Faça primeiro uma implantação de homologação, smoke tests e geração de um relatório sintético. Só implante produção após minha autorização explícita.

Após a autorização, implante, rode migrations, faça smoke tests autenticados, valide PDF, agendamento, backup, permissões de arquivos e ausência de segredos em logs. Crie docs/IMPLANTACAO.md, registre versões implantadas e atualize STATUS_DO_PROJETO.md. Pare.
```

---

## PROMPT 13 — Go-live e operação assistida

```text
Objetivo: concluir o go-live com evidências e entregar a operação ao escritório.

Durante dois ciclos completos de sincronização:

1. monitore duração, requisições, erros, itens sem vínculo, parceiros alterados e PDFs gerados;
2. verifique se falhas são reprocessadas sem duplicação;
3. confirme que a versão anterior permanece disponível quando uma nova geração falha;
4. faça amostragem humana dos dados e do layout;
5. teste restauração de backup em ambiente separado;
6. teste revogação/rotação de token sem revelar o valor;
7. valide acesso e download com cada papel;
8. execute a suíte completa de testes e a verificação de dependências;
9. registre limitações conhecidas e backlog priorizado;
10. produza um manual curto para operação não técnica.

Crie docs/ACEITE_PRODUCAO.md com evidências, responsáveis e decisão de aceite. Crie docs/MANUAL_OPERACIONAL.md com: consultar parceiros, interpretar status, regenerar relatório, reprocessar falha, verificar sincronização, trocar token e escalar incidente.

Não declare o projeto concluído se houver falha silenciosa, vínculo ambíguo, dado proibido no relatório, backup não testado ou controle de acesso quebrado. Atualize STATUS_DO_PROJETO.md e apresente o backlog da versão 2.
```

## 5. Escopo da primeira versão multiparceiro

### Entra

- todos os parceiros que possuam vínculo determinístico com a carteira;
- carga inicial e atualização agendada;
- processos/clientes, fases, áreas e últimos andamentos confirmados pela API;
- indicadores com regras documentadas;
- relatório HTML e PDF;
- portal interno autenticado com lista, busca, situação e download;
- relatórios versionados;
- logs, retry, reprocessamento, auditoria e backup;
- identificação explícita de dados ausentes e parceiros com erro.

### Não entra sem nova validação

- escrita no Advbox;
- geração de texto jurídico por IA;
- envio automático ao parceiro por WhatsApp;
- portal externo com conta individual por parceiro;
- financeiro sem regra de rateio formal e fonte confirmada;
- notificações por serviço pago;
- réplica visual exata do PDF antigo;
- campos livres do Advbox sem classificação.

## 6. Plano de prazo indicativo

Os prazos abaixo são estimativas de esforço de um desenvolvedor e dependem da qualidade da API, do mapeamento dos parceiros e da hospedagem.

| Bloco | Etapas | Estimativa |
|---|---|---:|
| Preparação | 0–1 | 1–2 dias úteis |
| Prova da API e vínculo | 2–3 | 2–5 dias úteis |
| Dados e sincronização | 4–5 | 4–7 dias úteis |
| Indicadores e relatórios | 6–7 | 4–7 dias úteis |
| Portal e automação | 8–9 | 4–7 dias úteis |
| Segurança, escala e implantação | 10–13 | 5–10 dias úteis |
| **Total indicativo** | | **20–38 dias úteis** |

O principal fator de variação é o vínculo parceiro-carteira. Se ele não estiver disponível na API e não houver cadastro consistente no Advbox, será necessário limpar ou importar um mapeamento inicial.

## 7. Custos

Como a API está ativada e a hospedagem já existe, a meta realista é **zero custo recorrente adicional de software**. A stack proposta é composta por software livre e não depende de API de IA.

Ainda precisam ser confirmados como recursos já cobertos:

- capacidade de CPU/RAM para Chromium gerar PDFs;
- PostgreSQL;
- armazenamento e retenção dos PDFs;
- backup e restauração;
- domínio e certificado HTTPS;
- envio de e-mail, se for desejado futuramente;
- horas de desenvolvimento, operação e suporte.

Se algum desses itens não estiver incluído na hospedagem, ele será custo ou limitação operacional, mesmo sem taxa de licença.

## 8. Checklist antes do primeiro acesso à API

- [ ] `.env` consta no `.gitignore` antes de receber o token.
- [ ] O token não foi colado na conversa nem em documentação.
- [ ] A URL-base foi confirmada em fonte oficial ou na conta.
- [ ] A auditoria usa somente GET.
- [ ] O limite inicial é conservador: 20 GET/min.
- [ ] Logs e saídas são sanitizados.
- [ ] Não há persistência de resposta bruta real.
- [ ] Existe procedimento para revogar/rotacionar o token.
- [ ] O teste foi autorizado por alguém responsável pela conta.

## 9. Regra de ouro para as próximas decisões

Não desenvolver em torno de um único relatório. Toda função deve receber um identificador de parceiro, operar sobre contratos genéricos e ser testada com parceiros com perfis diferentes. A validação de P-017 comprova compatibilidade com o processo antigo; a carga integral comprova o produto.
