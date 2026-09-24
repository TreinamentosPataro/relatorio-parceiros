# Regras permanentes do projeto

## Antes de alterar

- Leia `PLANO_EXECUCAO_CODEX.md`, `STATUS_DO_PROJETO.md`, os documentos em `docs/` e as análises relevantes à etapa.
- Execute uma etapa por vez e respeite seus portões de decisão.
- Preserve os materiais originais de referência e os artefatos de análise existentes.

## Privacidade e segurança

- Nunca copie para código, testes, documentação ou logs dados pessoais dos arquivos de referência.
- Use somente dados sintéticos em desenvolvimento e testes.
- Nunca imprima ou versione tokens, senhas, cookies, cabeçalhos de autorização, `.env` ou respostas reais integrais.
- Segredos entram somente por variáveis de ambiente ou pelo gerenciador de segredos do ambiente.
- A visão externa usa allowlist explícita. Campos livres, credenciais, CPF completo, contatos, dados de saúde e anotações internas são bloqueados por padrão.
- Logs devem registrar apenas identificadores técnicos opacos, estados, durações e contagens necessárias.

## Advbox

- A integração é somente leitura até autorização explícita em contrário.
- Implemente apenas endpoints e campos confirmados pela auditoria da API.
- Não use métodos diferentes de GET na auditoria e não faça chamadas reais antes da etapa correspondente.
- Respeite paginação, limites, timeout, retry e redaction.

## Arquitetura

- A aplicação é um monólito modular multiparceiro; não especialize funções para um único parceiro.
- Cliente e processo são entidades distintas.
- Ausência, zero, não aplicável, pendente e restrito são estados diferentes.
- Motor de regras, visão interna, visão externa e renderização permanecem desacoplados.
- O alvo de produção é o runtime Python/FastAPI da Vercel. Docker Compose é apenas para desenvolvimento local.
- Não persista banco, PDFs, sessões, jobs ou checkpoints no filesystem da função Vercel.
- Não publique produção no plano Hobby/Free.

## Qualidade e conclusão

- Adicione ou atualize testes proporcionais a cada mudança.
- Execute testes, lint e verificações aplicáveis antes de declarar uma etapa concluída.
- Não alegue que uma verificação passou se ela não foi executada; registre causa e consequência.
- Atualize `STATUS_DO_PROJETO.md` e a documentação de decisões ao concluir cada etapa.
- Não avance automaticamente para a próxima etapa.
