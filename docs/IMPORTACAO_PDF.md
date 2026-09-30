# Ingestão privada de PDF — etapa PDF-1

**Estado:** PDF-1 a PDF-4 implementadas tecnicamente em desenvolvimento/teste com fixtures sintéticas e API falsa. Não há OCR, chamada real ao Advbox no fluxo PDF, revisão real, publicação ou uso autorizado de dados reais.

## Fluxo implementado

1. Somente uma sessão autenticada com papel `portal_admin` acessa `GET /portal/imports/new` e envia `POST /portal/imports/new`. O ADR-004 manteve esse papel como operador do MVP.
2. O formulário exige CSRF, parceiro ativo, início/fim do período e um único arquivo.
3. O servidor descarta o nome original após validar extensão segura. Nome, caminho e conteúdo do arquivo não entram no banco, auditoria ou log.
4. A validação limita o corpo do PDF a 20 MiB, exige assinatura `%PDF-`, MIME `application/pdf`, 1 a 200 páginas A4 retrato e documento não criptografado.
5. A inspeção percorre somente objetos, páginas, geometria e anotações. Ela não chama extração de texto. `/Link` é contado como anotação de layout permitida; qualquer outra anotação, `AcroForm` ou arquivo incorporado produz `PDF_ANNOTATED_SOURCE`.
6. Um SHA-256 detecta reenvio idêntico. A duplicidade aponta para o lote existente, retorna conflito idempotente e não grava um segundo objeto ou lote.
7. Arquivo aceito recebe chave opaca criada pelo servidor, escrita local atômica e metadados PostgreSQL. O lote registra os eventos `uploaded` e `uploaded -> quarantined`; no `private_pilot`, o worker allowlisted passa a reivindicá-lo pela fila durável.
8. A confirmação mostra apenas parceiro, período, páginas, tamanho, UUID do lote e estado. Não existe rota de download do PDF-fonte.

## Storage e atomicidade

`PrivatePdfStorage` é a fronteira para um futuro provedor de objetos privados. `LocalPrivatePdfStorage` existe apenas para `development` e `test`, grava em `PDF_STORAGE_ROOT` (padrão `storage/pdf-imports`) e recusa toda escrita/remoção quando `APP_ENV=production`.

A escrita local usa arquivo temporário, `fsync` e troca atômica. Metadados e auditoria são confirmados em uma transação. Se o banco falha antes do commit, o objeto recém-criado é removido. Uma interrupção abrupta ainda pode deixar um objeto órfão; produção exige volume persistente privado na VPS, rotina de reconciliação, backup externo e política de retenção aprovados em P-014/P-019.

## Persistência

- `pdf_source_documents`: hash, chave opaca, MIME, tamanho, páginas e criação; nunca nome original ou texto.
- `pdf_import_batches`: fonte, parceiro selecionado, período, versão futura de parser/layout, estado, autor, rejeição/substituição e timestamps.
- `pdf_import_events`: histórico append-only de transições com ator e códigos catalogados.
- `pdf_import_reviews`: decisões humanas catalogadas da PDF-4, com campos técnicos de item, método, antes/depois e revisão; somente para ensaio sintético local.

A migration é `20260923_0005`. As transições permitidas ficam centralizadas em `pdf_imports/lifecycle.py` e seguem o contrato. `rejected` e `superseded` são terminais.

## Auditoria e falha segura

As ações permitidas são `pdf_upload_succeeded`, `pdf_upload_rejected`, `pdf_upload_duplicate` e `pdf_upload_failed`. O log contém somente ação, tipo de entidade e UUID de correlação. Motivos de arquivo são códigos fixos; respostas ao navegador são genéricas. Falha do storage não cria lote e não expõe a causa interna.

## Verificação

Fixtures geradas em memória cobrem PDF válido, assinatura falsa, PDF malformado, anotação, link permitido, excesso de tamanho/páginas, página fora de A4, nome/MIME inválido, duplicidade, CSRF, autorização, falha de storage, limpeza e recusa em produção. O PDF real anotado enviado pelo escritório não é fixture e não foi submetido ao endpoint.

## Pendências e próximo portão

- P-018: resolvida no ADR-004; administrador pode executar o fluxo completo com auditoria.
- P-019: política do ADR-004 aprovada após o dry-run PDF-7; expiração e restauração serão comprovadas no PDF-8.
- P-020: resolvida no ADR-004; operação sob demanda, período mensal e carteira completa.
- P-014: volumes privados da VPS, criptografia aplicável, acesso, revogação, backup e restauração.

A etapa PDF-4 implementa a revisão sintética; OCR, extração de texto livre para persistência, publicação e uso produtivo continuam fora do escopo.

## Parser estrutural PDF-2

`parse_pdf_manifest` é isolado e versionado (`advbox-manifest-1`, layout `advbox-positional-1`). Faz novamente a validação estrutural e de anotações, exige camada de texto em todas as páginas, usa fragmentos com posição para reconhecer os blocos de processo/pasta e agrega páginas de continuação. O detector foi confrontado somente em memória com sete PDFs de referência; a inspeção exibiu apenas contagens e códigos e localizou os 11 blocos documentados no contrato. Três números seguiram o padrão CNJ; quatro cabeçalhos com dígitos fora dele receberam `invalid_identifier`. A versão reconhece o padrão posicional observado, não outros formatos.

