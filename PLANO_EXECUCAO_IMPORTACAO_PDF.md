# Plano de execução — importação manual de PDF do Advbox

**Data:** 23/09/2026  
**Estado:** PDF-0 e PDF-1 concluídas; ingestão privada validada somente com PDFs sintéticos em desenvolvimento/teste; PDF-2 ainda não iniciada  
**Substitui:** o caminho de atribuição automática da etapa 11 do `PLANO_EXECUCAO_CODEX.md`  
**Preserva:** fundação, API oficial GET-only, banco, relatórios, portal, worker e controles das etapas 0 a 10

## 1. Objetivo do novo fluxo

O operador continuará gerando manualmente, no módulo Parceiros do Advbox, um PDF para cada parceiro e período. A plataforma receberá esse arquivo em uma área autenticada, identificará de forma determinística quais processos pertencem à carteira, reconciliará esses processos com a API oficial do Advbox e produzirá a visão interna e o relatório formatado.

```text
Operador escolhe o parceiro e envia o PDF exportado do Advbox
                            │
                            ▼
Validação, hash, quarentena e extração estrutural do PDF
                            │
                            ▼
Manifesto da carteira: número processual e/ou pasta, sem inferência por nome
                            │
                            ▼
Reconciliação com processos da API oficial GET-only
                            │
             ┌──────────────┴──────────────┐
             ▼                             ▼
      correspondência única       pendência/ambiguidade
             │                             │
             ▼                             ▼
Dados normalizados da API           revisão humana auditada
             └──────────────┬──────────────┘
                            ▼
       allowlist, indicadores, HTML/PDF e portal versionados
```

O PDF de origem é um **documento de entrada privado** e uma prova da composição da carteira. Ele não será republicado. A API oficial continua sendo a fonte preferencial para os dados estruturados de processos, clientes, andamentos e transações. Um campo existente somente no PDF só poderá ser usado depois de ser classificado, aprovado e incluído explicitamente na allowlist.

## 2. Decisões que orientam todas as etapas

1. O usuário escolhe o parceiro no upload; o nome encontrado no PDF não cria nem troca esse vínculo.
2. A correspondência usa, nesta ordem, número processual normalizado e pasta exata quando a pasta tiver unicidade comprovada. Nome de pessoa, parte, advogado ou texto livre nunca será chave de associação.
3. Correspondência ausente ou múltipla exige revisão. Nenhum processo será associado por aproximação silenciosa.
4. O arquivo original, o texto extraído e dados pessoais não entram em logs, documentação, fixtures ou mensagens de erro.
5. A primeira versão aceita somente PDF com camada de texto. PDF escaneado é recusado com orientação clara; OCR fica fora do escopo até decisão específica de privacidade e precisão.
6. Upload aceita apenas PDF real validado por assinatura, tamanho, páginas e limites definidos; extensão de arquivo não é prova suficiente.
7. O documento recebe SHA-256, versão do parser, usuário, parceiro, período, horários e estado de processamento. Reenvio idêntico é detectado.
8. O PDF fica em storage privado. O filesystem da Vercel não é armazenamento persistente. Em desenvolvimento, qualquer storage local deve recusar produção.
9. A integração Advbox permanece GET-only e usa exclusivamente endpoints oficiais já confirmados. As rotas internas sem autorização não serão implementadas.
10. A visão externa mantém allowlist estrita. Contatos, CPF/CNPJ completo, dados de saúde, credenciais, observações, textos livres e o PDF-fonte são bloqueados por padrão.
11. Publicação exige lote reconciliado, zero ambiguidade não resolvida, regras de conteúdo aprovadas e revisão registrada.
12. Dados reais não serão copiados para código, testes, documentação, logs, screenshots versionadas ou artefatos de demonstração.
13. O PDF anotado pelo escritório é evidência de requisitos, não arquivo de importação nem fixture. Destaques amarelos não participam do parser.
14. As prioridades candidatas são: parte/cliente, tipo de ação/benefício, fase, financeiro detalhado e andamento manual recente. Elas devem vir da API oficial e continuam sujeitas à matriz interna/externa, P-006/P-007/P-023 e controle de acesso.

