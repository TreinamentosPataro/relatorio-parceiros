# Inventário dos ambientes

**Situação:** parcialmente confirmado em 11/09/2026  
**Finalidade:** separar o ambiente local de desenvolvimento da hospedagem de produção e transformar ambos em requisitos verificáveis.  
**Regra:** não registrar neste arquivo senhas, tokens, chaves privadas ou outros segredos.

## Ambientes definidos

| Ambiente | Finalidade | Situação |
|---|---|---|
| Máquina local Windows | Desenvolvimento, testes e uso de Docker | Inspecionada e validada para a fundação técnica. |
| Vercel | Portal e funções, publicados em domínio/subdomínio próprio | Conta no plano Hobby/Free confirmada. Esse plano não é elegível para a produção profissional da empresa; migração para plano adequado está pendente. |
| PostgreSQL externo | Persistência durável da aplicação | Obrigatório para produção na Vercel; provedor e plano ainda não escolhidos. |
| Armazenamento de objetos externo | PDFs versionados e demais arquivos duráveis | Obrigatório para produção; provedor e plano ainda não escolhidos. |

## Inventário preenchido

| Item | Resposta confirmada | Evidência/observação | Impacto na implantação |
|---|---|---|---|
| Sistema operacional local | Windows x64, versão 25H2, build 26200 | Leitura local; o rótulo legado do Registro informa “Windows 10 Home”, por isso a versão/build são a referência técnica | A execução local deverá ser compatível com Windows; a produção usará o runtime Linux gerenciado da Vercel. |
| CPU / RAM / disco local | Intel Core i5-1334U; 12 processadores lógicos; 7,7 GB de RAM; unidade C: com 476,0 GB, sendo 369,1 GB livres | Leitura local. Havia cerca de 0,5 GB de RAM livre no momento da inspeção, valor que varia com a carga | Disco é suficiente para a fundação; a baixa memória livre observada pode afetar Docker e testes com Chromium e deve ser reavaliada durante a execução. |
| Docker local | Docker Desktop ativo; Engine 29.7.2 e Compose 5.5.0 | Instalação por usuário em `AppData`; CLI não está no `PATH`, mas foi executada diretamente e os contêineres foram validados | Docker/Compose está aprovado para desenvolvimento local. O caminho não define o runtime de produção da Vercel. |
| Acesso SSH | Cliente SSH presente; servidor SSH local não encontrado | Inspeção de comandos e serviços do Windows | Vercel não exige SSH tradicional para deploy; acesso será por Git, painel e/ou CLI. |
| Proxy reverso | Não aplicável como componente autogerenciado na arquitetura Vercel | A Vercel fornece roteamento/CDN e funções gerenciadas | Não criar Nginx/Caddy para produção. Regras necessárias serão configuradas no projeto Vercel. |
| Domínio ou subdomínio | Domínio corporativo confirmado: `patarotreinamentos.com.br` | Ainda falta escolher se será usado o domínio raiz ou um subdomínio específico e confirmar quem altera o DNS | Para preservar o site principal, recomenda-se um subdomínio dedicado; o nome final depende de aprovação. O registro será o indicado pela Vercel, normalmente CNAME para subdomínio. |
| HTTPS | Suportado pela Vercel, ainda não configurado para este projeto | A Vercel provisiona certificado após validação e propagação do DNS | O portal com autenticação/dados reais só poderá ser liberado após domínio verificado e certificado ativo. |
| PostgreSQL local | PostgreSQL 17 disponível via Docker Compose | Contêiner `postgres:17-alpine` iniciou e passou no healthcheck; `psql` continua ausente no Windows | Desenvolvimento usará o contêiner e volume local; produção continuará usando serviço externo. |
| PostgreSQL de produção | Externo à Vercel; provedor pendente | A Vercel orienta usar integrações como Neon, Supabase ou AWS Aurora Postgres; o antigo Vercel Postgres não está disponível para projetos novos | Escolher região próxima da função, SSL e pool de conexões compatível com serverless. |
| Armazenamento de PDFs | Externo e durável; provedor pendente | Funções Vercel possuem sistema de arquivos somente leitura e `/tmp` temporário de até 500 MB | Não usar “disco do servidor”. Gerar temporariamente e enviar o PDF para storage privado, por exemplo Vercel Blob ou equivalente aprovado. |
| Política de backup | Não confirmada | Deve cobrir PostgreSQL e armazenamento de PDFs; rollback de deployment da Vercel não substitui backup de dados | Selecionar retenção e testar restauração antes da produção. |
| Servidor SMTP | Não aplicável ao MVP; serviço não informado | A Vercel não fornece serviço de e-mail para domínio | Não implementar e-mail até existir provedor, remetente e conteúdo aprovados. |
| Monitoramento | Plano Hobby informado; política operacional pendente | O plano Hobby oferece recursos básicos e retenção limitada; a produção deverá ser avaliada no plano profissional escolhido | Definir logs, alertas, retenção e responsável antes da produção. |
| Responsável operacional | A preencher | Informar função e substituto; evite dados pessoais desnecessários | Define quem recebe alertas, aprova deploys, restaura dados e coordena incidentes. |
| Ferramentas locais auxiliares | Git 2.55.0, Node.js 24.20.0 e npm 11.19.0 disponíveis | Inspeção local | Permitem Git e instalação futura da CLI da Vercel. |
| Python local | Python 3.12.14 disponível dentro do Docker; não instalado no Windows | Imagem de desenvolvimento construída e testes executados no contêiner | Docker é o caminho local oficial; instalação nativa permanece opcional. |
| Vercel CLI local | Não encontrada | `vercel` ausente do `PATH` | Pode ser instalada posteriormente; não é necessária nesta etapa documental. |

