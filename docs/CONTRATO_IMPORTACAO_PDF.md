# Contrato de importação do PDF de carteira

**Versão:** 1.1  
**Data:** 23/09/2026  
**Estado:** contrato arquitetural da etapa PDF-0; nenhuma ingestão, extração, persistência ou interface foi implementada

## Finalidade e limites

O lote representa a composição da carteira de **um parceiro** em **um período ou data de corte**. O operador exporta manualmente o documento no módulo Parceiros do Advbox, seleciona na plataforma o parceiro e o período correspondentes e envia o PDF. O documento-fonte é privado, serve como manifesto de pertencimento e nunca é republicado como relatório.

Este contrato não autoriza upload produtivo, parser, OCR, chamada real à API, persistência, publicação ou correção manual de dados. A implementação ocorrerá nas etapas posteriores do plano e usará somente fixtures sintéticas até autorização específica.

## Evidência estrutural disponível

A inspeção somente leitura e sanitizada cobriu sete PDFs de referência produzidos pelo mesmo gerador, sem registrar nomes de arquivo, texto, identificadores, hashes ou dados pessoais:

- todos são A4 e possuem camada de texto em todas as páginas;
- há dois documentos de 1 página, um de 2 páginas, dois de 4 páginas e dois de 5 páginas, totalizando 22 páginas;
- os documentos multipágina repetem uma região de cabeçalho estrutural;
- aparecem marcadores recorrentes de processo, pasta, cliente, partes e andamentos;
- não foi detectada estrutura tabular nativa confiável;
- existem páginas de continuação sem novo marcador de início, portanto um bloco de processo pode atravessar a quebra de página.

Essas observações autorizam apenas o desenho de um parser estrutural posicional. Elas não provam estabilidade futura do layout. Cada layout deverá ter detector e versão próprios; formato desconhecido falha fechado.

### PDF anotado como evidência de requisitos

Um PDF adicional de 55 páginas foi analisado porque o escritório marcou em amarelo as informações que considera prioritárias. Foram observadas 13 anotações nas páginas 1, 2 e 4, classificadas somente por categoria: identificação da parte/cliente, tipo de ação/benefício, fase, detalhe financeiro, marcador de registro interno e andamento manual recente. Nenhum valor foi transcrito.

Esse arquivo é um artefato privado de requisitos e não amplia o manifesto. Cor e anotação nunca participam do parser nem da correspondência. Como o arquivo foi editado depois da exportação, ele não é uma entrada válida para o fluxo produtivo nem pode virar fixture. As prioridades e perguntas decorrentes estão em `docs/PRIORIDADES_CONTEUDO_ESCRITORIO.md`.

## Formato aceito no MVP

Um arquivo é elegível somente se cumprir todos os itens abaixo:

| Regra | Critério testável |
|---|---|
| Contêiner | PDF real, com assinatura `%PDF-`, extensão `.pdf` e MIME compatível; extensão isolada não basta |
| Proteção | Não criptografado, sem senha e legível pela biblioteca homologada |
| Tamanho | Maior que zero e no máximo 20 MiB |
| Páginas | Entre 1 e 200 páginas, todas A4 retrato; largura e altura podem variar no máximo 5 pontos tipográficos em relação a 595,28 × 841,89 pt |
| Texto | `extract_text().strip()` não vazio em todas as páginas e marcadores estruturais reconhecidos; documento integral ou parcialmente escaneado é recusado |
| Origem | Exportação manual do módulo Parceiros do Advbox, sem edição posterior |
| Escopo | Um único parceiro e um único período/data de corte por arquivo |
| Layout | Versão reconhecida pelo detector; cabeçalho repetido e quebras de página devem poder ser descartados/agregados deterministicamente |
| Identificação | Cada item deve possuir número processual reconhecível ou pasta; item sem ambos vai para revisão e não pode ser associado automaticamente |

Os limites de 20 MiB e 200 páginas são limites técnicos iniciais e deverão ser configuráveis, testados nas bordas e revistos na homologação. A primeira versão não executa OCR nem tenta recuperar documento corrompido.

## Pré-condições da exportação e do envio

Antes do envio, o operador deve:

