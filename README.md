# Plataforma de Relatórios de Parceiros

Aplicação multiparceiro com sincronização Advbox somente leitura, modelo normalizado, relatório HTML/PDF e portal interno. As telas e arquivos do portal nesta etapa usam apenas dados sintéticos; não há publicação real nem implantação profissional.

## Stack

- Python 3.12 e FastAPI;
- Jinja2 para páginas server-side;
- SQLAlchemy 2, Alembic e PostgreSQL;
- HTTPX para integrações futuras somente leitura;
- Playwright para geração local de PDF;
- Argon2id e sessões PostgreSQL para a prévia autenticada local;
- pytest, respx e Ruff para qualidade;
- Docker Compose para desenvolvimento local;
- runtime Python/FastAPI da Vercel como alvo de hospedagem.

## Preparação local com Docker

O Docker Desktop precisa estar iniciado. No PowerShell:

```powershell
Copy-Item .env.example .env
docker compose up --build
```

O valor de `POSTGRES_PASSWORD` em `.env.example` é apenas um marcador. Substitua-o no arquivo `.env` local e mantenha `DATABASE_URL` coerente se também executar a aplicação fora do Compose.

Com os serviços saudáveis, acesse `http://localhost:8000/health`. A resposta esperada é:

```json
{"status":"ok"}
```

Para preparar o portal sintético, aplique as migrations, gere as prévias e cadastre um usuário interno interativamente conforme [docs/PORTAL.md](docs/PORTAL.md). Depois acesse `http://localhost:8000/portal/login`. Não existe credencial padrão. A demonstração local não libera relatórios reais.

Para encerrar:

```powershell
docker compose down
```

O volume do PostgreSQL é preservado. Use `docker compose down --volumes` somente quando houver intenção explícita de apagar os dados locais.

## Execução nativa alternativa

Requer Python 3.12 e PostgreSQL acessível:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
uvicorn app:app --app-dir src --reload
```

## Testes e verificações

Com Docker:

```powershell
docker compose run --rm app pytest
docker compose run --rm app ruff check .
docker compose run --rm app ruff format --check .
```

Com o ambiente virtual ativo:

```powershell
pytest
ruff check .
ruff format --check .
```

## Auditoria segura do Advbox

Após configurar `ADVBOX_API_TOKEN` somente no `.env` local ignorado pelo Git:

```powershell
docker compose run --rm app audit-advbox
```

O comando usa exclusivamente `GET`, limita-se a 20 requisições por minuto e grava apenas metadados sanitizados em `docs/ADVBOX_API_AUDIT.md` e `docs/VINCULO_PARCEIRO_CARTEIRA.md`. Não salva respostas brutas nem valores de campos.

Para validar toda a carteira e produzir somente contagens:

```powershell
docker compose run --rm app python -m partner_reports.integrations.advbox.linkage_cli
```

## Configuração

A configuração é validada por `pydantic-settings`. `APP_ENV` e `DATABASE_URL` são obrigatórias. Uma ausência ou URL incompatível com PostgreSQL interrompe a inicialização com erro de validação; o endpoint de saúde não devolve configurações nem segredos.

O arquivo `.env` é ignorado pelo Git. Em produção, use variáveis de ambiente da Vercel e nunca grave credenciais no repositório, imagem, documentação ou logs.

## Banco e migrations

Com o PostgreSQL local iniciado:

```powershell
docker compose up -d postgres
docker compose run --rm app alembic upgrade head
docker compose run --rm app alembic check
docker compose run --rm app pytest
```

O schema usa IDs internos, IDs Advbox únicos, valores monetários `NUMERIC`/`Decimal`, timestamps com timezone e estados explícitos de disponibilidade. Payloads brutos não são armazenados. A migration da etapa 8 acrescenta credenciais, sessões, tentativas de login e solicitações de geração no PostgreSQL.

## Estrutura

```text
src/
├── app.py                         entrada compatível com a Vercel
└── partner_reports/
    ├── config.py                  configuração tipada
    ├── main.py                    fábrica da aplicação
    ├── domain/                    regras de negócio
    ├── integrations/advbox/       integração somente leitura
    ├── persistence/               banco e migrations
    ├── reports/                   modelos e renderização HTML/PDF
    ├── jobs/                      sincronização; geração agendada pendente
    └── web/                       rotas, autenticação e templates do portal
tests/                             testes automatizados
```

## Vercel

`src/app.py` expõe a aplicação ASGI reconhecida pelo runtime Python da Vercel. O deploy não usa o Dockerfile. PostgreSQL, PDFs, sessões e jobs deverão usar serviços persistentes externos; o filesystem da função não será usado como armazenamento.

Não publique esta aplicação profissional no plano Hobby/Free. A implantação fica bloqueada até existir plano Vercel adequado, banco externo, armazenamento privado de PDFs e autorização explícita.

## Limites atuais

- a aplicação web não chama o Advbox ao navegar no portal;
- os arquivos servidos localmente são apenas amostras `SYNTHETIC-*` das etapas 7 e 9;
- a fila de regeneração é processada pelo worker local somente para fontes sintéticas; consulte `docs/RUNBOOK.md`;
- o portal não serve PDFs/HTML em produção até haver storage privado e portões aprovados;
- nunca execute carga real integral nem publique a aplicação profissional no plano Hobby/Free.
