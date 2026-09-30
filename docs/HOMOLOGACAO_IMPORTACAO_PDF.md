# Homologação privada da importação PDF — PDF-7

**Data:** 25/09/2026

**Estado:** duas passagens concluídas; GO para iniciar PDF-8

Este documento registra somente métricas agregadas. Nenhum nome de arquivo original, hash, nome de pessoa, número processual, pasta, texto, valor financeiro, credencial ou payload da API foi copiado.

## Autorização e escopo

O responsável autorizou o início do PDF-7 em 25/09/2026. A autorização foi aplicada à primeira passagem privada, estrutural e sem persistência. As fontes foram copiadas para `storage/private` com nomes opacos; a pasta é ignorada pelo Git. Originais fora do repositório não foram alterados.

Após receber o resultado agregado, o responsável aprovou em 25/09/2026: manter os quatro identificadores inválidos como pendências sem vínculo, adotar a política de retenção do ADR-004, executar a segunda passagem persistente e aceitar a prévia interna agregada.

A triagem examinou 11 PDFs disponíveis: sete exportações originais foram aceitas, um arquivo anotado foi recusado com `PDF_ANNOTATED_SOURCE` e três arquivos fora do layout foram recusados com `LAYOUT_UNKNOWN`. Somente as sete exportações originais permaneceram no corpus autorizado.

## Dry-run estrutural e reconciliação GET-only

| Métrica | Resultado |
|---|---:|
| Modo | `pdf7_private_dry_run_no_persistence` |
| Fontes aceitas / fontes únicas | 7 / 7 |
| Páginas | 22 |
| Itens do manifesto | 11 |
| Parser / layout | `advbox-manifest-1` / `advbox-positional-1` |
| Continuações entre páginas | 6 |
| Identificadores fora do padrão aceito | 4 |
| Processos na fotografia oficial | 4.377 |
| Leituras integrais idênticas exigidas | 2 |
| Requisições GET | 88 |
| HTTP 429 / HTTP 5xx / erros de transporte | 0 / 0 / 0 |

| Resultado da reconciliação | Contagem |
|---|---:|
| `matched` | 7 |
| `unmatched` | 0 |
| `ambiguous` | 0 |
| `duplicate_source` | 0 |
| `invalid_identifier` | 4 |
| Total | 11 |

A reconciliação usou somente número processual canônico exato e, quando aplicável, pasta exata única. Os quatro identificadores inválidos não receberam vínculo. Nome, parte, cliente, responsável, texto e similaridade não participaram da decisão.

Uma verificação posterior recusou a fotografia com `ADVBOX_SNAPSHOT_CONTENT_CHANGED`, pois o conteúdo oficial mudou entre as duas leituras integrais. A falha fechada funcionou como projetado: esse resultado não substituiu a fotografia bem sucedida, não produziu reconciliação parcial e reforça a necessidade de repetir a leitura em uma janela estável antes de qualquer passagem persistente.

Em nova tentativa autorizada, duas leituras voltaram a ser idênticas, com as mesmas contagens agregadas. A segunda passagem coletou novamente duas leituras idênticas e usou essa fotografia estável na transação persistente.

O comando instalado para repetir somente esta passagem é:

```text
homologate-pdf --input-dir /caminho/privado
```

A saída contém apenas estado, códigos técnicos e contagens agregadas.

## Persistência e exposição

| Efeito | Contagem |
|---|---:|
| Metadados de fontes gravados no banco | 7 |
| Lotes privados gravados | 7 |
| Reconciliações gravadas | 7 |
| Decisões pendentes gravadas | 4 |
| Vínculos ativos criados | 0 |
| Versões publicadas criadas | 0 |
| Prévias internas agregadas | 1 |

As fontes foram copiadas para o storage local privado ignorado pelo Git. Os lotes usam parceiros técnicos opacos de homologação e permanecem em `needs_review`; não representam cadastro definitivo de parceiros. Não houve associação dos quatro inválidos, publicação, envio ou deploy.