1. entrar no módulo Parceiros do Advbox com sua própria autorização;
2. selecionar exatamente um parceiro;
3. aplicar o período/data de corte e os filtros obrigatórios aprovados em P-020;
4. conferir na interface que o parceiro e o período escolhidos correspondem ao lote que será criado;
5. exportar diretamente para PDF, sem imprimir, combinar, recortar, anotar ou converter o arquivo;
6. não renomear o parceiro com base no conteúdo do documento: o vínculo é sempre o parceiro técnico selecionado no upload;
7. enviar o arquivo uma única vez e tratar um reenvio idêntico como duplicidade, não como nova fotografia;
8. manter o arquivo somente em local privado autorizado até a política de retenção P-019 ser aprovada.

Enquanto periodicidade e filtros estiverem pendentes, o lote pode ser usado apenas em desenvolvimento/homologação autorizada e não possui promessa de completude ou atualização.

## Fontes, autoridade e precedência

| Fonte | Papel autorizado | Não pode fazer |
|---|---|---|
| PDF exportado | Comprovar quais processos compõem a carteira escolhida naquele período/corte; fornecer número processual e/ou pasta somente para reconciliação | Fornecer dados estruturados finais, mudar o parceiro selecionado, publicar texto livre ou expandir a carteira por inferência |
| API oficial Advbox GET-only | Fornecer os dados estruturados de processos, clientes, andamentos e transações para itens reconciliados | Incluir na carteira item ausente do PDF ou usar rota interna não autorizada |
| Entrada manual governada | Definir regras aprovadas e versionadas, decisões de revisão por catálogo e metadados operacionais indispensáveis | Digitar nomes/valores para completar a origem, criar correspondência por texto livre ou substituir silenciosamente PDF/API |

A precedência é por finalidade, não por sobreposição genérica:

1. **composição da carteira:** PDF;
2. **dados estruturados do item:** API oficial;
3. **fórmulas, allowlists e tratamento de exceções:** regras manuais previamente aprovadas e versionadas.

Uma divergência entre fontes gera código de qualidade e `needs_review`. Não há sobrescrita silenciosa. Nome de parceiro, cliente, parte, advogado, responsável, origem ou qualquer texto livre nunca participa da chave.

## Identidade e metadados mínimos do lote

O modelo a ser implementado deverá representar, no mínimo:

| Grupo | Campos mínimos |
|---|---|
| Identidade | `batch_id`, `source_document_id`, `partner_id` técnico selecionado |
| Competência | `period_start`, `period_end` e/ou `as_of`, conforme procedimento aprovado |
| Proveniência | `uploaded_by`, `uploaded_at`, `source_sha256`, `byte_size`, `page_count` |
| Processamento | `state`, `parser_version`, `layout_version`, `created_at`, `updated_at` |
| Reconciliação | identificador da fotografia da API, contagens por resultado e instante da reconciliação |
| Decisão | revisor/publicador quando aplicável, instante, código de motivo e lote substituído/substituto |

O nome original, caminho local, texto integral extraído, valores de cabeçalho e conteúdo livre não são metadados permitidos em logs ou auditoria.

## Manifesto mínimo por item

Cada item extraído possui somente os campos allowlisted necessários ao vínculo:

| Campo | Regra |
|---|---|
| `manifest_item_id` | UUID interno opaco |
| `source_ordinal` | Ordem determinística do bloco no documento |
| `process_number_normalized` | Opcional; forma canônica validada, sem pontuação/espaços |
| `folder_exact` | Opcional; usado apenas quando o número está ausente |
| `source_page_start` / `source_page_end` | Intervalo de páginas do bloco, inclusive quando atravessa página |
| `quality_flags` | Códigos de catálogo, sem texto livre |
| `match_status` | `matched`, `unmatched`, `ambiguous`, `duplicate_source` ou `invalid_identifier` |
| `match_method` | `process_number_exact`, `folder_exact_unique` ou nulo |
| `matched_lawsuit_id` | ID técnico interno/Advbox somente quando a correspondência for única |

Ao menos um entre número processual e pasta deve existir para tentativa automática. O texto integral extraído existe, no máximo, em memória durante o parse e não integra o manifesto.

## Regras de correspondência