### 2.1 Prioridades operacionais recebidas do escritório

O documento `docs/PRIORIDADES_CONTEUDO_ESCRITORIO.md` registra de forma sanitizada as categorias marcadas no PDF de 55 páginas e as perguntas ainda necessárias. A marcação confirma relevância operacional, mas não resolve fonte, fórmula, semântica ou autorização de publicação.

- parte/cliente: candidato à visão interna restrita; nome nunca é chave e segue bloqueado externamente até P-007/P-023;
- tipo de ação/benefício: usar catálogo/IDs oficiais, sem extrair o rótulo do PDF como fonte final;
- fase: tratar como fase operacional, distinta de status jurídico;
- financeiro: avaliar lançamentos estruturados, `is_internal`, regras de sinal/totalização/rateio e visibilidade por papel;
- andamento: distinguir o último cronológico do “relevante”; texto livre permanece restrito por padrão.

Se uma prioridade não tiver campo oficial confirmado, a etapa correspondente registra `content_source_gap` e para no portão de decisão. Não se usa o texto do PDF como substituto silencioso.

## 3. O que será reaproveitado

| Componente existente | Uso no novo fluxo |
|---|---|
| `AdvboxClient` e sincronização | Buscar e atualizar os dados estruturados dos processos identificados no PDF |
| PostgreSQL e modelos normalizados | Guardar lote, vínculos auditados, dados reconciliados e versões |
| `ReportViewModel` | Montar a visão canônica após reconciliação e aprovação |
| Renderização HTML/PDF | Gerar o relatório final com a paleta já aprovada |
| Portal interno | Receber upload, mostrar validação, revisão, histórico e relatório |
| Worker, lease e retentativas | Processar importações e gerações fora da requisição web |
| Autenticação, CSRF e auditoria | Restringir upload, revisão, publicação e download |

O adaptador de rotas internas do Advbox deixa de ser necessário. A fonte do vínculo parceiro–processo passa a ser o PDF exportado manualmente e aprovado pelo operador.

## 4. Sequência e portões

| Etapa | Resultado | Portão para avançar |
|---|---|---|
| PDF-0 | Contrato da importação e decisões do produto | Formato aceito, papéis das fontes e pendências documentados |
| PDF-1 | Ingestão privada e modelo do lote | Upload seguro, hash, estados e storage abstrato testados |
| PDF-2 | Parser estrutural | Manifesto extraído com fixtures sintéticas e falha segura para layout desconhecido |
| PDF-3 | Reconciliação com a API oficial | Correspondências únicas separadas de ausentes/ambíguas, sem heurística por nome |
| PDF-4 | Revisão humana no portal | Operador consegue aprovar/rejeitar/corrigir com trilha auditável |
| PDF-5 | Regras de conteúdo e minimização | Matriz interna/externa das prioridades do escritório e indicadores aprovados; texto livre bloqueado |
| PDF-6 | Relatório e versionamento ponta a ponta | Lote aprovado gera HTML/PDF e versão reproduzível |
| PDF-7 | Homologação privada com arquivos reais | Cenários reais passam sem vazamento e divergências ficam explicadas |
| PDF-8 | Infraestrutura e implantação | Banco, objetos, jobs, identidade, backups e plano Vercel adequados validados |
| PDF-9 | Go-live assistido | Primeiro ciclo produtivo aprovado, monitorado e reversível |

Execute sempre um prompt por vez. Não avance automaticamente, mesmo quando os testes passarem.

---

## PROMPT PDF-0 — Contrato da importação e decisões

**Quando usar:** agora, antes de alterar código ou banco.

