# PDF-6 — geração privada a partir de lote aprovado

**Escopo atual:** desenvolvimento/teste com parceiros sintéticos ou exatamente allowlisted em `private_pilot`. `validated` significa prévia privada tecnicamente completa, não autorização de publicação externa. `publication_ready` continua falso.

## Entrada e revisão

O adaptador `pdf_imports.reporting` exige lote `approved`, parser versionado, fotografia de reconciliação verificada no mesmo dia do fim do período, manifesto/classificações completos, vínculos ativos revisados e correspondência entre item, vínculo e processo normalizado. Relações cliente–processo e datas de movimentos vêm das tabelas normalizadas. A consulta seleciona IDs, estados, vínculos e datas; não carrega nome de cliente, número processual, valor/categoria financeira nem título do movimento para compor o relatório. Conflito, lacuna ou dado normalizado posterior à fotografia impede a prévia.

A chave SHA-256 de revisão combina parceiro, início/fim do período, SHA-256 do PDF-fonte, versão do parser, SHA-256 da fotografia da API e versão das regras (`portfolio_snapshot_v1`). O PDF-fonte fornece somente a composição. A versão guarda a chave de revisão e `pdf_batch_id`; a migration `20260925_0011` também vincula a solicitação de geração ao lote e impede duas versões do mesmo parceiro com a mesma revisão de lote.

## Job, acesso e recuperação

O administrador solicita geração no detalhe do lote aprovado ou pela ação de regenerar o parceiro. O worker usa a fila/lease existente, valida novamente o escopo, monta `InternalReportViewModel`, passa pela allowlist externa, gera HTML e PDF e grava os dois objetos privados antes de inserir uma versão `validated` em transação. Chaves sintéticas e privadas usam namespaces distintos. O commit reconfere lote, revisão e lease; falha remove os objetos da tentativa quando possível e preserva a versão anterior. O digest do par HTML/PDF é verificado no download.

O portal mostra versão, período, horário, origem genérica e pendência das regras, sem chave de storage nem PDF-fonte. HTML/PDF exigem sessão e conferência de parceiro/versão; apenas relatório gerado é baixável. A restauração administrativa aceita também versões `private_pilot` dentro da allowlist exata, exige CSRF e confirmação, verifica o hash conjunto dos artefatos e registra auditoria. Esta liberação foi validada somente no ambiente local com dados sintéticos.

## Hierarquia de conteúdo após aprovação

O relatório atual mostra somente panorama, qualidade, carteira pseudonimizada e metodologia. Quando P-006/P-007/P-023 forem decididas, a ordem proposta é: identificação da parte/cliente com papel definido, tipo de ação/benefício, fase operacional separada de status jurídico, bloco financeiro por processo com segregação de registros internos e andamento cronológico/relevante com política de texto. Cada seção deverá receber contrato interno e externo próprios, fonte, versão de regra, estado de ausência e testes antes de aparecer. Esta proposta não acrescenta campos nem valores aos templates atuais.

## Limites

- A fotografia PDF-3 comprova a coleção de processos, mas ainda não constitui contrato produtivo de completude de clientes, relações e movimentos. `source_complete=True` neste adaptador é restrito ao ensaio sintético; dados reais permanecem bloqueados.
- O período só é aceito quando a fotografia verificada cai no dia final do lote. Carteira vazia tem prévia visual sintética, mas a revisão PDF-4 ainda não aprova manifesto vazio sem regra humana específica.
- Em `private_pilot`, artefatos usam o volume privado configurado e chaves `private/generated/*`; o backend nunca publica o diretório diretamente. Retenção e backup continuam aplicáveis.
- A versão `validated` não deve ser tratada como relatório publicável. Nenhuma chamada real à API, PDF real, envio ou implantação integra esta etapa.
