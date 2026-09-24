"""Render sanitized audit artifacts; raw response values are not accepted by this module."""

from pathlib import Path

from partner_reports.integrations.advbox.audit import AuditRunResult, ResourceObservation


def _pagination_text(observation: ResourceObservation) -> str:
    pagination = observation.pagination
    if pagination is None:
        return "não detectada na amostra"
    total = "não informado" if pagination.total_count is None else str(pagination.total_count)
    return (
        f"{pagination.style}; total={total}; limit={pagination.limit}; offset={pagination.offset}"
    )


def render_api_audit(result: AuditRunResult) -> str:
    """Build the API audit using metadata only."""

    lines = [
        "# Auditoria segura da API Advbox",
        "",
        f"**Execução UTC:** {result.started_at.isoformat()} a {result.finished_at.isoformat()}  ",
        "**Modo:** somente leitura (`GET`), amostra mínima e sem persistência "
        "de respostas brutas  ",
        "**Teto aplicado:** 20 requisições/minuto, com timeout e retentativa limitada",
        "",
        "## Resultado sanitizado por recurso",
        "",
        "| Recurso | Endpoint | HTTP | Duração (ms) | Itens na amostra | Paginação/erro seguro |",
        "|---|---|---:|---:|---:|---|",
    ]
    for observation in result.observations:
        status = "—" if observation.status_code is None else str(observation.status_code)
        duration = "—" if observation.duration_ms is None else str(observation.duration_ms)
        count = "—" if observation.item_count is None else str(observation.item_count)
        detail = observation.safe_error or _pagination_text(observation)
        lines.append(
            f"| {observation.resource} | `{observation.endpoint_template}` | {status} | "
            f"{duration} | {count} | {detail} |"
        )

    lines.extend(
        [
            "",
            "## Esquema observado",
            "",
            "Somente caminhos de campos, tipos e contagens de nulos são registrados. Valores, "
            "identificadores e conteúdo textual não são gravados.",
        ]
    )
    for observation in result.observations:
        lines.extend(["", f"### {observation.resource}", ""])
        if not observation.fields:
            lines.append("Sem esquema disponível.")
            continue
        lines.extend(
            [
                "| Campo | Tipos | Observações | Nulos |",
                "|---|---|---:|---:|",
            ]
        )
        for field in observation.fields:
            lines.append(
                f"| `{field.path}` | {', '.join(field.types)} | "
                f"{field.observed_count} | {field.null_count} |"
            )
        if observation.id_fields:
            lines.append(f"\nIDs candidatos: {', '.join(f'`{p}`' for p in observation.id_fields)}.")
        if observation.date_fields:
            lines.append(
                f"\nDatas candidatas: {', '.join(f'`{p}`' for p in observation.date_fields)}."
            )
        if observation.partner_candidate_fields:
            lines.append(
                "\nCampos semanticamente candidatos ao vínculo: "
                + ", ".join(f"`{p}`" for p in observation.partner_candidate_fields)
                + "."
            )

    lines.extend(
        [
            "",
            "## Como percorrer coleções",
            "",
            "Quando `data`, `limit`, `offset` e `totalCount` forem observados, percorrer por "
            "`offset += limit` até alcançar `totalCount`, mantendo IDs estáveis e deduplicação. "
            "Esta auditoria não executa a carga integral.",
            "",
            "## Segurança aplicada",
            "",
            "- Nenhum método mutável é exposto pelo auditor.",
            "- Redirecionamentos de login e HTTP 401 são falhas de autenticação.",
            "- HTTP 403/404 são classificados explicitamente; HTTP 429 e 5xx usam "
            "retentativa limitada.",
            "- O relatório não contém token, cabeçalhos, URLs com IDs, valores de campos "
            "ou respostas brutas.",
            "",
        ]
    )
    return "\n".join(lines)


def render_linkage_report(result: AuditRunResult) -> str:
    """Render only technical evidence for the critical linkage gate."""

    lines = [
        "# Vínculo parceiro–carteira no Advbox",
        "",
        f"**Classificação:** {result.linkage_status.value}",
        "",
        "## Evidência técnica sanitizada",
        "",
    ]
    lines.extend(f"- {item}" for item in result.linkage_evidence)
    candidate_rows = [
        (observation.resource, path)
        for observation in result.observations
        for path in observation.partner_candidate_fields
    ]
    if candidate_rows:
        lines.extend(
            [
                "",
                "## Campos candidatos observados",
                "",
                "| Recurso | Caminho do campo |",
                "|---|---|",
            ]
        )
        lines.extend(f"| {resource} | `{path}` |" for resource, path in candidate_rows)
    lines.extend(
        [
            "",
            "## Regra do gate",
            "",
            "Somente um campo direto e tecnicamente estável de parceiro permite classificar o "
            "vínculo como confirmado nesta etapa. Campos de origem, indicação, responsável, tag, "
            "pasta ou carteira são candidatos, não equivalências presumidas. A ausência em amostra "
            "mínima não prova ausência na coleção completa.",
            "",
            "## Próxima ação",
            "",
            "Se a classificação permanecer `INCONCLUSIVO`, não avançar para banco, sincronização "
            "ou portal. Validar o significado do campo candidato com o responsável funcional ou "
            "definir um mapeamento governado na etapa 3.",
            "",
        ]
    )
    return "\n".join(lines)


def write_sanitized_reports(result: AuditRunResult, output_directory: Path) -> None:
    """Atomically replace the two sanitized Markdown audit artifacts."""

    output_directory.mkdir(parents=True, exist_ok=True)
    reports = {
        "ADVBOX_API_AUDIT.md": render_api_audit(result),
        "VINCULO_PARCEIRO_CARTEIRA.md": render_linkage_report(result),
    }
    for filename, content in reports.items():
        target = output_directory / filename
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(target)
