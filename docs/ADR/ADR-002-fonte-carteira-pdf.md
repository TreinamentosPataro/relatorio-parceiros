# ADR-002 — PDF como fonte da composição da carteira

- **Status:** aceito
- **Data:** 23/09/2026
- **Escopo:** origem do vínculo parceiro–processo no fluxo revisado de importação
- **Substitui:** a alternativa condicional de automatizar rotas internas registrada em D-029
- **Preserva:** IDs estáveis, vigência, auditoria e rejeição de ambiguidade definidos no ADR-001

## Contexto

A API oficial GET-only fornece dados estruturados dos processos, mas não informa a qual parceiro cada processo compartilhado pertence. A interface do módulo Parceiros demonstrou uma relação técnica, porém suas rotas são internas, dependem de sessão/CSRF, não possuem contrato público e não serão autorizadas pela Advbox para automação.

O operador já consegue exportar manualmente um PDF por parceiro. A inspeção sanitizada de sete arquivos de referência confirmou PDF A4 textual, cabeçalho estrutural repetido, marcadores recorrentes e blocos que podem atravessar páginas, sem tabela nativa confiável. O arquivo pode, portanto, atuar como manifesto privado da carteira, desde que um parser versionado falhe fechado e a API oficial continue responsável pelos dados estruturados.

## Forças de decisão

- respeitar a autorização e o contrato do fornecedor;
- não usar nome nem texto livre como chave;
- obter composição determinística por parceiro;
- manter os dados estruturados na API oficial;
- permitir auditoria, revisão, substituição e reprodução por lote;
- minimizar digitação, vazamento e acoplamento a layout não documentado;
- não antecipar OCR, scraping ou publicação de dados reais.

## Alternativas consideradas

| Alternativa | Autorização/estabilidade | Determinismo e auditoria | Esforço/risco operacional | Decisão |
|---|---|---|---|---|
| Rota interna não autorizada | Contrato inexistente; autorização negada; sessão/CSRF e layout podem mudar | IDs técnicos seriam úteis, mas a coleta dependeria de interface privada | Alto risco contratual e de segurança; exigiria manter automação de sessão | Rejeitada; não será implementada |
| CSV manual | Formato estruturado e simples de validar, porém não existe exportação oficial confirmada para esse vínculo | Bom se houver schema e IDs estáveis governados | Exigiria montagem/transformação manual e criaria uma segunda fonte sujeita a erro | Não escolhida; poderá ser reavaliada somente se o Advbox oferecer exportação oficial governada |
| PDF como manifesto | Exportação manual disponível no módulo autorizado; layout não é API e exige versionamento | Determinístico para composição quando número/pasta são extraídos e reconciliados; arquivo/hash sustentam evidência | Esforço moderado de exportação e revisão; risco de mudança de layout tratado por falha fechada | **Escolhida** |
| Digitação manual | Independe de formato técnico | Baixa escala, propensa a omissão/transposição e difícil reconciliação | Alto custo recorrente e maior tratamento de dados pessoais | Rejeitada como fonte da carteira; entrada manual limita-se a regras/decisões aprovadas |

## Decisão

Adotar o PDF exportado manualmente do módulo Parceiros como prova da **composição da carteira** de um parceiro e período. O operador seleciona o parceiro por ID técnico no upload; qualquer nome dentro do PDF é apenas conteúdo e nunca cria ou altera o vínculo.

A precedência fica dividida por responsabilidade:

1. o **PDF** determina quais itens pertencem à carteira;
2. a **API oficial Advbox GET-only** fornece os dados estruturados dos itens reconciliados;
3. **entradas manuais** fornecem somente regras e decisões previamente aprovadas, versionadas e auditadas.

A reconciliação usa primeiro número processual normalizado exato. Somente na ausência do número pode usar pasta exata com unicidade comprovada. Nome de parceiro, cliente, parte, advogado, responsável, origem, similaridade ou texto livre são proibidos como chave.

O PDF-fonte é um objeto privado de entrada, nunca uma saída publicável. A primeira versão aceita apenas camada de texto e layout reconhecido; OCR fica fora do escopo. Ambiguidade, ausência de correspondência ou divergência não são resolvidas silenciosamente e encaminham o lote para revisão.

## Consequências positivas

- Elimina a dependência de rotas internas não autorizadas.
- Preserva a API oficial como fonte dos dados estruturados e reduz o conteúdo extraído do PDF ao manifesto mínimo.
- Mantém evidência reproduzível por hash, versão do parser, páginas de origem e fotografia da API.
- Permite detectar duplicidade, substituição e mudança de layout.
- Torna explícita a etapa manual que já existe, automatizando o fluxo somente depois do upload.
- Mantém o modelo governado do ADR-001: vínculo por ID técnico, vigência, fonte, status e auditoria.

## Consequências negativas e riscos

- O operador precisa exportar e enviar um arquivo por parceiro/período.
- A qualidade depende de periodicidade e filtros padronizados.
- Mudança de layout exige nova versão/detector e homologação; formato desconhecido será recusado.
- O PDF pode conter dados além do necessário, exigindo storage privado, retenção própria e processamento em memória do texto.
- Número processual pode faltar e pasta pode não ser única; exceções exigem revisão ou reexportação.
- O PDF comprova a carteira no corte informado, não atualização em tempo real.
- A publicação continua bloqueada até aprovação de papéis, retenção, conteúdo externo e indicadores.

## Relação com o ADR-001

O ADR-001 continua válido quanto ao modelo normalizado de vínculo, IDs estáveis, vigência, auditoria e bloqueio de múltiplos vínculos. Ficam superadas suas expectativas operacionais de obter a carga inicial por CSV genérico ou administração livre: a fonte primária da composição passa a ser `pdf_manifest`, reconciliada com IDs da API. Correção manual não pode usar nomes nem fabricar valores; somente regras/exceções aprovadas poderão atuar sobre IDs técnicos existentes.

## Controles obrigatórios decorrentes

1. Validar assinatura, MIME, tamanho, páginas, criptografia, camada de texto e versão de layout antes de extrair.
2. Calcular SHA-256, detectar reenvio idêntico e manter storage privado fora do filesystem persistente da Vercel.
3. Persistir apenas manifesto allowlisted e métricas sanitizadas; texto integral fica no máximo em memória.
4. Versionar parser/layout e registrar páginas de origem para cada item.
5. Falhar fechado para scan, OCR, layout desconhecido, bloco incompleto e limite excedido.
6. Classificar todo item em resultado exclusivo e bloquear vínculo/publicação com ambiguidade.
7. Separar aprovação do lote de autorização de publicação.
8. Usar somente dados sintéticos em código e testes; arquivos reais ficam privados e entram apenas em homologação autorizada.

## Decisões pendentes

- P-018: papéis de upload, revisão e publicação e eventual regra de quatro olhos;
- P-019: retenção/eliminação de PDF, manifesto, auditoria e backups;
- P-020: periodicidade, período/corte e filtros obrigatórios da exportação;
- P-006/P-007: regras dos indicadores e matriz de campos internos/externos;
- P-022: catálogo de tratamento de exceções de identificadores e divergências.

## Critério para reconsiderar

Reavaliar esta decisão somente se o Advbox oferecer e autorizar uma fonte oficial de composição por parceiro com IDs estáveis, contrato documentado e condições operacionais homologáveis. Uma fonte oficial futura deverá ser reconciliada com os lotes existentes; não autoriza migração silenciosa nem associação por nome.
