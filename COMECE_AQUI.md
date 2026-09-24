# Comece aqui — construção da plataforma no Codex

> **Mudança de estratégia em 23/09/2026:** a Advbox não autorizará o uso automatizado das rotas internas de parceiros. A continuidade passa pelo PDF exportado manualmente no Advbox. Use `COMECE_AQUI_IMPORTACAO_PDF.md` e `PLANO_EXECUCAO_IMPORTACAO_PDF.md`. O roteiro abaixo permanece como histórico das etapas 0 a 10 já concluídas.

Este arquivo é o roteiro curto. Os prompts completos estão em `PLANO_EXECUCAO_CODEX.md`.

## Forma de trabalho

1. Trabalhe sempre em `C:\Users\Henrique Norman\Desktop\pataro\relatorio-parceiros`.
2. Execute um prompt por vez.
3. Ao final de cada prompt, confira arquivos alterados, testes executados, limitações e `STATUS_DO_PROJETO.md`.
4. Se um critério de aceite falhar, peça a correção na mesma tarefa antes de avançar.
5. Não envie token do Advbox pela conversa.
6. Não permita operações de escrita no Advbox.
7. Não comece pelo design do PDF. Primeiro prove dados, vínculo e regras.

## Ciclo 1 — Preparar o projeto

### Passo 1

Execute o **PROMPT 0** do plano.

Resultado esperado:

- inventário da hospedagem;
- decisões e pendências registradas;
- status do projeto;
- nenhuma implementação ainda.

Depois, preencha as informações conhecidas da hospedagem. O mínimo para o próximo ciclo é saber sistema operacional, disponibilidade de Docker, PostgreSQL, domínio/HTTPS, espaço em disco e backup.

### Passo 2

Execute o **PROMPT 1**.

Resultado esperado:

- projeto Python/FastAPI organizado;
- `AGENTS.md` com regras permanentes;
- `.gitignore` protegendo `.env`;
- configuração tipada;
- `/health` funcionando;
- testes iniciais passando.

Ao terminar o Prompt 1, uma nova tarefa do Codex aberta na raiz do projeto carregará automaticamente o `AGENTS.md`. Na tarefa atual, os prompts seguintes também mandam lê-lo explicitamente.

## Ciclo 2 — Provar o acesso aos dados

### Passo 3

Somente depois de confirmar que `.env` está no `.gitignore`, crie o `.env` local a partir de `.env.example` e adicione o token do Advbox fora da conversa. Não versionar, imprimir ou incluir o token em captura de tela.

### Passo 4

Execute o **PROMPT 2**.

Resultado esperado:

- autenticação confirmada;
- endpoints realmente disponíveis para a conta;
- paginação e limites conhecidos;
- inventário sanitizado dos campos;
- conclusão `CONFIRMADO`, `AUSENTE` ou `INCONCLUSIVO` para o vínculo parceiro–carteira.

Não prossiga para banco ou PDF enquanto o vínculo estiver inconclusivo.

### Passo 5

Execute o **PROMPT 3**.

Resultado esperado:

- regra determinística de vínculo;
- identificador técnico estável;
- relatório de itens vinculados, sem vínculo e ambíguos;
- alternativa de mapeamento administrativo caso a API não exponha parceiro diretamente.

## Ciclo 3 — Construir o núcleo

Quando o vínculo estiver resolvido, execute na ordem:

1. **PROMPT 4:** banco, migrations e contratos flexíveis;
2. **PROMPT 5:** sincronização multiparceiro idempotente;
3. **PROMPT 6:** indicadores e visões interna/externa;
4. **PROMPT 7:** HTML e PDF condicionais.

Antes do Prompt 6, o escritório precisa definir os significados de:

- clientes únicos e processos;
- benefício concedido;
- em financeiro;
- em judicial;
- regra de status executivo;
- regra de parceria, taxas, impostos e arredondamento.

Sem uma regra aprovada, o sistema deve marcar o indicador como pendente e não inventar um cálculo.

## Ciclo 4 — Transformar o núcleo em produto

Execute na ordem:

1. **PROMPT 8:** portal interno multiparceiro;
2. **PROMPT 9:** jobs e atualização automática;
3. **PROMPT 10:** segurança, LGPD e isolamento;
4. **PROMPT 11:** carga e homologação de todos os parceiros;
5. **PROMPT 12:** implantação na hospedagem existente;
6. **PROMPT 13:** operação assistida e aceite.

## Regra para aprovação de cada etapa

Use esta mensagem quando uma etapa terminar e você quiser uma conferência antes de avançar:

```text
Revise criticamente a etapa que acabou de ser implementada. Leia o git diff e o STATUS_DO_PROJETO.md. Execute todos os testes, lint e verificações aplicáveis. Compare os resultados com os critérios de aceite do prompt executado. Não faça a próxima etapa. Corrija somente defeitos da etapa atual. Ao final, informe: arquivos alterados, comandos executados, resultados, riscos restantes e se o portão está APROVADO ou REPROVADO, citando evidências.
```

## Primeiro comando

Comece agora pelo `PROMPT 0 — Diagnóstico do ambiente e preparação do trabalho`, disponível em `PLANO_EXECUCAO_CODEX.md`.