```text
Atue como arquiteto e responsável técnico. Trabalhe no diretório atual e leia integralmente AGENTS.md, PLANO_EXECUCAO_IMPORTACAO_PDF.md, STATUS_DO_PROJETO.md, docs/REQUISITOS_E_DECISOES.md, docs/HOMOLOGACAO.md, docs/MODELO_DE_DADOS.md, docs/RELATORIO.md e docs/MODELO_DE_AMEACAS.md.

Objetivo: formalizar o contrato do novo fluxo em que o operador exporta manualmente um PDF do módulo Parceiros do Advbox e o envia à plataforma. Não altere código, migrations ou banco nesta etapa.

Faça o seguinte:

1. Inspecione somente a estrutura dos PDFs de referência disponíveis, sem copiar dados pessoais para documentos, logs ou testes. Registre apenas características como presença de camada de texto, quantidade de páginas, marcadores estruturais, repetição de cabeçalho e possibilidade de um bloco atravessar páginas.
2. Crie docs/CONTRATO_IMPORTACAO_PDF.md com: formato aceito, pré-condições para exportar, papéis das fontes, estados do lote, campos mínimos do manifesto, regras de correspondência, motivos de rejeição e critérios para revisão/publicação.
3. Crie docs/ADR/ADR-002-fonte-carteira-pdf.md comparando: rota interna não autorizada, CSV manual, PDF como manifesto e digitação manual. Registre a decisão pelo PDF e suas consequências.
4. Defina precedência: PDF comprova a composição da carteira; API oficial fornece dados estruturados; entradas manuais fornecem somente regras aprovadas. Não use nomes como chave.
5. Registre as decisões humanas ainda necessárias: papéis de upload/revisão/publicação, retenção do PDF-fonte, periodicidade, filtros obrigatórios na exportação, campos externos e regras dos indicadores.
6. Atualize docs/REQUISITOS_E_DECISOES.md e STATUS_DO_PROJETO.md para marcar P-005 como superada pela mudança de estratégia, sem apagar seu histórico.

Não implemente upload, parser, OCR, chamada real à API, persistência ou interface. Ao final, entregue os arquivos alterados, as decisões confirmadas, as pendências mínimas e pare.
```

**Critério de aceite:** contrato testável, fontes e precedência explícitas, nenhuma informação pessoal transcrita e próxima ação objetiva.

---

## PROMPT PDF-1 — Ingestão privada, storage e modelo do lote

```text
Leia AGENTS.md, PLANO_EXECUCAO_IMPORTACAO_PDF.md, STATUS_DO_PROJETO.md, docs/CONTRATO_IMPORTACAO_PDF.md, o ADR-002 e o modelo de ameaças.

Objetivo: implementar a recepção segura do PDF e o ciclo de vida do lote, ainda sem interpretar processos nem chamar o Advbox real.

Implemente:

1. Interface de storage privado com implementação local apenas para development/test e recusa explícita em production.
2. Modelos e migration para documento-fonte, lote de importação e eventos/revisões indispensáveis, ajustando os nomes ao schema existente. Inclua UUID, parceiro selecionado, período, SHA-256, tamanho, páginas quando conhecido, versão do parser, estado, usuário e timestamps.
3. Estados transicionais explícitos, por exemplo: uploaded, quarantined, parsing, parsed, reconciling, needs_review, approved, rejected, failed e superseded, com transições validadas.
4. Endpoint e formulário autenticados com CSRF e papel apropriado para selecionar parceiro, período e arquivo.
5. Validação por assinatura PDF, MIME, extensão, tamanho, páginas, nome seguro e duplicidade. Não confie no nome do arquivo e não preserve o nome original em logs.
6. Detecção de edição pós-exportação: rejeite destaques, comentários, texto, carimbos, anexos e formulários com `PDF_ANNOTATED_SOURCE`; links previstos pelo layout devem ser classificados separadamente. O PDF anotado do escritório é requisito privado, não entrada de teste.
7. Gravação atômica: metadado e objeto não podem ficar inconsistentes; falhas devem ser retomáveis ou limpas com segurança.
8. Auditoria allowlisted de upload, rejeição e duplicidade, sem caminho, texto extraído ou dado pessoal.
9. Testes sintéticos para arquivo válido, arquivo falso, arquivo anotado, excesso de tamanho/páginas, duplicidade, CSRF, autorização, falha de storage e produção recusada.

Não extraia texto, não implemente OCR e não chame a API. Atualize documentação, execute migrations, testes, lint e verificação de deriva. Pare ao final.
```