1. Normalizar número processual somente por uma função versionada que remova formatação permitida e valide o formato esperado. Comparar por igualdade exata com a API.
2. Se houver exatamente um processo para o número normalizado, classificar `matched` com método `process_number_exact`.
3. Zero candidatos resulta em `unmatched`; mais de um, em `ambiguous`.
4. Usar pasta somente quando o número estiver ausente. A normalização conservadora limita-se a Unicode NFC e remoção de espaços externos; não há aproximação, correção ortográfica ou comparação por nome.
5. Pasta com exatamente um candidato comprovado resulta em `matched` com método `folder_exact_unique`; zero resulta em `unmatched`; mais de um, em `ambiguous`.
6. Número e pasta conflitantes, identificador inválido, bloco incompleto ou item repetido não são resolvidos por precedência silenciosa: vão para revisão.
7. O mesmo item da origem não pode criar dois vínculos; duplicidade no PDF é `duplicate_source`.
8. Cada item termina em exatamente um resultado. Só `matched` produz proposta de vínculo ao parceiro selecionado.
9. Nomes e similaridade textual são proibidos e deverão ter testes negativos explícitos.

## Estados e transições do lote

| Estado | Significado |
|---|---|
| `uploaded` | Objeto e metadados mínimos recebidos atomicamente; ainda não confiável |
| `quarantined` | Em validação de tipo, limites, duplicidade e segurança |
| `parsing` | Parser versionado processando o PDF reconhecido |
| `parsed` | Manifesto determinístico produzido, ainda sem reconciliação completa |
| `reconciling` | Itens sendo comparados à fotografia da API oficial |
| `needs_review` | Há exceção, divergência, carteira vazia ou decisão humana pendente |
| `approved` | Composição reconciliada e decisão auditada; não implica publicação |
| `rejected` | Lote recusado por motivo catalogado e terminal |
| `failed` | Falha técnica sanitizada, retomável somente por ação explícita |
| `superseded` | Lote substituído por outro lote aprovado para o mesmo escopo |

Transições permitidas:

```text
uploaded -> quarantined
quarantined -> parsing | rejected | failed
parsing -> parsed | needs_review | rejected | failed
parsed -> reconciling | needs_review
reconciling -> approved | needs_review | failed
needs_review -> reconciling | approved | rejected | superseded
failed -> quarantined
approved -> superseded
```

Qualquer outra transição é inválida. `rejected` e `superseded` são terminais. Reprocessamento preserva documento, hash, versão anterior, eventos e autoria; não reescreve histórico.

## Rejeição e encaminhamento para revisão

Rejeições usam códigos fixos, sem nome de arquivo ou conteúdo:

| Código | Condição |
|---|---|
| `FILE_EMPTY` | Zero bytes |
| `FILE_NOT_PDF` | Extensão/MIME/assinatura incompatíveis |
| `PDF_MALFORMED` | Estrutura ilegível ou corrompida |
| `PDF_ENCRYPTED` | Criptografia ou senha |
| `SIZE_LIMIT_EXCEEDED` | Mais de 20 MiB |
| `PAGE_LIMIT_EXCEEDED` | Mais de 200 páginas |
| `PAGE_FORMAT_UNSUPPORTED` | Página fora do formato aceito |
| `TEXT_LAYER_REQUIRED` | Uma ou mais páginas sem camada de texto utilizável |
| `LAYOUT_UNKNOWN` | Detector não reconhece a versão estrutural |
| `PARSER_LIMIT_EXCEEDED` | Limite de tempo/memória/complexidade atingido |
| `SOURCE_SCOPE_INVALID` | Arquivo não comprova um único escopo parceiro/período conforme os filtros aprovados |
| `PDF_ANNOTATED_SOURCE` | O arquivo contém destaque, comentário, texto, carimbo, anexo ou formulário acrescentado após a exportação; links previstos pelo layout podem ser tratados separadamente |

Não são rejeições automáticas, mas obrigam `needs_review`: zero itens, item sem número e pasta, bloco incompleto, duplicidade, identificador inválido, ausência ou multiplicidade na API, conflito entre número e pasta, divergência de contagem e alerta de quebra de página não resolvido. Reenvio com o mesmo SHA-256 é tratado como duplicidade idempotente e aponta para o lote existente; não cria uma segunda carteira.

## Critérios de revisão e aprovação

Um lote só pode ficar `approved` quando:

