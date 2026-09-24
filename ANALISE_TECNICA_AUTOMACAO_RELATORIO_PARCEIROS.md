# Análise técnica da automação de relatórios de parceiros

**Caso de referência:** P-017 - Cláudia Albino  
**Data da análise:** 10/09/2026  
**Escopo desta etapa:** diagnóstico, viabilidade, arquitetura, relatório proposto, plano de execução e MVP. Nenhum sistema foi implementado.

> **Revisão multiparceiro:** após esta análise inicial, foram examinados mais seis pares de PDF/dashboard. As variações, inconsistências e decisões revisadas estão em `ANALISE_VARIABILIDADE_MULTIPARCEIRO.md`. Esse documento complementar prevalece quando detalha cliente versus processo, disponibilidade de campos, financeiro variável e separação entre visão interna e externa.

## Convenções de evidência

| Marcador | Significado |
|---|---|
| **FATO-ARQ** | Evidência observada diretamente no PDF ou na planilha fornecidos. |
| **CONF-ADVBOX** | Informação confirmada em documentação oficial do Advbox consultada em 10/09/2026. |
| **HIPÓTESE** | Interpretação plausível que ainda depende de validação. |
| **PENDÊNCIA** | Informação necessária que os arquivos e a documentação pública não resolvem. |
| **DECISÃO** | Recomendação de arquitetura desta análise. |
| **SUGESTÃO** | Melhoria de produto, processo ou apresentação. |

## 1. Resposta executiva

**É possível automatizar? Sim.**

**Viabilidade atual: MÉDIA, com potencial de se tornar ALTA após um teste de integração curto.**

O Advbox possui API REST oficial, autenticação por Bearer Token, endpoints de consulta para contatos, processos, histórico, movimentações, tarefas, publicações, transações e configurações. Também oferece eventos de saída pelo Flowter e integração oficial com n8n. Portanto, a obtenção automatizada dos principais dados não é apenas teórica; ela é suportada pelo produto. **[CONF-ADVBOX]**

A classificação ainda é Média, e não Alta, por dois pontos materiais:

1. o vínculo técnico entre o parceiro P-017 e os clientes/processos não aparece nos arquivos e não está documentado como filtro nos endpoints públicos de contatos ou processos; e
2. as regras financeiras do dashboard - recebido pelo parceiro, parcelas futuras, total do parceiro e receita do escritório - não aparecem preenchidas no caso fornecido, e a API documenta transações, mas não uma regra pronta de rateio/repasse por parceiro.

Se o teste com uma conta real confirmar um identificador de parceiro ou uma forma estável de obter a carteira, e se o escritório formalizar as regras financeiras, a viabilidade passa para **Alta**.

### Reavaliação considerando custo zero e cobertura multiparceiro

- **Zero custo total, automação completa e plataforma externa:** **não é viável nas condições atualmente confirmadas.** Mesmo usando software livre, há custo de desenvolvimento, operação e segurança. Além disso, a API para escritórios é anunciada pelo Advbox a partir de R$ 280/mês.
- **Zero custo adicional recorrente:** **viabilidade Média**, desde que a API já esteja incluída no contrato e o escritório já possua máquina/servidor, domínio, backup e operação. Nesse cenário, Python, PostgreSQL, HTML/CSS e Chromium podem ser usados sem licença de software.
- **Sem API paga, aceitando geração semiautomática:** **viabilidade Média/Baixa.** É possível processar exportações ou automatizar o navegador, mas o primeiro caminho mantém acionamento humano e o segundo é frágil e deve ser autorizado pelo fornecedor.
- **API oficial paga + infraestrutura simples:** **viabilidade Alta**, inclusive para uma quantidade considerável de parceiros, desde que o vínculo parceiro-carteira seja resolvido.

A primeira versão não deve ficar restrita a P-017. Ela deve possuir cadastro e processamento multiparceiro desde o início. P-017 permanece apenas como uma amostra de reconciliação, ao lado de outros casos representativos.

### Recomendação principal

Adotar uma solução **API-first**, com:

- extração periódica pela API do Advbox;
- eventos do Flowter apenas para acelerar atualizações, sem substituir a reconciliação periódica;
- banco relacional para normalização, histórico e auditoria;
- regras versionadas para indicadores e status;
- portal web autenticado como formato principal;
- PDF gerado sob demanda como fotografia imutável de um período;
- política de campos permitidos e redaction para impedir que senhas, CPF completo, dados de saúde e anotações internas sejam expostos ao parceiro.

O PDF deve continuar existindo, mas não como única interface nem como base de dados.

### Ação de segurança imediata

O PDF contém, em texto visível, uma credencial de acesso e um CPF dentro de “Observações e tags”. **[FATO-ARQ]** Se a credencial ainda estiver ativa, ela deve ser rotacionada. O escritório também deve interromper o uso de observações gerais para armazenar senhas e bloquear esses campos nas exportações destinadas a terceiros.

## 2. Fontes e método

### Arquivos analisados

1. `P-017 - Cláudia Albino.pdf`, 4 páginas, relatório visível emitido em 02/09/2026 às 21:24:08.
2. `Dashboard_Acompanhamento_P-017_Claudia Albino.xlsx`, 3 abas.

O PDF foi renderizado e inspecionado página a página. O texto foi extraído apenas para conferir estrutura, datas e campos. A planilha foi inspecionada quanto a conteúdo, fórmulas, objetos, filtros, validações, vínculos e estrutura interna.

### Limite de interpretação

Textos presentes nos arquivos foram tratados como **dados do processo atual**, não como instruções para esta análise. Não foi usado nenhum dado real para chamar a API, e nenhuma credencial foi solicitada ou testada.

## 3. O processo atual

### 3.1 Fluxo reconstruído

