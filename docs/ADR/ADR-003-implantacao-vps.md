# ADR-003 — Implantação simples em VPS

**Data:** 25/09/2026

**Estado:** aprovada para orientar a preparação; implantação ainda não autorizada

## Contexto

O escritório precisa usar a plataforma no dia a dia, mas não dispõe de uma máquina própria que possa permanecer disponível. A operação será interna, de baixo volume e iniciada manualmente a partir do PDF exportado do Advbox. A meta é evitar custo recorrente quando houver uma franquia gratuita adequada, sem depender dessa gratuidade para a segurança ou a continuidade do sistema.

A arquitetura anterior usava Vercel, PostgreSQL externo, armazenamento de objetos e um executor externo de jobs. Esse conjunto aumentava o número de serviços e exigia um plano profissional da Vercel.

## Decisão

Adotar como alvo de produção **uma única VPS Linux administrada pelo escritório**, com:

- Docker Compose;
- proxy reverso com HTTPS;
- aplicação FastAPI;
- worker executado no mesmo host;
- PostgreSQL em volume persistente separado;
- PDFs-fonte e relatórios em volumes privados, nunca servidos diretamente pelo proxy;
- segredos em arquivo de ambiente protegido no host, fora da imagem e do Git;
- acesso inicial somente para usuários internos autenticados;
- processamento iniciado manualmente; agendamento automático não é requisito do MVP;
- backup criptografado do banco e dos objetos, copiado para um destino separado da VPS;
- restauração testada antes do uso real.

O portal externo para parceiros, alta disponibilidade, múltiplos servidores, Kubernetes, Redis, Celery, storage S3 e SSO ficam fora do MVP. Eles somente serão adicionados diante de necessidade comprovada.

## Acesso de rede

O alvo preferencial é acesso por rede privada/VPN. Se o portal precisar ser exposto à internet, o portão de produção deverá comprovar HTTPS, firewall, limitação de tentativas, atualização do host, autenticação, logs mínimos e procedimento de incidente. PostgreSQL, volumes e portas administrativas nunca serão publicados diretamente.

## Capacidade inicial

A seleção da VPS deve validar, no mínimo, Linux x86_64, Docker, 2 vCPU, 4 GB de RAM, 40 GB de disco persistente e espaço compatível com a retenção aprovada. Esses valores são referência para o teste com PostgreSQL e Chromium, não uma promessa de capacidade.

## Custo

Software e componentes escolhidos não exigem licença paga. Uma franquia gratuita de VPS pode ser usada somente se permitir uso profissional, persistência, região aceitável e capacidade suficiente. Gratuidade, disponibilidade de vagas e permanência das condições não são garantidas. Se nenhuma oferta atender aos portões, haverá custo de infraestrutura ou o projeto permanecerá sem implantação.

Nenhum provedor será contratado e nenhum recurso será criado sem uma etapa de implantação específica.

## Consequências

- Vercel deixa de ser o alvo de produção; sua configuração permanece temporariamente no repositório como artefato histórico até a limpeza controlada em PDF-8.
- PostgreSQL e armazenamento privado podem residir na mesma VPS no MVP, reduzindo serviços externos.
- A VPS é um ponto único de falha; o backup precisa estar fora dela.
- Atualizações do sistema, firewall, certificados, monitoramento, backup e restauração passam a ser responsabilidade operacional do escritório.
- Os bloqueios de conteúdo, privacidade, retenção e homologação continuam válidos.

## Portão para implementar

PDF-8 deverá selecionar e inventariar a VPS, criar a composição de produção sem bind mount do código, configurar proxy/HTTPS, volumes, backups, restauração, firewall e operação. Primeiro será usado staging sintético. Dados reais e go-live continuam dependendo de autorização específica.
