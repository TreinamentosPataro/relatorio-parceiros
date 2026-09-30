# Relatório HTML/PDF — etapa 7

**Estado:** prévia técnica com dados exclusivamente sintéticos. Não existe rota pública, armazenamento de PDF, envio nem autorização de publicação real.

## Fluxo e layout

`InternalReportViewModel` → projeção externa com allowlist → template Jinja2 autoescapado + CSS local → HTML responsivo → Chromium/Playwright → PDF A4 em memória. HTML e PDF usam o mesmo `ReportViewModel`. O gerador retorna bytes; o chamador futuro terá de usar volume persistente privado e controle de acesso, sem gravar na camada efêmera do contêiner.

O cabeçalho mostra código técnico do parceiro, período, atualização e versão. O corpo traz resumo e cartões de clientes únicos/processos distintos, alertas de qualidade, tabela de casos com referências pseudonimizadas e data do último registro cronológico, e metodologia/fonte/corte. O HTML oferece detalhes recolhíveis e associação cliente–processo para carteiras pequenas. Na impressão a associação separada é omitida porque a própria tabela contém o vínculo; detalhes recolhíveis também não entram no PDF. O status executivo permanece “Em revisão”, sem inferência jurídica. A seção financeira permanece bloqueada no portão PDF-5, mesmo que um valor sintético declare fonte `approved_financial_rule`: P-006/P-007 ainda não foram aprovadas. Distribuições e KPIs jurídicos continuam ausentes ou marcados como pendentes até aprovação formal de regras/categorias.

O CSS usa fontes do sistema, não carrega CDN ou recurso remoto, adapta a largura de tela e possui regras A4 de impressão. A identidade preto/dourado/texto claro está registrada em `docs/DESIGN_SYSTEM.md`; em telas estreitas, processos viram cartões rotulados, enquanto no PDF os cabeçalhos de tabela se repetem e linhas não devem ser partidas entre páginas. O Chromium aborta requisições externas na geração do PDF.

## Portão de privacidade

- O template nunca recebe o modelo interno. A projeção permite apenas os campos tipados do modelo externo e rejeita publicação (`publication_ready=false`).
- Nesta fase, origem, versão da regra e referências de cliente/processo devem corresponder aos valores controlados pelo construtor; texto livre não classificado é rejeitado. Status executivo, distribuições e KPIs jurídicos disponíveis sem aprovação também são rejeitados.
- Padrões de CPF, CNPJ, número processual completo, segredo, token, dado de saúde e HTML/script ativo são bloqueados antes do template. Autoescape é uma segunda barreira.
- Nenhum nome, contato, documento pessoal, observação livre ou texto de andamento é campo da visão externa. A data do último andamento não equivale a conclusão ou relevância jurídica.
- PDF-5 revalida os objetos aninhados antes da projeção para impedir valores forjados por cópia de modelo; confere proveniência e concordância das contagens e referências, exige a fonte oficial da data cronológica e bloqueia data de andamento relevante e valor financeiro enquanto faltarem as regras. A matriz campo a campo está em `docs/MATRIZ_CONTEUDO_PDF5.md`.
- Essas barreiras não substituem P-006/P-007, homologação de negócio, revisão de segurança e testes com políticas de acesso antes de dados reais.

## Amostras e validação

Com Docker ativo, na raiz do projeto:

```text
docker compose run --rm app python -m partner_reports.reports.preview_cli --output-root output
docker compose run --rm app pytest -q tests/test_report_render.py
```

As amostras ficam em `output/html/` e `output/pdf/`: `preview_zero`, `preview_one` e `preview_many` (0, 1 e 55 casos sintéticos). Capturas de tela da paleta em desktop e celular ficam em `output/preview/`. Em 16/09/2026, as páginas PDF finais foram renderizadas e inspecionadas: A4, respectivamente 1, 1 e 3 páginas; sem corte de linha/tabela, título órfão ou página quase vazia. A suíte cobre HTML condicional, isolamento de IDs internos, rejeição de padrões sensíveis e texto não classificado, escape, portão financeiro, geração Chromium, cores calculadas no navegador e ausência de rolagem horizontal nas larguras de 375 e 1280 px.

## Limitações e próximos portões

- PDF-6 acrescentou adaptador e versionamento apenas para lotes sintéticos aprovados, com download autenticado pelo portal. Não há adaptador de geração para dados reais, matriz P-006/P-007/P-023 aprovada ou publicação.
- O navegador foi instalado apenas na imagem local de desenvolvimento. Compatibilidade, tamanho, memória e duração de Chromium na VPS ainda exigem medição; a imagem de produção não comprova esse cenário.
- Volumes privados produtivos, backup e implementação da retenção aprovada continuam pendentes. O versionamento e a rota autenticada atuais usam somente artefatos locais sintéticos; nenhum PDF deve ser disponibilizado fora do ambiente de desenvolvimento antes desses portões. O fluxo PDF-6 está documentado em `docs/RELATORIO_PDF6.md`.
- A aparência dos dados sintéticos não valida o conteúdo jurídico/financeiro de um relatório real.