- o arquivo passou por todas as validações e o parser/layout estão versionados;
- todo item foi classificado exatamente uma vez;
- não existe `ambiguous`, `duplicate_source`, `invalid_identifier`, bloco incompleto ou divergência sem resolução governada;
- cada item elegível possui correspondência única, ou a carteira vazia foi confirmada contra a exportação e os filtros por revisor autorizado;
- parceiro, período, hash, versão do parser, fotografia da API, contagens e decisão estão auditados;
- qualquer decisão humana usa ação e motivo de catálogo aprovados, sem texto livre nem fabricação de dado;
- a separação de funções definida em P-018 foi respeitada. Enquanto pendente, somente administrador local pode revisar e nenhuma publicação é permitida.

Itens `unmatched` não são ligados manualmente por nome. O tratamento seguro é corrigir a origem/reexportar ou aplicar uma regra de exceção previamente aprovada em P-022, sempre por ID técnico existente e com auditoria.

## Critérios adicionais para publicação

`approved` não significa `publication_ready`. Publicação exige também:

1. lote aprovado e não substituído;
2. fotografia da API completa e reprodutível;
3. zero pendência/ambiguidade de vínculo;
4. matriz de campos internos/externos aprovada em P-007;
5. fórmulas, período, fonte e responsável dos indicadores aprovados em P-006;
6. papel de publicação e regra de quatro olhos aprovados em P-018;
7. retenção, storage privado, identidade, isolamento e auditoria produtivos homologados;
8. relatório derivado exclusivamente da allowlist; PDF-fonte, nomes, contatos, documentos completos, saúde, credenciais, observações e texto livre permanecem bloqueados.

Enquanto qualquer item estiver pendente, a saída permanece interna e `publication_ready=false`.

## Decisões humanas ainda necessárias

| ID | Pergunta objetiva | Bloqueia |
|---|---|---|
| P-018 | Quais papéis podem enviar, revisar e publicar? O autor pode revisar/publicar o próprio lote ou haverá quatro olhos? | Fluxo real de revisão/publicação (PDF-4) |
| P-019 | Por quanto tempo PDF-fonte, manifesto, auditoria e backups serão retidos e como serão eliminados? | Homologação persistente e produção (PDF-7/8) |
| P-020 | Qual periodicidade, período/data de corte e conjunto exato de filtros o operador deve aplicar na exportação? | Comparabilidade e aceite de lote real |
| P-007 | Quais campos entram nas visões interna e externa, com finalidade, retenção e responsável? | Conteúdo publicável (PDF-5) |
| P-006 | Quais fórmulas, fontes, intervalos, exceções, arredondamentos e proprietários definem cada indicador? | Indicadores/financeiro (PDF-5) |
| P-022 | Qual tratamento catalogado é permitido para item sem número, pasta ausente/não única e divergência PDF-API? | Aprovação de exceções reais (PDF-3/4) |
| P-023 | Como as cinco prioridades do escritório se dividem entre visão interna/externa, qual sua semântica e qual papel pode acessá-las? | Matriz de conteúdo e relatório (PDF-5/6) |

## Critérios de teste das próximas etapas

- Os limites de bytes/páginas e cada código de rejeição terão testes sintéticos de borda.
- O mesmo PDF e versão do parser deverão produzir o mesmo manifesto e as mesmas páginas de origem.
- Fixtures cobrirão 0, 1 e muitos itens, bloco entre páginas, cabeçalho repetido, número ausente, duplicidade e layout desconhecido.
- Fixtures sintéticas cobrirão arquivo com anotação e provarão que cor/destaque nunca altera o manifesto; fonte anotada será recusada com `PDF_ANNOTATED_SOURCE`.
- A reconciliação cobrirá correspondência única/ausente/múltipla e provará, por teste negativo, que nome e similaridade nunca são usados.
- Logs, auditoria e erros serão inspecionados para garantir ausência de texto extraído, nome original, número processual, pasta e dados pessoais.

## Próximo portão

Submeter este contrato e o ADR-002 à aprovação dos responsáveis e responder, no mínimo, P-018, P-019 e P-020 no momento em que cada uma bloquear a trilha. Após o aceite do contrato, a próxima etapa técnica é exclusivamente PDF-1: ingestão privada, storage e modelo do lote, ainda sem parser, OCR ou chamada à API.