## Inspeção visual privada

As 22 páginas foram renderizadas e inspecionadas em ambiente local. Todas permaneceram A4, legíveis e coerentes com o layout reconhecido. Cabeçalhos, blocos de processo, tabelas e continuações entre páginas ficaram visíveis; nenhum layout desconhecido foi aceito silenciosamente. As imagens temporárias de inspeção foram removidas após a conferência.

A prévia interna agregada também foi renderizada e inspecionada: uma página A4, sete origens opacas, 11 itens, 7 correspondências e 4 pendências. A extração de texto não encontrou padrão processual, CPF/CNPJ, pasta, token ou credencial. O artefato privado não é versão publicável.

## Cinco prioridades do escritório

O resultado abaixo combina a cobertura oficial já auditada com o escopo minimizado aprovado no ADR-004. Não registra valores reais.

| Prioridade | Fonte técnica | Decisão do MVP | Resultado |
|---|---|---|---|
| Parte/cliente | `/lawsuits` + `/customers` | Nome somente interno; nunca chave | Fonte encontrada; sem exposição nesta passagem |
| Ação/benefício | `/lawsuits` + catálogo de `/settings` | Rótulo oficial, sem classificação jurídica própria | Fonte encontrada; sem projeção nesta passagem |
| Fase | fase/etapa oficial | Fase operacional, não status jurídico | Fonte encontrada; sem projeção nesta passagem |
| Financeiro | `/transactions` | Valores e cálculos fora do MVP | Fonte técnica conhecida; conteúdo restrito |
| Andamento | `/last_movements` e endpoints individuais auditados | Texto e relevância fora do MVP | Data/origem estruturada conhecidas; texto restrito |

Registros financeiros internos e a diferença entre último andamento cronológico e andamento relevante permanecem explicitamente restritos, conforme ADR-004.

## Cobertura disponível nesta passagem

O corpus disponível confirmou múltiplas fontes, carteira pequena, identificador inválido e bloco continuado entre páginas. Carteira vazia, carteira grande, reenvio idêntico, PDF substituto, item válido ausente na API e mudança de layout não estavam demonstráveis no conjunto aceito; esses cenários permanecem cobertos apenas pelos testes sintéticos e devem ser reavaliados quando houver exportações originais autorizadas com essas características.

## Critérios e portão

| Critério | Resultado |
|---|---|
| Corpus original privado, textual e versionável | Aprovado |
| Layout conhecido sem aceitação silenciosa | Aprovado |
| Correspondência ambígua ou duplicada | Zero |
| Itens não conciliados | Quatro `invalid_identifier`, explícitos e sem vínculo |
| Vazamento para documento/log/teste versionado | Não observado |
| Persistência privada minimizada | Aprovada e executada |
| Política de retenção P-012/P-019 | Aprovada; implementação produtiva será testada no PDF-8 |
| Fotografia oficial usada na persistência | Duas leituras idênticas |
| Prévia interna agregada | Aprovada e inspecionada |

## Verificações técnicas

- 165 testes aprovados; um aviso de depreciação de dependência, sem falha;
- Ruff lint e formatação aprovados;
- `alembic check` sem deriva e `git diff --check` sem erros;
- auditoria de dependências sem vulnerabilidades conhecidas; o pacote local não publicado no PyPI ficou fora dessa consulta;
- imagem Docker de desenvolvimento reconstruída e entrypoint `homologate-pdf --help` validado;
- arquivos privados ignorados pelo Git e imagens temporárias de inspeção removidas.

**GO:** PDF-7 concluído. Os 11 itens estão reconciliados ou explicitamente pendentes, sem ambiguidade, associação inventada ou publicação. O PDF-8 pode começar pelo staging sintético e pela preparação da VPS.

**NO-GO:** publicação, dados reais na VPS e go-live. Esses atos dependem dos portões próprios do PDF-8/PDF-9, incluindo volumes, HTTPS, firewall, identidade, backup, expiração e restauração comprovados.
