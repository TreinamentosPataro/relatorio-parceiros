FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN groupadd --system app && useradd --system --gid app --create-home app

COPY pyproject.toml README.md ./
COPY src ./src
COPY alembic.ini ./
COPY migrations ./migrations
RUN python -m pip install --no-cache-dir --upgrade "pip>=26.2,<27" \
    && python -m pip install --no-cache-dir .

FROM base AS development

COPY tests ./tests
RUN python -m pip install --no-cache-dir ".[dev]"
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN python -m playwright install --with-deps chromium \
    && chmod -R a+rX /ms-playwright

USER app
EXPOSE 8000
CMD ["uvicorn", "app:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000", "--reload", "--no-access-log"]

FROM base AS production

USER app
EXPOSE 8000
CMD ["uvicorn", "app:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
