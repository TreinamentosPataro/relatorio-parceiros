# Comece aqui — novo fluxo por PDF do Advbox

Os prompts completos estão em `PLANO_EXECUCAO_IMPORTACAO_PDF.md`. Este roteiro substitui apenas o caminho bloqueado da etapa 11; as etapas 0 a 10 já construídas continuam válidas.

## Como trabalhar

1. Abra `C:\Users\Henrique Norman\Desktop\pataro\relatorio-parceiros`.
2. Execute um único prompt `PDF-*` por vez.
3. Ao final, confira os critérios de aceite, arquivos alterados, testes e `STATUS_DO_PROJETO.md`.
4. Não avance automaticamente. Se o portão falhar, corrija a mesma etapa.
5. Nunca copie dados reais dos PDFs para código, testes, documentação, logs ou conversa.
6. Mantenha os PDFs reais somente em `storage/private`, fora do Git.
7. A API do Advbox continua GET-only. Não implemente as rotas internas que não foram autorizadas.
8. Leia `docs/PRIORIDADES_CONTEUDO_ESCRITORIO.md`: o PDF marcado em amarelo é evidência de requisitos, não fixture nem arquivo válido de importação.

## Sequência

1. `PROMPT PDF-0`: contrato da importação, ADR e decisões — sem código.
2. `PROMPT PDF-1`: upload privado, storage e modelo do lote.
3. `PROMPT PDF-2`: parser estrutural do PDF textual.
4. `PROMPT PDF-3`: reconciliação com a API oficial.
5. `PROMPT PDF-4`: revisão humana e aprovação no portal.
6. `PROMPT PDF-5`: conteúdo, indicadores e minimização.
7. `PROMPT PDF-6`: geração/versionamento ponta a ponta.
8. `PROMPT PDF-7`: homologação privada com PDFs reais.
9. `PROMPT PDF-8`: infraestrutura e implantação profissional.
10. `PROMPT PDF-9`: go-live assistido.

## Próxima ação

PDF-0 foi concluída documentalmente. Revise e aprove `docs/CONTRATO_IMPORTACAO_PDF.md`, o ADR-002 e as prioridades do escritório; em seguida execute somente o `PROMPT PDF-1 — Ingestão privada, storage e modelo do lote`. PDF-1 não implementa parser, OCR nem chamada real à API.

## Mensagem de revisão entre etapas

```text
Revise criticamente somente a etapa PDF-* que acabou de ser implementada. Leia o git diff e o STATUS_DO_PROJETO.md. Execute todos os testes, lint, migrations e verificações aplicáveis. Compare as evidências com os critérios de aceite do prompt. Não inicie a etapa seguinte. Corrija apenas defeitos da etapa atual. Ao final, informe arquivos alterados, comandos, resultados, riscos restantes e se o portão está APROVADO ou REPROVADO.
```