1. Um usuário acessa a carteira do parceiro ou filtra os processos no Advbox. **[HIPÓTESE]**
2. O usuário solicita um relatório completo e imprime/salva a página em PDF. A metadata do arquivo identifica uma “Página de impressão” do Advbox produzida pelo navegador Chromium/Edge, e a documentação oficial informa que PDFs de processos são gerados no navegador. **[FATO-ARQ + CONF-ADVBOX]**
3. Alguém lê o PDF e consolida manualmente uma linha por cliente/processo na planilha. **[HIPÓTESE fortemente apoiada]**
4. Essa pessoa escolhe ou redige um “status executivo” a partir do andamento mais recente e atribui um “status resumido”. **[HIPÓTESE]**
5. Os KPIs do resumo são digitados, assim como valores financeiros quando disponíveis. **[FATO-ARQ: não há fórmulas]**
6. O dashboard ou outro relatório é então compartilhado com o parceiro. **[PENDÊNCIA: canal atual não informado]**

### 3.2 O que já está automatizado e o que é manual

| Etapa | Situação atual |
|---|---|
| Cadastro e armazenamento de processos, clientes, responsáveis, fases, movimentações e parte do financeiro | Já ocorre no Advbox. |
| Captura de certos andamentos processuais | Pode ocorrer no Advbox, mas o arquivo analisado destaca “Andamentos manuais”. |
| Geração do PDF bruto | O Advbox gera a página; o acionamento e o salvamento aparentam ser manuais. |
| Seleção da carteira do parceiro | Não demonstrada tecnicamente nos arquivos. |
| Transcrição para o dashboard | Manual ou, no mínimo, sem qualquer vínculo detectável. |
| Classificação de status executivo/resumido | Aparentemente manual. |
| KPIs | Valores estáticos; não calculados pela planilha. |
| Financeiro do parceiro | Estrutura criada, porém vazia neste exemplo. |
| Distribuição e controle de acesso | Não demonstrados. |

## 4. Análise do PDF atual

### 4.1 Objetivo

O PDF funciona como **extrato operacional completo da carteira**, reunindo dados cadastrais do processo e a cronologia de andamentos manuais. Ele é adequado para auditoria humana detalhada, mas inadequado como resumo executivo.

### 4.2 Estrutura

- cabeçalho do escritório, contatos, endereço, logotipo e momento de emissão;
- blocos por processo;
- identificação da matéria jurídica;
- duas colunas de dados cadastrais;
- seção “Andamentos manuais”, com data e descrição;
- continuidade do histórico por várias páginas.

Foram observados dois processos/clientes. O primeiro possui 3 registros visíveis de andamento; o terceiro registro agrega vários registros antigos em um único texto. O segundo possui 68 linhas de andamento distribuídas entre as páginas 2, 3 e 4. **[FATO-ARQ]**

### 4.3 Campos apresentados

| Grupo | Campos no PDF |
|---|---|
| Escritório | nome, telefone, e-mail, endereço, logotipo, data/hora de emissão |
| Processo | número CNJ ou requerimento, área, pasta, fase, comarca, vara, sistema eletrônico |
| Partes | cliente e parte contrária |
| Objeto | ação/benefício, data do requerimento, valor, contingenciamento |
| Gestão | responsável |
| Notas | observações, tags, telefones e texto livre |
| Histórico | data e descrição de cada andamento manual |

### 4.4 Origem aparente

Todos os campos parecem vir do Advbox. Isso não significa que todos sejam gerados automaticamente: fase, observações, tags e andamentos manuais dependem de alimentação humana dentro do sistema. **[FATO-ARQ + HIPÓTESE]**

### 4.5 Filtros, agrupamentos e cálculos

- agrupamento principal por processo;
- ordenação aparente dos andamentos do mais recente para o mais antigo;
- nenhum cálculo, KPI ou totalização visível;
- o período não é explicitado como filtro: o relatório contém histórico integral disponível;
- o nome/código do parceiro não aparece no conteúdo do PDF, apesar de constar no nome do arquivo. **[FATO-ARQ]**

### 4.6 Problemas observados

1. **Exposição crítica de dados:** há uma senha e CPF em observações exportadas. Há ainda dados socioeconômicos, familiares e de saúde que exigem controle de necessidade e acesso.
2. **Fase contraditória:** um processo aparece cadastrado como “Aguardando distribuição da ação”, enquanto os andamentos mais recentes dizem “Aguardando julgamento do recurso”. A fase estruturada está desatualizada ou o texto livre passou a ser a fonte informal de verdade.
3. **Campos ausentes:** o primeiro processo não possui número, data de requerimento, valor, comarca, vara ou sistema eletrônico preenchidos.
4. **Histórico contaminado:** há textos “DELETE” e vários acontecimentos antigos concatenados dentro de um único andamento.
5. **Leitura difícil:** textos longos em caixa alta, repetição de frases, pouca hierarquia e ausência de síntese.
6. **Paginação fraca:** páginas de continuação repetem o cabeçalho do escritório, mas não deixam claro em todo ponto qual processo está sendo continuado; não há número de página.
7. **Sem rastreabilidade de seleção:** o relatório não mostra parceiro, critérios de filtro, quantidade de registros selecionados ou janela temporal.
8. **Mistura de públicos:** notas internas e dados operacionais são colocados no mesmo artefato que potencialmente será enviado ao parceiro.

## 5. Análise da planilha atual

### 5.1 Objetivo

Transformar o extrato extenso em uma visão consolidada da carteira, com KPIs, uma linha por cliente/processo e uma seção financeira.

### 5.2 Estrutura técnica

| Aba | Intervalo usado | Conteúdo |
|---|---:|---|
| `Resumo Parceiro` | A1:H12 | Título, data-base, 4 KPIs e 5 linhas financeiras |
| `Clientes` | A1:I3 | Cabeçalho e 2 registros |
| `Financeiro` | A1 | Vazia |

Não existem fórmulas, tabelas estruturadas, gráficos, imagens, validações, formatação condicional, nomes definidos ou vínculos externos. Há um filtro simples no cabeçalho de `Clientes` e congelamento da primeira linha. **[FATO-ARQ]**

### 5.3 Campos da aba `Clientes`

- Cliente
- Pasta
- Ação/benefício
- Fase atual
- Status executivo
- Responsável
- Contingenciamento
- Valor informado
- Status resumido