**Critério de aceite:** um PDF sintético pode ser recebido com segurança e auditado, sem ser interpretado nem exposto publicamente.

---

## PROMPT PDF-2 — Parser estrutural do PDF do Advbox

```text
Leia os documentos do plano PDF e o código da etapa PDF-1.

Objetivo: transformar um PDF textual do Advbox em um manifesto tipado de processos, sem copiar nem publicar o conteúdo livre do documento.

Implemente um parser isolado e versionado que:

1. confirme a existência de camada de texto e recuse imagem/scan com código de erro claro;
2. extraia texto com posição e agrupe blocos por marcadores estruturais, inclusive quando um processo atravessar páginas;
3. produza somente campos allowlisted do manifesto: número processual normalizado quando presente, pasta exata quando presente, referência técnica do item, páginas de origem e indicadores de qualidade;
4. não extraia para persistência nomes, contatos, documentos, credenciais, saúde, narrativa ou observações livres;
5. detecte cabeçalhos/rodapés repetidos, bloco incompleto, registro duplicado, zero processos, layout desconhecido e limite excedido;
6. grave somente manifesto normalizado e métricas sanitizadas. Texto integral extraído deve existir no máximo em memória durante o processamento;
7. preserve hash e versão do parser para reprodutibilidade;
8. use PDFs totalmente sintéticos como fixtures, incluindo 0, 1 e muitos processos, um caso de pelo menos 55 páginas, quebra de página, ausência de número, duplicidade e layout incompatível.
9. ignore cor e aparência como fonte semântica e recuse anotações pós-exportação antes do parse; parte/cliente, ação, fase, financeiro e andamento não entram no manifesto nem na persistência do parser.

Não use OCR, regex por nome de pessoa nem dados reais em fixtures. Faça uma inspeção controlada do PDF de referência somente para validar a estrutura; a saída exibida deve conter exclusivamente contagens, marcadores genéricos e códigos de erro. Execute testes, lint e atualização documental/status. Pare.
```

**Critério de aceite:** o mesmo arquivo e versão do parser produzem o mesmo manifesto; layouts não reconhecidos falham fechados e nenhum texto sensível é persistido ou logado.

---

## PROMPT PDF-3 — Reconciliação com a API oficial

```text
Leia AGENTS.md, o contrato da importação, a documentação da sincronização, o modelo de dados e o parser implementado.

Objetivo: reconciliar cada item do manifesto com os processos acessíveis pela API oficial GET-only do Advbox.

Implemente:

1. reconciliação por número processual normalizado exato;
2. fallback por pasta exata somente quando o número estiver ausente e a pasta tiver correspondência única comprovada;
3. resultados tipados: matched, unmatched, ambiguous, duplicate_source e invalid_identifier;
4. proibição testada de correspondência por nome, similaridade textual, cliente, parte ou responsável;
5. associação proposta ao parceiro do lote somente após correspondência única; vínculo aprovado deve guardar lote, método, evidência técnica, vigência e revisor;
6. enriquecimento pelos endpoints oficiais confirmados, respeitando paginação, 20 GET/min, retry e redaction existentes;
7. idempotência, retomada e fotografia consistente; reprocessar não pode duplicar vínculos nem versões;
8. dry-run que emite apenas contagens por resultado e não persiste dados reais sem autorização específica.
9. matriz sanitizada de cobertura da API para as cinco prioridades do escritório: parte/cliente, tipo de ação/benefício, fase, financeiro e andamento. Registre apenas nomes de campos/endpoints confirmados, disponibilidade e lacunas; não use valores do PDF e não implemente projeção nesta etapa.

Cubra com API falsa: correspondência única, ausente, múltipla, número formatado, pasta não única, mudança da origem, 429, timeout e retomada. Execute primeiro somente testes sintéticos. Se houver autorização já registrada para um dry-run real, mostre exclusivamente contagens agregadas. Atualize documentação/status e pare.
```

**Critério de aceite:** todo item fica exatamente em uma categoria; nenhum ambíguo é vinculado e nenhuma chave baseada em nome existe.

---