## Requisitos derivados da Vercel

1. FastAPI pode ser publicado no runtime oficial Python da Vercel, onde a aplicação se torna uma Vercel Function. O runtime Python está em Beta e suporta Python 3.12, 3.13 e 3.14. Fonte: [Python Runtime](https://vercel.com/docs/functions/runtimes/python) e [FastAPI on Vercel](https://vercel.com/docs/frameworks/backend/fastapi).
2. A produção não usará Docker Compose como modelo principal. A fundação deverá continuar executável localmente por Docker, quando a instalação estiver acessível, mas também compatível com o runtime oficial da Vercel.
3. O sistema de arquivos da função é somente leitura, com `/tmp` temporário limitado a 500 MB. Banco, relatórios e checkpoints precisam de persistência externa. Fonte: [Vercel Function Runtimes](https://vercel.com/docs/functions/runtimes).
4. PostgreSQL deverá vir de um provedor externo integrado ou acessível pela Vercel. Devem ser escolhidos região, SSL, pool de conexões, backup e custo. Fonte: [Postgres on Vercel](https://vercel.com/docs/postgres) e [Marketplace Storage](https://vercel.com/docs/marketplace-storage).
5. PDFs exigem uma prova técnica específica. Chromium/Playwright não pode ser presumido como equivalente a um servidor Docker tradicional; o pacote, o binário, a memória, o tempo de função e o envio imediato para storage deverão ser validados.
6. Sincronizações longas deverão ser divididas em páginas/jobs retomáveis. O tempo máximo de função e a frequência do Cron variam por plano; no Hobby, Cron é limitado a uma execução diária. Fonte: [Function Limits](https://vercel.com/docs/functions/limitations) e [Cron Usage and Pricing](https://vercel.com/docs/cron-jobs/usage-and-pricing).
7. O subdomínio poderá ser configurado por CNAME conforme o valor exibido no projeto. Após a verificação DNS, a Vercel tenta provisionar o certificado automaticamente. Fonte: [Custom Domain](https://vercel.com/docs/domains/working-with-domains/add-a-domain) e [SSL Certificates](https://vercel.com/docs/domains/working-with-ssl).
8. O banco e o storage devem ficar próximos da região configurada para as funções e possuir termos de tratamento de dados adequados ao projeto.
9. O plano Hobby é destinado apenas a uso pessoal ou não comercial. Como esta é uma aplicação profissional do escritório, a produção deverá usar Pro ou outro plano contratualmente adequado. Fonte: [Vercel Terms — Hobby Plan](https://vercel.com/legal/terms) e [Account Plans](https://vercel.com/docs/plans).

## Informações que não podem ser descobertas apenas nesta máquina

- projeto/time Vercel que receberá a aplicação;
- host final: domínio raiz ou subdomínio específico, e quem pode alterar o DNS;
- decisão/contratação de plano Vercel adequado ao uso profissional;
- provedor/plano de PostgreSQL de produção;
- provedor/plano de armazenamento privado de PDFs;
- política de backup e restauração desses dois provedores;
- responsável operacional e destinatários de alertas;

Essas informações dependem de conta, contrato ou decisão organizacional e não devem ser inferidas a partir do hardware local.