### 5.4 Indicadores da aba `Resumo Parceiro`

- Total de clientes: 2
- Benefícios concedidos: 0
- Em financeiro: 0
- Em judicial: 0
- Cliente com financeiro detalhado: não informado
- Recebido pelo parceiro: não informado
- A receber pelo parceiro: não informado
- Total do parceiro: não informado
- Receita do escritório registrada: não informado

### 5.5 Cálculos e filtros

Não há cálculos. Os quatro KPIs são números digitados. O filtro da aba `Clientes` permite filtrar as nove colunas, mas não existe mecanismo de atualização, deduplicação, reconciliação ou rastreamento da fonte. **[FATO-ARQ]**

### 5.6 Problemas observados

1. **Resumo não reproduzível:** não existe fórmula que demonstre como 2, 0, 0 e 0 foram obtidos.
2. **Possível inconsistência “Em judicial”:** o segundo registro possui número CNJ, vara, sistema eletrônico e status de julgamento de recurso no PDF, mas o KPI “Em judicial” é 0. A definição pode ser diferente, ou o KPI pode estar incorreto/desatualizado.
3. **Fase e status executivo divergem:** “Aguardando distribuição da ação” versus “Aguardando julgamento do recurso”.
4. **Ausência vira zero:** o primeiro processo não apresenta valor no PDF, mas a planilha registra 0. Isso mistura “não informado” com valor financeiro efetivamente zero.
5. **Valor sem definição:** o rótulo “Valor informado” não esclarece se é valor da causa, honorários esperados, honorários recebidos ou contingência.
6. **Status resumido sem regra:** não há tabela de mapeamento nem critérios para “Arquivado” ou para a repetição do status longo no segundo caso.
7. **Financeiro incompleto:** a aba está vazia e o resumo contém apenas hífens.
8. **Partner identity ausente:** nem a planilha mostra de forma explícita o nome/código do parceiro no cabeçalho.
9. **Escalabilidade baixa:** linhas, KPIs e períodos dependem de edição manual.

## 6. Comparação entre PDF e dashboard

### 6.1 Informações em ambos

- cliente;
- pasta;
- ação/benefício;
- fase atual;
- responsável;
- contingenciamento;
- valor;
- uma interpretação do andamento mais recente.

### 6.2 Apenas no PDF

- dados do escritório e momento exato de emissão;
- número do processo/requerimento e área;
- parte contrária;
- data do requerimento;
- comarca, vara e sistema eletrônico;
- observações, tags e contatos;
- histórico completo de andamentos manuais;
- dados sensíveis e credencial indevidamente armazenada nas notas.

### 6.3 Apenas no dashboard

- KPIs consolidados;
- “status executivo” e “status resumido”;
- estrutura conceitual de repasse financeiro do parceiro;
- tabela comparável com uma linha por cliente/processo.

### 6.4 Conclusão da comparação

O PDF é a **fonte operacional rica e não filtrada**; a planilha é a **camada de curadoria executiva**, mas atualmente sem regras automatizadas. A solução futura precisa unir a completude do primeiro com a clareza do segundo, sem transportar notas internas e dados sensíveis para o destinatário externo.

## 7. Mapa de dados e cobertura da API

| Informação desejada | Fonte atual | Cobertura técnica confirmada | Situação |
|---|---|---|---|
| Cliente e identificador | PDF/Advbox | `/customers`, `/customers/{id}`, clientes associados em `/lawsuits` | Confirmada |
| Processo, pasta e número | PDF/Advbox | `/lawsuits`, `/lawsuits/{id}` | Confirmada |
| Tipo e grupo da ação | PDF/Advbox | `type`, `group` do processo | Confirmada |
| Responsável | PDF/Advbox | `responsible_id`, `responsible` | Confirmada |
| Fase e etapa | PDF/Advbox | `stages_id`, `stage`, `steps_id`, `step` | Confirmada |
| Datas de criação/fechamento/arquivamento | Advbox | filtros e campos dos processos | Confirmada |
| Histórico de tarefas | Advbox | `/history/{lawsuit_id}` | Confirmada |
| Movimentações manuais/tribunal | PDF/Advbox | `/movements/{lawsuit_id}?origin=MANUAL|TRIBUNAL` | Confirmada em categoria; conteúdo textual completo precisa ser testado |
| Último andamento | PDF/Advbox | `/last_movements` | Confirmada |
| Transações e situação de pagamento | Advbox | `/transactions` com filtros por processo, cliente e datas | Confirmada |
| Honorários esperados/valor financeiro do processo | Advbox | `fees_expec` e `fees_money` em processo | Confirmada; semântica deve ser conciliada com “Valor” do PDF |
| Contingenciamento categórico | PDF | A API mostra um campo `contingency`, mas os exemplos públicos sugerem valor numérico, enquanto o PDF mostra classificação textual | Pendente |
| Data do requerimento | PDF | Pode ser `process_date`, mas a equivalência não está confirmada | Pendente |
| Comarca, vara, sistema eletrônico | PDF | Não aparecem nos exemplos públicos de resposta do processo | Pendente |
| Observações e tags | PDF | `notes` existe; tags separadas não estão documentadas | Parcial; não expor notas brutas |
| Vínculo parceiro → carteira | Nome dos arquivos/processo de negócio | Não existe filtro `partner_id` documentado nos endpoints públicos consultados | Gate crítico |
| Percentual/regra de repasse | Dashboard vazio | Transações existem, mas rateio por parceiro não está documentado | Gate crítico |

## 8. O que o Advbox permite atualmente

### 8.1 API oficial

