# Ingestão privada de PDF — etapa PDF-1

**Estado:** implementada e verificada somente em desenvolvimento/teste com PDFs sintéticos. Não há parser, OCR, chamada ao Advbox, reconciliação, revisão, publicação ou uso autorizado de dados reais.

## Fluxo implementado

1. Somente uma sessão autenticada com papel `portal_admin` acessa `GET /portal/imports/new` e envia `POST /portal/imports/new`. Esse é o padrão seguro temporário enquanto P-018 estiver pendente.
2. O formulário exige CSRF, parceiro ativo, início/fim do período e um único arquivo.
3. O servidor descarta o nome original após validar extensão segura. Nome, caminho e conteúdo do arquivo não entram no banco, auditoria ou log.
4. A validação limita o corpo do PDF a 20 MiB, exige assinatura `%PDF-`, MIME `application/pdf`, 1 a 200 páginas A4 retrato e documento não criptografado.
5. A inspeção percorre somente objetos, páginas, geometria e anotações. Ela não chama extração de texto. `/Link` é contado como anotação de layout permitida; qualquer outra anotação, `AcroForm` ou arquivo incorporado produz `PDF_ANNOTATED_SOURCE`.
6. Um SHA-256 detecta reenvio idêntico. A duplicidade aponta para o lote existente, retorna conflito idempotente e não grava um segundo objeto ou lote.
7. Arquivo aceito recebe chave opaca criada pelo servidor, escrita local atômica e metadados PostgreSQL. O lote registra os eventos `uploaded` e `uploaded -> quarantined`; permanece em `quarantined` até a futura etapa PDF-2.
8. A confirmação mostra apenas parceiro, período, páginas, tamanho, UUID do lote e estado. Não existe rota de download do PDF-fonte.

## Storage e atomicidade

`PrivatePdfStorage` é a fronteira para um futuro provedor de objetos privados. `LocalPrivatePdfStorage` existe apenas para `development` e `test`, grava em `PDF_STORAGE_ROOT` (padrão `storage/pdf-imports`) e recusa toda escrita/remoção quando `APP_ENV=production`.

A escrita local usa arquivo temporário, `fsync` e troca atômica. Metadados e auditoria são confirmados em uma transação. Se o banco falha antes do commit, o objeto recém-criado é removido. Uma interrupção abrupta entre sistemas ainda pode deixar um objeto órfão; produção exige storage externo, rotina de reconciliação e política de retenção aprovados em P-014/P-019.

## Persistência

- `pdf_source_documents`: hash, chave opaca, MIME, tamanho, páginas e criação; nunca nome original ou texto.
- `pdf_import_batches`: fonte, parceiro selecionado, período, versão futura de parser/layout, estado, autor, rejeição/substituição e timestamps.
- `pdf_import_events`: histórico append-only de transições com ator e códigos catalogados.
- `pdf_import_reviews`: estrutura reservada para decisões humanas catalogadas da PDF-4; nenhuma revisão/publicação foi habilitada.

A migration é `20260923_0005`. As transições permitidas ficam centralizadas em `pdf_imports/lifecycle.py` e seguem o contrato. `rejected` e `superseded` são terminais.

## Auditoria e falha segura

As ações permitidas são `pdf_upload_succeeded`, `pdf_upload_rejected`, `pdf_upload_duplicate` e `pdf_upload_failed`. O log contém somente ação, tipo de entidade e UUID de correlação. Motivos de arquivo são códigos fixos; respostas ao navegador são genéricas. Falha do storage não cria lote e não expõe a causa interna.

## Verificação

Fixtures geradas em memória cobrem PDF válido, assinatura falsa, PDF malformado, anotação, link permitido, excesso de tamanho/páginas, página fora de A4, nome/MIME inválido, duplicidade, CSRF, autorização, falha de storage, limpeza e recusa em produção. O PDF real anotado enviado pelo escritório não é fixture e não foi submetido ao endpoint.

## Pendências e próximo portão

- P-018: papéis definitivos de upload/revisão/publicação e eventual regra de quatro olhos.
- P-019: retenção/eliminação do PDF-fonte e objetos rejeitados/órfãos.
- P-020: periodicidade e filtros obrigatórios da exportação.
- P-014: provedor privado de produção, criptografia, acesso, revogação e restauração.

A próxima ação técnica é somente PDF-2: parser estrutural versionado sobre fixtures sintéticas, mantendo extração livre, OCR, API real e publicação fora do escopo até seus portões.