## PROMPT PDF-4 — Revisão humana e aprovação no portal

```text
Leia o plano PDF, contrato, modelo de ameaças, documentação do portal e resultados da reconciliação.

Objetivo: oferecer um fluxo interno auditável para conferir o lote antes de qualquer relatório.

Implemente no portal autenticado:

1. lista de importações por parceiro, período, estado, horário e contagens;
2. detalhe com itens matched, unmatched e ambiguous, sem apresentar campos livres do PDF;
3. ações de aprovar, rejeitar, substituir e solicitar reprocessamento, com CSRF, papéis e confirmação;
4. correção manual apenas por seleção de ID técnico existente e justificativa de catálogo; nunca por digitação livre de nomes;
5. separação de funções configurável: uploader não aprova o próprio lote quando a política exigir quatro olhos;
6. concorrência otimista/bloqueio para impedir duas decisões incompatíveis;
7. trilha allowlisted de ator, ação, lote, item, método, antes/depois técnicos e horário;
8. bloqueio de aprovação enquanto houver ambiguidade ou erro não resolvido.

Use somente dados e PDFs sintéticos. Teste autorização direta das rotas, CSRF, conflito concorrente, isolamento entre parceiros, substituição, reprocessamento e ausência de dados sensíveis em resposta/log/auditoria. Faça inspeção visual desktop/celular. Atualize documentação/status e pare.
```

**Critério de aceite:** um lote sintético pode percorrer upload → parse → reconciliação → revisão → aprovação com trilha completa e sem publicação antecipada.

---

## PROMPT PDF-5 — Conteúdo, indicadores e minimização

```text
Leia docs/DICIONARIO_INDICADORES.md, docs/RELATORIO.md, o contrato PDF e as decisões P-006/P-007 disponíveis.

Objetivo: decidir e implementar exatamente quais dados reconciliados alimentam a visão interna e a externa, priorizando as necessidades registradas em `docs/PRIORIDADES_CONTEUDO_ESCRITORIO.md`.

Antes de codificar, produza ou atualize uma matriz campo a campo com: fonte, finalidade, visão interna, visão externa, transformação, estado de ausência, sensibilidade, retenção e responsável pela aprovação.

Comece pelas cinco prioridades do escritório e não trate o destaque amarelo como aprovação:

1. parte/cliente: defina papel processual e se o nome fica somente na visão interna; nome nunca é chave;
2. tipo de ação/benefício: mapeie ID/catálogo oficial e rótulo aprovado;
3. fase: mantenha fase operacional separada de status jurídico;
4. financeiro por processo: avalie tipo, vencimento, pagamento, competência, categoria, identificação/parcela, valor, `is_internal` e totalização, cada qual com regra e estado;
5. andamento: defina último cronológico versus relevante, endpoint de origem, tamanho e política para texto livre.

Regras:

1. API oficial prevalece para dados estruturados; PDF fornece composição da carteira e somente campos adicionais explicitamente aprovados.
2. Texto livre do PDF ou da API é bloqueado por padrão. Contato, documento completo, saúde, credencial e observação não entram na visão externa.
3. Cliente único e processo são métricas separadas; ausência nunca vira zero.
4. Indicador ou financeiro sem fórmula, período, fonte e responsável aprovados permanece pending_validation e não aparece como valor calculado.
5. Divergência entre PDF e API gera alerta de qualidade, não substituição silenciosa.
6. O portão publication_ready exige lote aprovado, fotografia completa, nenhuma ambiguidade e matriz de conteúdo aprovada.
7. Campo prioritário sem fonte oficial confirmada fica `content_source_gap`; não copie o valor do PDF para preencher a lacuna.
8. Nome/parte e texto de andamento são restritos por padrão. Registro financeiro interno nunca alcança a visão externa por herança.

Implemente apenas regras aprovadas. Para decisões humanas ausentes, mantenha estado pendente e liste a pergunta objetiva; não invente. Cubra com testes sintéticos de privacidade, nulos, zero, divergência, carteira vazia e dados proibidos. Execute a suíte completa, atualize documentação/status e pare.
```