A documentação oficial apresenta uma API REST em `https://app.advbox.com.br/api/v1`, com 22 endpoints agrupados em contatos, processos, tarefas, publicações, transações, documentos e configurações. Ela permite consultar processos, histórico, movimentações e transações, além de criar/atualizar alguns registros. Para este projeto, a integração deve começar **somente com operações GET**. [Documentação da API](https://api.softwareadvbox.com.br/docs) e [visão geral dos endpoints](https://api.softwareadvbox.com.br/docs/referencia).

A autenticação usa Bearer Token. O limite oficial informado é de 30 requisições GET por minuto por conta; respostas excedentes usam HTTP 429. [Autenticação e limites](https://api.softwareadvbox.com.br/docs/autenticacao).

A página comercial informa API para escritórios a partir de R$ 280/mês em 10/09/2026 e rotas de consulta para clientes, processos, intimações e movimentações. Preço, plano aplicável e condições comerciais precisam ser confirmados na contratação. [API Advbox](https://advbox.com.br/api).

### 8.2 Exportações

O Advbox permite:

- relatório de processos em Excel com dados da aba “Dados” conforme o filtro ativo;
- PDF resumido com cadastro, fase e último andamento;
- PDF completo com andamentos automáticos, andamentos manuais, intimações, tarefas e financeiro.

A exportação Excel é enviada por e-mail, exige perfil Gestor/Administrador e, na interface documentada, considera apenas os registros visíveis na paginação. O PDF é gerado no navegador. [Relatórios do menu Processos](https://guia.advbox.com.br/menu-processos/dicas-menu-processos).

**Uso recomendado:** fallback, reconciliação e carga inicial. Não deve ser o mecanismo principal de uma automação contínua, pois mantém passos humanos e riscos de paginação.

### 8.3 Webhooks e automação por eventos

O Flowter envia payload JSON para sistemas externos quando uma tarefa específica é concluída ou um processo muda de etapa. O próprio guia descreve esse envio como webhook outbound. [Flowter na prática](https://guia.advbox.com.br/flowter/flowter-na-pratica).

**Limitação:** não há confirmação pública de eventos para toda alteração de contato, toda movimentação manual ou toda transação. Por isso, o webhook deve sinalizar atualização rápida, enquanto uma sincronização periódica reconcilia a verdade completa.

### 8.4 n8n

Há nodes comunitários indicados oficialmente (`n8n-nodes-advbox`) e autenticação com token da API. [Integração Advbox + n8n](https://guia.advbox.com.br/api/integracao-advbox-n8n).

**Uso recomendado:** orquestração simples, notificações e protótipo. As regras financeiras, de segurança e de indicador devem permanecer em código versionado e testado.

### 8.5 Automação de navegador

É tecnicamente possível automatizar login, filtros e impressão, mas é a última alternativa. Mudanças visuais, sessão, MFA, CAPTCHA, paginação e falhas silenciosas tornam a manutenção e a auditoria piores. Deve ser usada apenas se a API não expuser um campo indispensável e se o fornecedor autorizar esse uso.

## 9. Arquitetura recomendada

```text
Advbox API (fonte principal)        Flowter (aceleração por evento)
             \                         /
              -> Coletor somente leitura
                        |
                 Staging criptografado
                        |
             Normalização + validações
                        |
                PostgreSQL auditável
                        |
        Motor de indicadores versionado
                  /             \
       Portal web autenticado   HTML para impressão
                  |                    |
     filtros e dados atuais      PDF versionado/imutável
                  \                    /
             Acesso do parceiro por RBAC
             + logs + expiração + revogação
```

### 9.0 Experiência multiparceiro

A tela inicial deve ser um diretório de parceiros. Cada item exibe nome, código, data da última sincronização, data do último PDF e eventual erro. Ao clicar, o usuário abre o relatório já gerado ou solicita uma nova geração a partir do último snapshot válido.

O clique **não deve consultar o Advbox e montar tudo em tempo real**. A solução deve sincronizar a base em lote e pré-gerar os PDFs após cada ciclo. Assim, o acesso é imediato, a plataforma não ultrapassa o rate limit e uma indisponibilidade momentânea do Advbox não impede a leitura do último relatório válido.

### 9.1 Funcionamento

1. O coletor consulta `/settings` para manter IDs de fases, etapas, usuários e categorias.
2. Obtém a carteira do parceiro por identificador confirmado. Se o Advbox não expuser esse vínculo, usa uma tabela de relacionamento controlada pelo escritório até existir integração melhor.
3. Busca processos paginados e, para cada processo, último andamento, movimentações/tarefas necessárias e transações financeiras autorizadas.
4. Mantém throttling, retry com backoff para 429 e idempotência.
5. Armazena o payload bruto por tempo curto e normaliza campos relevantes em tabelas relacionais.
6. Executa validações: ausente versus zero, duplicidade, fase versus último status, processo sem cliente, transação sem vínculo e carteira sem parceiro.
7. Calcula KPIs com regras identificadas por versão e data de vigência.
8. Publica os dados no portal e gera uma versão HTML imprimível.
9. Cria PDF apenas quando solicitado ou em agenda aprovada, registrando versão, data-base, checksum e origem dos dados.
10. Notifica o parceiro com um link autenticado/expirável; não envia dados sensíveis no corpo do e-mail.

### 9.2 Modelo mínimo de dados

- `partners`
- `partner_portfolios` ou `partner_lawsuits`
- `customers`
- `lawsuits`
- `lawsuit_customers`
- `stages` e `steps`
- `movements`
- `tasks`
- `transactions`
- `partner_financial_rules`
- `report_runs`
- `report_snapshots`
- `access_grants`
- `audit_events`
- `data_quality_issues`

### 9.3 Tecnologias sugeridas

**MVP e primeira produção:**

- Python 3.12;
- FastAPI para API interna e portal server-side;
- Pydantic para contratos e validação;
- SQLAlchemy/Alembic;
- PostgreSQL;
- Jinja2 + HTML/CSS para o relatório;
- Playwright/Chromium para PDF;
- armazenamento S3 compatível com criptografia e versionamento;
- job agendado e fila simples baseada no banco no MVP;
- cofre de segredos do provedor de nuvem;
- OpenTelemetry/Sentry ou equivalentes para logs, métricas e alertas.

**Portal mais sofisticado, se necessário:** Next.js/React consumindo a API interna. Não é requisito do MVP.

**DECISÃO:** manter o motor de regras independente do renderizador. Os mesmos dados devem alimentar HTML e PDF, evitando divergência entre formatos.

## 10. O que temos, o que falta descobrir e o que desenvolver

### 10.1 O que já temos

- dois exemplos reais de processo para teste;
- um PDF bruto completo gerado pelo Advbox;
- uma primeira seleção de campos executivos;
- quatro KPIs conceituais;
- cinco métricas financeiras desejadas;
- exemplos de inconsistência e ausência de dados;
- documentação pública suficiente para confirmar API, autenticação, limites, processos, movimentações, tarefas e transações.

### 10.2 O que precisamos descobrir

1. Como o parceiro P-017 é representado no Advbox: parceiro da rede, origem do contato, tag, campo próprio ou lista manual?
2. A API devolve esse vínculo mesmo sem documentá-lo? Existe rota adicional habilitada por conta?
3. Qual a regra de contagem de “cliente”: contato único, processo, contrato ou pasta?
4. O que caracteriza benefício concedido?
5. O que caracteriza “Em financeiro” e “Em judicial”?
6. Qual campo é o “Valor” do PDF: valor da causa, honorário esperado, honorário em dinheiro ou outro?
7. Como interpretar contingenciamento textual versus o campo da API?
8. Qual é a fonte do repasse ao parceiro e qual a fórmula contratual?
9. Como tratar entradas, parcelas futuras, cancelamentos, estornos, inadimplência, impostos e despesas?
10. O endpoint de movimentações retorna o texto integral dos andamentos manuais do caso real?
11. Comarca, vara, sistema eletrônico, tags e data do requerimento estão em rotas/campos acessíveis?
12. Qual periodicidade o parceiro espera: tempo real, diária, semanal ou mensal?
13. Quem pode ver CPF, dados de saúde, renda e observações internas?
14. Qual política de retenção, residência de dados, backup e descarte o escritório exige?
15. Qual identidade digital o parceiro usará: conta própria, SSO, MFA ou link temporário?

### 10.3 O que precisaremos desenvolver

- conector Advbox somente leitura;
- adaptador de paginação, throttling e retry;
- cadastro/mapeamento de parceiros;
- modelo de dados e migrações;
- regras de qualidade e reconciliação;
- motor versionado de KPIs;
- regra financeira de repasse;
- política de allowlist e redaction;
- templates HTML responsivos e de impressão;
- gerador de PDF;
- portal/autenticação/autorização;
- agendador e processamento em fila;
- logs, métricas, alertas e painel operacional;
- testes automatizados e conjunto de reconciliação;
- documentação de operação, incidentes e recuperação.

## 11. Alternativas de implementação

Estimativas abaixo são **hipóteses de planejamento** para um profissional de software com apoio parcial de alguém do jurídico/financeiro. Não incluem prazo comercial do fornecedor, contratação, saneamento amplo da base nem integrações corporativas ainda não informadas.

### 11.1 O que “sem custo” pode significar

| Interpretação | É possível? | Condições |
|---|---|---|
| Nenhum desembolso e nenhum custo de trabalho/operação | Não | Desenvolvimento, operação e segurança sempre consomem recursos. |
| Nenhuma licença de software adicional | Sim | Uso de componentes open source. A API e a infraestrutura precisam já estar contratadas. |
| Nenhuma mensalidade de hospedagem | Sim, para uso interno | Execução em servidor/máquina existente, com backup e acesso restrito à rede/VPN. |
| Acesso externo do parceiro sem nova infraestrutura | Somente se já existir infraestrutura segura | É necessário um serviço acessível, autenticação, domínio/certificado, backup e suporte. |
| Nenhuma mensalidade de API | Não com a API oficial, salvo benefício contratual | A página oficial anuncia API para escritórios a partir de R$ 280/mês. É preciso confirmar se o plano atual já inclui o recurso. |

| Alternativa | Complexidade | Custo | Segurança | Confiabilidade/manutenção | Escala | Prazo provável de MVP | Parecer |
|---|---|---|---|---|---|---|---|
| API customizada + banco + HTML/PDF + portal | Média/alta | Maior construção inicial + API | Melhor controle, se bem implementada | Alta; contrato explícito e testes | Alta | 4-6 semanas após acesso e regras | **Recomendada** |
| API + n8n + banco + template HTML/PDF | Média | Menor início; custo de hospedagem/gestão do n8n | Boa, exige governança de credenciais e nós | Média/alta; fluxos visuais podem ficar difíceis de testar | Média | 3-5 semanas | Boa para MVP/orquestração |
| Exportação Excel/PDF + processamento | Baixa/média | Menor | Depende de e-mail, arquivos e permissões | Média/baixa; paginação e acionamento humano | Baixa/média | 1-3 semanas | Fallback ou prova rápida, não automação plena |
| Automação de navegador | Média no início, alta depois | Baixo licenciamento, alto custo recorrente de manutenção | Pior; sessão e credenciais de usuário | Baixa; suscetível a mudanças de interface | Baixa | 2-4 semanas | Último recurso |

### Dependência do Advbox

Todas as alternativas dependem do Advbox como fonte. A API reduz a dependência da interface visual, mas não elimina mudanças de contrato, campos, limites ou disponibilidade. A solução deve ter cache, snapshots, reconciliação, alertas e capacidade de reprocessar.

### 11.2 Viabilidade de extração em escala

Sim, a extração é tecnicamente possível para uma carteira multiparceiro. O endpoint de processos é paginado e a documentação recomenda páginas de até 100 registros. O endpoint de últimos andamentos também trabalha com 100 itens por página. O limite geral é 30 consultas GET por minuto.

O sistema deve buscar a base **uma vez por ciclo** e depois agrupá-la por parceiro. Não deve repetir a extração completa para cada parceiro. Uma estimativa simplificada é:

```text
consultas do ciclo ≈ páginas de processos
                   + páginas de últimos andamentos
                   + páginas de transações
                   + consultas de detalhe somente dos processos alterados
```

Exemplos teóricos, sem contar transações e detalhes:

- 1.000 processos: aproximadamente 10 páginas de processos + 10 páginas de últimos andamentos;
- 5.000 processos: aproximadamente 50 + 50 páginas;
- uma carga integral que consultasse individualmente 1.000 processos consumiria, no mínimo, cerca de 34 minutos apenas pelo limite de 30 GET/minuto.

Isso não inviabiliza o projeto. Significa que a carga inicial deve usar fila e que os ciclos seguintes precisam ser incrementais, consultando detalhes apenas quando algo mudou. A quantidade de PDFs também não é o problema principal: PDFs são gerados localmente a partir do banco e não consomem a API.

## 12. Formato e desenho do relatório automatizado

### 12.1 Formato recomendado

**Portal web autenticado como principal + PDF sob demanda como secundário.**

O portal é melhor para filtros, dados atualizados, expansão de detalhes, correções, revogação de acesso e auditoria. O PDF é melhor para fechamento mensal, aprovação, arquivo, reunião e prova do que foi apresentado em uma data.

Um dashboard hospedado em BI pode acelerar análises internas, mas não é a primeira escolha para o parceiro se exigir licenças por usuário, tiver controle de linha complexo ou expuser metadados. Pode ser avaliado depois.

### 12.2 Estrutura proposta

1. **Identificação:** parceiro, código, período, data/hora de atualização, versão do relatório e cobertura dos dados.
2. **Resumo executivo:** clientes únicos, processos ativos, arquivados, em produção, administrativos, judiciais, recursais, em execução e com pendência financeira.
3. **Qualidade/alertas:** fase divergente do último andamento, cadastro incompleto, processo sem atualização há X dias, transação sem vínculo e dados pendentes. Os limiares devem ser configurados, não inventados.
4. **Carteira:** cliente, pasta, processo/requerimento mascarado quando necessário, ação, etapa, fase, responsável, último andamento e data.
5. **Financeiro autorizado:** recebido no período, a receber, vencido, total do parceiro, base de cálculo, percentual/regra aplicada e conciliação.
6. **Detalhe do caso:** dados essenciais, últimos andamentos relevantes e tarefas/prazos autorizados.
7. **Metodologia:** definições dos indicadores, exclusões, ausências e fonte.
8. **Apêndice opcional:** histórico completo. Não deve aparecer no resumo padrão.

### 12.3 Indicadores recomendados

- clientes únicos e processos por cliente;
- processos por etapa e fase;
- novos/encerrados no período;
- dias desde o último andamento;
- processos com fase/status divergentes;
- tarefas vencidas/próximas, se autorizadas;
- honorários recebidos, a receber e vencidos;
- repasse devido, pago e saldo do parceiro;
- completude cadastral.

Todo indicador deve exibir definição, período, numerador/denominador e tratamento de ausências. “Não informado” nunca deve virar zero por conveniência.

## 13. Segurança, privacidade e controle de acesso

A ANPD orienta controles baseados em autenticação, autorização e auditoria, além de medidas técnicas e administrativas desde a concepção do serviço. [Guia de Segurança da Informação da ANPD](https://www.gov.br/anpd/pt-br/centrais-de-conteudo/materiais-educativos-e-publicacoes/processo-guia-orientativo-sobre-seguranca-da-informacao-para-agentes-de-tratamento-de-pequeno-porte.pdf).

Controles mínimos:

- token do Advbox em cofre de segredos; nunca em código, planilha, chat ou PDF;
- usuário técnico somente leitura, se o Advbox suportar esse escopo;
- MFA para usuários humanos;
- RBAC por parceiro e, preferencialmente, controle por linha/tenant;
- allowlist de campos destinados ao parceiro;
- bloqueio padrão de `notes`, documentos e contatos sensíveis;
- redaction de CPF, credenciais, telefone e dados de saúde conforme finalidade;
- criptografia em trânsito e em repouso;
- URLs de PDF curtas, autenticadas ou assinadas e revogáveis;
- logs de acesso e download sem registrar conteúdo sensível;
- separação entre ambiente de teste e produção;
- dados sintéticos ou mascarados em desenvolvimento;
- política definida de retenção e exclusão;
- backups testados e plano de recuperação;
- resposta a incidente e rotação de chaves;
- revisão contratual dos provedores usados como operadores/suboperadores.

**Regra de produto:** nunca publicar diretamente todas as observações do Advbox. O que é seguro para a equipe interna não é automaticamente seguro para o parceiro.

## 14. Plano de execução do projeto

### Fase 0 - Contenção imediata

- **Objetivo:** remover o risco mais grave já identificado.
- **Tarefas:** verificar se a credencial exposta está ativa, rotacioná-la se necessário, identificar outros relatórios com credenciais e orientar a equipe.
- **Dependências:** administrador dos sistemas envolvidos.
- **Resultado:** credencial antiga inválida e regra provisória de não exportação de notas sensíveis.
- **Risco:** credencial reutilizada em outros serviços.
- **Concluída quando:** a rotação e a busca por exposição correlata estiverem registradas.

### Fase 1 - Descoberta e definição de negócio

- **Objetivo:** tornar cada KPI e cada campo inequívocos.
- **Tarefas:** mapear o fluxo real, responsáveis, frequência, destinatários, regras de status, períodos e financeiro.
- **Dependências:** jurídico, financeiro, controladoria e responsável pelo parceiro.
- **Resultado:** glossário aprovado e exemplos de entrada/saída.
- **Risco:** regras tácitas divergentes entre equipes.
- **Concluída quando:** todos os KPIs possuem definição, fonte, fórmula, exceções e proprietário.

### Fase 2 - Validação do acesso ao Advbox

- **Objetivo:** comprovar cobertura com dados reais e sem escrita.
- **Tarefas:** contratar/ativar API; gerar token seguro; testar `/settings`, `/customers`, `/lawsuits`, `/movements`, `/history`, `/last_movements` e `/transactions`; conferir limites e erros.
- **Dependências:** plano/API, autorização do escritório e ambiente seguro.
- **Resultado:** matriz campo → endpoint → resposta real.
- **Risco:** campos ou vínculo de parceiro ausentes.
- **Concluída quando:** os dois processos P-017 são encontrados e reconciliados com os arquivos.

### Fase 3 - Gate do parceiro e financeiro

- **Objetivo:** resolver os dois pontos que limitam a viabilidade.
- **Tarefas:** localizar o vínculo parceiro-carteira; testar filtros; definir tabela auxiliar se necessário; formalizar contratos de repasse e casos de estorno/inadimplência.
- **Dependências:** resultado da Fase 2 e contratos/regras internas.
- **Resultado:** algoritmo determinístico de carteira e repasse.
- **Risco:** necessidade permanente de manutenção manual do vínculo.
- **Concluída quando:** uma amostra é reconciliada sem diferença material aprovada.

### Fase 4 - Modelo de dados e ingestão

- **Objetivo:** criar uma cópia operacional mínima, auditável e reprocessável.
- **Tarefas:** schema, migrações, paginação, throttle, retry, idempotência, carga inicial e sincronização incremental.
- **Dependências:** contrato de dados aprovado.
- **Resultado:** banco populado com rastreabilidade de origem e data.
- **Risco:** duplicidade, exclusões e atualizações tardias.
- **Concluída quando:** duas execuções sucessivas não duplicam registros e a reconciliação diária fecha.

### Fase 5 - Qualidade e indicadores

- **Objetivo:** substituir números digitados por regras testáveis.
- **Tarefas:** implementar mapeamentos, ausente versus zero, status por etapa, alertas de divergência e cálculos financeiros.
- **Dependências:** glossário e dados normalizados.
- **Resultado:** KPIs versionados com testes unitários.
- **Risco:** fase desatualizada e narrativa livre conflitante.
- **Concluída quando:** o caso P-017 e uma amostra adicional batem com validação humana documentada.

### Fase 6 - Relatório e experiência

- **Objetivo:** apresentar a informação de forma clara e segura.
- **Tarefas:** protótipo HTML, tabela da carteira, detalhes, impressão, PDF, estados de erro e “dados indisponíveis”.
- **Dependências:** indicadores estabilizados e política de campos.
- **Resultado:** portal interno de pré-visualização e PDF consistente.
- **Risco:** excesso de detalhe e quebra de paginação.
- **Concluída quando:** jurídico, financeiro e uma amostra de destinatários de perfis diferentes aprovam conteúdo e legibilidade.

### Fase 7 - Identidade, autorização e privacidade

- **Objetivo:** garantir que cada parceiro veja somente sua carteira.
- **Tarefas:** login/MFA, RBAC, expiração/revogação, logs, redaction, retenção e testes de isolamento.
- **Dependências:** provedor de identidade e decisão de distribuição.
- **Resultado:** matriz de acesso implementada.
- **Risco:** vazamento entre parceiros.
- **Concluída quando:** testes positivos e negativos demonstram isolamento de tenant e de campos.

### Fase 8 - Testes e homologação

- **Objetivo:** provar exatidão, resiliência e segurança.
- **Tarefas:** testes unitários, integração, carga, 401/429/5xx, dados faltantes, duplicidade, regressão visual, reconciliação financeira e UAT.
- **Dependências:** solução integrada.
- **Resultado:** relatório de homologação e pendências aceitas.
- **Risco:** amostra pequena esconder exceções.
- **Concluída quando:** critérios de precisão, segurança e recuperação acordados forem atendidos.

### Fase 9 - Implantação e operação

- **Objetivo:** colocar o fluxo em produção com observabilidade.
- **Tarefas:** infraestrutura, CI/CD, secrets, backup, alertas, runbooks, responsáveis e janela de suporte.
- **Dependências:** homologação e aprovação de segurança.
- **Resultado:** execução agendada e geração auditável.
- **Risco:** falha silenciosa ou relatório desatualizado.
- **Concluída quando:** uma execução completa em produção for reconciliada e os alertas forem testados.

### Fase 10 - Validação multiparceiro e expansão de acesso

- **Objetivo:** validar o processamento de toda a carteira antes de ampliar o acesso externo.
- **Tarefas:** importar todos os parceiros elegíveis, gerar todos os relatórios internamente, reconciliar uma amostra representativa de parceiros e liberar acesso externo por ondas após aprovação.
- **Dependências:** operação estável.
- **Resultado:** plataforma multiparceiro processando toda a carteira e decisão de abertura baseada em evidência.
- **Risco:** regras ou qualidade de cadastro variarem entre parceiros.
- **Concluída quando:** dois ciclos completos de toda a carteira forem gerados, a amostra de reconciliação for aprovada e houver plano de liberação externa.

## 15. Primeira versão multiparceiro

Esta versão substitui a proposta anterior de um MVP limitado a um parceiro. O modelo técnico, o banco, a interface e o processamento devem suportar todos os parceiros desde a primeira entrega utilizável.

### 15.1 O que entra

- cadastro/importação de todos os parceiros elegíveis;
- tela inicial com lista e busca por parceiro;
- associação parceiro → clientes/processos;
- fila de processamento e geração em lote;
- somente leitura da API;
- identificação do cliente, pasta, processo, ação, etapa/fase, responsável, valor claramente definido e último andamento;
- KPIs com regras aprovadas;
- detecção de fase/status divergente e campos ausentes;
- HTML interno responsivo;
- PDF individual por parceiro, gerado a partir do mesmo HTML;
- armazenamento de snapshot e log da execução;
- painel com sucesso, falha, última atualização e possibilidade de reprocessar somente um parceiro;
- aprovação humana por amostragem antes do primeiro envio externo.

### 15.2 O que fica para a segunda etapa

- autoatendimento amplo do parceiro;
- histórico completo e documentos;
- notificações em tempo real;
- resumos por IA;
- comparação entre períodos e gráficos avançados;
- delegação de administradores por parceiro, autoatendimento avançado e cadastro autônomo;
- automação financeira, caso as regras ainda não estejam formalizadas;
- escrita de dados de volta no Advbox.

### 15.3 Dados e formato inicial

A primeira versão usa os campos estruturados da API e, no máximo, os cinco andamentos mais recentes autorizados. Observações brutas ficam excluídas. O formato inicial deve ser uma plataforma HTML interna com diretório de parceiros, visualização do relatório e botão para abrir/regenerar o PDF. O processamento inicial abrange toda a carteira; a validação detalhada usa P-017 e uma amostra que cubra parceiros pequenos, médios, grandes, com e sem financeiro.

### 15.4 Fluxo completo da primeira versão

```text
Agendamento ou “Sincronizar todos”
→ consulta paginada e segura à API uma vez por ciclo
→ identificação de todas as carteiras
→ normalização
→ validação e alertas
→ cálculo dos KPIs por parceiro
→ fila de geração de PDFs
→ diretório de parceiros atualizado
→ aprovação interna por amostragem
→ links seguros aos destinatários autorizados
→ logs de acesso, falhas e expiração
```

### 15.5 Como validar

1. Conferir os dois processos de P-017 contra o PDF, campo a campo, sem limitar o sistema a esse parceiro.
2. Selecionar amostras de parceiros de tamanhos e situações diferentes.
3. Demonstrar que dado ausente aparece como “Não informado”, e não zero.
4. Demonstrar a divergência de fase/status como alerta.
5. Conferir todos os KPIs por cálculo manual independente.
6. Garantir que CPF, senha, telefone e notas internas não aparecem.
7. Simular token inválido, 429, indisponibilidade e reprocessamento parcial.
8. Confirmar que uma falha em um parceiro não bloqueia os demais.
9. Validar que um usuário de outro parceiro não acessa P-017.
10. Obter aprovação formal de jurídico, financeiro e segurança.

## 16. Riscos e limitações

| Risco | Impacto | Mitigação |
|---|---|---|
| Vínculo do parceiro não exposto pela API | Carteira incorreta ou manutenção manual | Spike técnico; tabela auxiliar governada; solicitar rota ao Advbox |
| Regras financeiras indefinidas | Valores errados e disputa | Contrato de regras, reconciliação e aprovação do financeiro |
| Fase do processo desatualizada | KPI/status enganoso | Regra de qualidade e correção na fonte |
| Notas com credenciais/dados sensíveis | Vazamento grave | Allowlist, redaction, bloqueio de notas e treinamento |
| Rate limit GET de 30/min | Sincronização lenta em carteiras grandes | Paginação eficiente, cache, fila e backoff |
| Eventos Flowter incompletos | Atualização perdida | Reconciliação periódica obrigatória |
| Mudança na API | Falha de integração | Versionamento, testes de contrato e monitoramento |
| PDF encaminhado fora do portal | Perda de controle pós-download | Minimização, marca d'água, expiração do link e política de distribuição |
| Texto livre redundante/contaminado | Relatório ilegível | Últimos eventos estruturados, deduplicação e curadoria |
| Automação de navegador | Quebras frequentes | Evitar; usar somente como contingência autorizada |

## 17. Decisões que precisam de aprovação antes do código

1. Definição oficial dos KPIs atuais.
2. Definição do vínculo parceiro-carteira.
3. Definição da base e das regras de repasse financeiro.
4. Campos permitidos por perfil de parceiro.
5. Periodicidade e política de fechamento.
6. Portal, link seguro ou outro canal de entrega.
7. Retenção dos dados e PDFs.
8. Responsáveis por validar jurídico, financeiro, segurança e operação.

## 18. Conclusão

O processo atual faz duas coisas distintas: o Advbox produz um extrato operacional completo, e uma planilha transforma parte desse extrato em resumo executivo. A primeira parte contém os dados necessários, mas também excesso de texto e informações sensíveis; a segunda melhora a leitura, porém é integralmente estática e não possui regras auditáveis.

A automação deve usar a API oficial como fonte, e não tentar reproduzir visualmente o PDF. O melhor produto é um portal seguro com visão atualizada e um PDF sob demanda para fechamento. A implementação deve começar por um teste de integração somente leitura que resolva o vínculo do parceiro e comprove os campos financeiros. Esses gates determinam se o projeto passa de viabilidade Média para Alta.

## Fontes oficiais consultadas

- [API Advbox - visão comercial e plano para escritórios](https://advbox.com.br/api)
- [Documentação oficial da API](https://api.softwareadvbox.com.br/docs)
- [Referência dos 22 endpoints](https://api.softwareadvbox.com.br/docs/referencia)
- [Autenticação e rate limits](https://api.softwareadvbox.com.br/docs/autenticacao)
- [Listagem e filtros de processos](https://api.softwareadvbox.com.br/docs/lawsuits/getLawsuits)
- [Dados completos do processo](https://api.softwareadvbox.com.br/docs/lawsuits/getLawsuitById)
- [Histórico de tarefas](https://api.softwareadvbox.com.br/docs/lawsuits/getHistoryByLawsuitId)
- [Movimentações manuais e de tribunal](https://api.softwareadvbox.com.br/docs/lawsuits/getMovementsByLawsuitId)
- [Último andamento por processo](https://api.softwareadvbox.com.br/docs/lawsuits/getLastMovements)
- [Transações financeiras](https://api.softwareadvbox.com.br/docs/transactions/getTransactions)
- [Configurações e IDs da conta](https://api.softwareadvbox.com.br/docs/settings/getSettings)
- [Relatórios de processos em Excel e PDF](https://guia.advbox.com.br/menu-processos/dicas-menu-processos)
- [Parceiros no Advbox](https://guia.advbox.com.br/menu-configuracoes/parceiros)
- [Flowter e payloads de saída](https://guia.advbox.com.br/flowter/flowter-na-pratica)
- [Integração oficial com n8n](https://guia.advbox.com.br/api/integracao-advbox-n8n)
- [Guia de Segurança da Informação da ANPD](https://www.gov.br/anpd/pt-br/centrais-de-conteudo/materiais-educativos-e-publicacoes/processo-guia-orientativo-sobre-seguranca-da-informacao-para-agentes-de-tratamento-de-pequeno-porte.pdf)