O resultado contém UUID técnico derivado de hash+versão+ordinal, número processual canônico somente quando reconhecido, pasta exata, ordinal, páginas e flags catalogadas. Nenhum nome, contato, parte, narrativa, título de andamento ou valor financeiro entra no manifesto. Número ausente pode usar pasta exata na reconciliação PDF-3 apenas com unicidade comprovada. Número parcial/inválido, duplicidade, bloco incompleto e carteira vazia exigem revisão. Páginas sem texto, layout desconhecido, fonte anotada e limite excedido produzem códigos fechados, sem texto-fonte.

`parse_quarantined_batch` é a fronteira transacional: lê o objeto privado, verifica SHA-256 e contagem de páginas, persiste apenas `pdf_manifest_items` e contagens sanitizadas e grava transições. A fila adicionada em `20260930_0013` executa essa fronteira e retoma de `parsed` quando a API falha depois do parse, sem duplicar o manifesto.

## Reconciliação PDF-3

O coletor GET-only reutiliza `AdvboxClient` e lê `/lawsuits` em páginas de 100, com limite compartilhado de 20 GET/min e retentativas já testadas. Só guarda em memória ID Advbox, número processual canônico, pasta exata, IDs técnicos de clientes e hash dos campos normalizados. Duas varreduras completas precisam produzir o mesmo digest e total; alteração detectada, ID repetido, página inválida ou coleção incompleta bloqueiam a classificação. `ScanCheckpoint` permite retomar de uma página concluída em memória. Uma interrupção do processo exige iniciar nova varredura; a API de offset não fornece snapshot transacional, portanto igualdade entre duas leituras reduz, mas não elimina, o risco de alteração não observada.

Cada item recebe exatamente um resultado: `matched`, `unmatched`, `ambiguous`, `duplicate_source` ou `invalid_identifier`. Número completo tem precedência; pasta é fallback somente se o número estiver ausente. Conflito entre número e pasta, chave múltipla, duplicidade na origem ou mais de um item apontando ao mesmo ID bloqueiam proposta. Nomes, cliente, parte, responsável e similaridade não são usados. `/customers`, `/transactions` e `/last_movements` podem ser consultados para contagens de cobertura ligadas aos IDs já conciliados; a matriz de campos confirmados e lacunas está em `docs/COBERTURA_API_PDF3.md`.

`dry_run_batch` retorna somente contagens de resultados e não grava banco. `persist_synthetic_reconciliation` mantém o comportamento histórico dos ensaios. Para `private_pilot`, a persistência scoped grava digest, contagens e propostas e materializa somente processos `matched`, com ID Advbox, número canônico, pasta e relações a clientes representados apenas por ID técnico. Candidatos globais não correspondentes e campos como nome, protocolo, grupo, fase e responsável são descartados antes do banco. Repetir digest+parser não duplica resultado; o lote volta a `needs_review` e nenhum `partner_case_links` ativo é criado automaticamente.

## Revisão humana PDF-4 e adaptação ao piloto privado

`/portal/imports` lista lotes com filtro de parceiro, período e estado, horário e contagens; `/portal/imports/{id}` mostra classificações e histórico técnico, sem número/pasta extraídos nem texto livre do PDF. Ambas as rotas exigem `portal_admin`. POSTs de aprovar, rejeitar, solicitar reprocessamento, corrigir e substituir exigem sessão, CSRF, revisão atual do lote e confirmação explícita. A revisão usa bloqueio da linha do parceiro/lote e contador de revisão; formulário antigo retorna conflito. Uma nova reconciliação também incrementa o contador.

`PDF_FOUR_EYES=true` e `PDF_SYNTHETIC_CORRECTIONS=false` continuam como padrões seguros do ambiente sintético existente. O ADR-004 decidiu que o MVP produtivo permitirá autoaprovação administrativa auditada e correção somente por ID técnico existente; a configuração será alinhada no PDF-8. Nomes e justificativas livres não são aceitos. A aprovação continua bloqueada para item duplicado, inválido, sem correspondência ou ambíguo sem correção governada, manifesto incompleto, carteira vazia e processo local ausente.

Aprovação sintética cria vínculos ativos com lote, item, método, hash de evidência, vigência e revisor. Substituição é uma operação única: aprova o novo lote do mesmo parceiro/período, marca o anterior como `superseded` e inativa seus vínculos. Não há versão de relatório nem publicação. Solicitar reprocessamento registra uma decisão auditada ligada à execução de reconciliação exata, sem duplicar o pedido; aprovação e correção ficam bloqueadas até existir nova execução. Nenhuma chamada à API ou worker é disparado nesta etapa. `pdf_import_reviews` e `pdf_import_events` guardam ator, ação/motivo, lote, item, método, IDs técnicos antes/depois e horário, com log externo mínimo e allowlisted. As migrations `20260925_0009/0010` adicionam revisão otimista, histórico técnico, vínculo do pedido à execução e permitem nova vigência de vínculo após inativação do anterior.

P-018/P-022 foram resolvidas no ADR-004. A revisão agora aceita somente parceiros no escopo centralizado: `SYNTHETIC-*` em validação sintética ou IDs exatamente allowlisted em `private_pilot`. Aprovação cria vínculos com proveniência e pode enfileirar versão privada minimizada; não publica relatório nem amplia os campos permitidos. Homologação real e promoção continuam pendentes.