**Critério de aceite:** cada campo publicável tem fonte e aprovação rastreáveis; conteúdo proibido não alcança HTML nem PDF.

---

## PROMPT PDF-6 — Geração e versionamento ponta a ponta

```text
Leia o plano PDF, a matriz de conteúdo, docs/RELATORIO.md, docs/PORTAL.md e docs/RUNBOOK.md.

Objetivo: ligar um lote aprovado ao ReportViewModel, HTML, PDF final e histórico do portal, preservando reprodução e rollback.

Implemente:

1. adaptador lote aprovado + dados normalizados → InternalReportViewModel;
2. chave de revisão derivada de parceiro, período, hash do PDF-fonte, versão do parser, fotografia da API e versão das regras;
3. job idempotente que gera HTML/PDF, valida allowlist e só publica a versão quando todos os artefatos terminarem;
4. preservação da última versão válida em qualquer falha;
5. histórico que liga versão ao lote e mostra somente metadados seguros;
6. indicação clara de atualização, período, fonte e pendências sem expor o PDF original;
7. download autenticado do relatório gerado; nunca do PDF-fonte;
8. testes ponta a ponta sintéticos, regressão visual desktop/celular e inspeção de PDFs A4 de 0, 1 e muitos processos;
9. hierarquia de conteúdo que, quando aprovada, torne parte/cliente, ação, fase, financeiro e andamento localizáveis sem misturar a visão interna com a externa; teste nomes longos, muitas parcelas e andamento extenso.

Não use filesystem produtivo nem publique dados reais. Execute migrations, suíte completa, lint, verificação de deriva e inspeção visual. Atualize documentação/status e pare.
```

**Critério de aceite:** um lote sintético aprovado gera uma única versão reproduzível, privada e reversível; falha parcial não aparece ao usuário.

---

## PROMPT PDF-7 — Homologação privada com PDFs reais

**Preparação manual:** colocar os arquivos autorizados somente em `storage/private`, confirmar que a pasta está ignorada e registrar quem autorizou o teste. Não anexar PDFs reais a issues, commits ou mensagens.

```text
Leia AGENTS.md, o plano PDF, o contrato, a matriz de conteúdo, o modelo de ameaças e o status.

Objetivo: homologar o fluxo com PDFs reais autorizados sem publicar relatório nem persistir mais dados do que o necessário antes da aprovação.

Faça em duas passagens:

1. dry-run estrutural: hash, páginas, versão do parser e contagens de manifestos/matched/unmatched/ambiguous, sem nomes, números, textos ou payloads na saída;
2. somente após autorização explícita baseada no dry-run, processamento privado persistente e geração de prévia interna para revisão.

Cubra, conforme arquivos autorizados disponíveis: parceiros diferentes, carteira vazia/pequena/grande, processo sem número, bloco entre páginas, reenvio idêntico, PDF substituto, item ausente na API e mudança de layout. Compare contagens e estrutura com a exportação original em ambiente privado. Não transforme dados reais em fixtures.

Inclua uma rodada de homologação com usuários do escritório para as cinco prioridades, registrando somente resultado agregado: fonte encontrada, semântica aprovada/reprovada, visibilidade interna/externa e motivo de bloqueio. Confirme especificamente registros financeiros internos e diferença entre último andamento cronológico e andamento relevante. O PDF anotado não é arquivo de ingestão; use uma exportação original autorizada no fluxo.

Produza docs/HOMOLOGACAO_IMPORTACAO_PDF.md apenas com métricas agregadas, códigos de exceção, resultado dos critérios e aprovações; nenhum dado pessoal. Execute testes, lint e verificações de segurança. Não publique, não envie e não faça deploy. Atualize status e pare no portão GO/NO-GO.
```

**Critério de aceite:** todos os itens dos arquivos homologados ficam reconciliados ou explicitamente pendentes, sem associação ambígua, vazamento ou dado real em artefato versionado.

---

## PROMPT PDF-8 — Infraestrutura produtiva e implantação

