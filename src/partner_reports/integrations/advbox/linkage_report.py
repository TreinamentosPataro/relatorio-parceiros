"""Count-only report for the full partner-linkage audit."""

from pathlib import Path

from partner_reports.integrations.advbox.linkage_audit import FullPortfolioLinkageAudit


def render_full_linkage_audit(result: FullPortfolioLinkageAudit) -> str:
    customers = result.customers
    lawsuits = result.lawsuits
    validation = result.validation_without_mapping
    lines = [
        "# Validação integral do vínculo parceiro–carteira",
        "",
        f"**Execução UTC:** {result.started_at.isoformat()} a {result.finished_at.isoformat()}  ",
        "**Modo:** API somente leitura; nenhum valor de campo ou resposta bruta foi persistido",
        "",
        "## Cobertura das coleções",
        "",
        "| Recurso | Total | Páginas | IDs duplicados | Campo direto de parceiro |",
        "|---|---:|---:|---:|---:|",
        f"| Clientes | {customers.total} | {customers.pages} | "
        f"{customers.duplicate_ids} | {customers.direct_partner_fields} |",
        f"| Processos | {lawsuits.total} | {lawsuits.pages} | "
        f"{lawsuits.duplicate_ids} | {lawsuits.direct_partner_fields} |",
        "",
        "## Candidatos indiretos",
        "",
        "| Medida | Contagem |",
        "|---|---:|",
        f"| Clientes com origem | {customers.with_origin} |",
        f"| Clientes sem origem | {customers.without_origin} |",
        f"| Origens distintas (valores descartados) | {customers.distinct_origins} |",
        f"| Processos com ao menos uma origem de cliente | {lawsuits.with_origin} |",
        f"| Processos sem origem de cliente | {lawsuits.without_origin} |",
        f"| Processos com uma única origem de cliente | {lawsuits.with_one_customer_origin} |",
        f"| Processos com múltiplas origens de clientes | "
        f"{lawsuits.with_multiple_customer_origins} |",
        f"| Processos com pasta preenchida | {lawsuits.with_folder} |",
        f"| Processos com responsável técnico | {lawsuits.with_responsible_id} |",
        f"| Relações processo–cliente | {result.lawsuit_customer_references} |",
        f"| IDs de cliente relacionados e ausentes da coleção | "
        f"{result.lawsuit_customer_references_missing} |",
        "",
        "## Validador com mapeamento ainda vazio",
        "",
        "| Entidade | Total | Vinculados | Sem vínculo | Múltiplos vínculos |",
        "|---|---:|---:|---:|---:|",
        f"| Clientes | {validation.customers.total} | {validation.customers.linked} | "
        f"{validation.customers.unlinked} | {validation.customers.multiple} |",
        f"| Processos | {validation.lawsuits.total} | {validation.lawsuits.linked} | "
        f"{validation.lawsuits.unlinked} | {validation.lawsuits.multiple} |",
        "",
        f"Referências inexistentes no mapeamento: {validation.nonexistent_references}.",
        "",
        "## Conclusão técnica",
        "",
        "A coleção integral não deve ser associada por nome ou texto livre. Origem, pasta e "
        "responsável permanecem candidatos sem equivalência funcional aprovada; uma única "
        "fotografia da API também não prova estabilidade temporal. Até a carga de um mapeamento "
        "governado, todos os registros são classificados explicitamente como `sem vínculo` e "
        "nenhum relatório de parceiro pode ser publicado.",
        "",
    ]
    return "\n".join(lines)


def write_full_linkage_audit(result: FullPortfolioLinkageAudit, output: Path) -> None:
    content = render_full_linkage_audit(result)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(output)