```text
Leia o inventário de hospedagem, plano PDF, status, runbook, modelo de ameaças e homologação. Consulte documentação oficial atual dos provedores antes de qualquer decisão que possa ter mudado.

Objetivo: implantar o fluxo homologado em infraestrutura profissional, privada e recuperável.

Portões obrigatórios antes do deploy:

- Vercel Pro ou plano contratualmente adequado ao uso empresarial;
- PostgreSQL externo com SSL, pool, extensão necessária, backup e restauração testada;
- storage privado de objetos para fontes e relatórios, com buckets/prefixos e permissões separados;
- executor de jobs compatível com duração, concorrência e retentativas;
- segredos em cofre/variáveis protegidas;
- identidade, papéis, MFA/SSO ou decisão formal equivalente;
- retenção do PDF-fonte, relatórios, auditoria e backups aprovada;
- logs, alertas, domínio e responsável operacional definidos.

Implemente adaptadores produtivos e configuração sem segredos no repositório. Valide upload, download autorizado, isolamento de parceiro, migração, job, rollback, expiração/remoção conforme política e restauração em ambiente separado. Faça primeiro staging com dados sintéticos; depois use dados reais somente com autorização específica. Configure domínio apenas após o staging aprovado. Atualize documentação/status e pare antes do go-live.
```

**Critério de aceite:** staging funciona sem filesystem persistente da Vercel, backups/restauração e isolamento são comprovados e não há bloqueio contratual conhecido.

---

## PROMPT PDF-9 — Go-live assistido e aceite

```text
Leia toda a documentação operacional e o relatório de homologação. Confirme que o portão da etapa PDF-8 está aprovado.

Objetivo: realizar o primeiro ciclo produtivo de forma assistida, observável e reversível.

Execute com um conjunto pequeno aprovado:

1. upload por operador autorizado;
2. processamento e reconciliação monitorados;
3. revisão por pessoa autorizada diferente quando exigido;
4. geração e conferência privada do relatório;
5. publicação interna controlada;
6. confirmação de auditoria, métricas, alertas, backup e possibilidade de retirada/rollback;
7. registro de tempos, erros, decisões e aceite sem dados pessoais;
8. atualização do runbook com procedimento rotineiro: exportar, enviar, revisar, publicar, substituir, revogar e eliminar conforme retenção.

Não amplie para toda a carteira enquanto o primeiro ciclo não for aceito. Em qualquer divergência de vínculo, privacidade ou isolamento, retire a versão, preserve evidência mínima, corrija e repita a homologação afetada. Entregue o termo técnico de aceite, pendências residuais, responsáveis e rotina operacional. Pare.
```

**Critério de aceite:** primeiro relatório produtivo aprovado por negócio e operação, sem incidente, com rollback, auditoria e responsabilidades comprovados.

## 5. Decisões humanas mínimas e momento em que bloqueiam

| Decisão | Pode esperar até | Opção técnica segura enquanto pendente |
|---|---|---|
| Quem pode enviar, revisar e publicar | PDF-4 | Somente administrador local; sem publicação |
| Retenção do PDF-fonte | PDF-7 | Não usar produção; conservar apenas os arquivos privados já autorizados |
| Periodicidade e filtros da exportação | PDF-7 | Importação manual sem promessa de atualização automática |
| Campos da visão externa | PDF-5 | Visão externa não publicável |
| Fórmulas e regras financeiras | PDF-5 | `pending_validation`; omitir valores |
| Semântica e visibilidade das cinco prioridades do escritório (P-023) | PDF-5 | Campos `restricted`/`pending_validation`; nenhuma publicação |
| Tratamento de item sem número e pasta não única | PDF-3 | `needs_review`; nunca associar automaticamente |
| Plano Vercel, banco, storage e jobs | PDF-8 | Operação exclusivamente local e sintética |

## 6. Definição de sucesso do projeto revisado

O produto estará pronto quando um operador conseguir exportar um PDF de parceiro no Advbox, enviá-lo de forma privada, revisar somente as exceções, gerar o relatório com dados reconciliados da API oficial e disponibilizá-lo no portal com controle de acesso, versionamento e auditoria. A etapa manual de exportação será explícita; do upload em diante, o processo será automatizado e retomável.
