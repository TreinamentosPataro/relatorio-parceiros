# ADR-005 — Liberação gradual de parceiros reais no piloto

**Status:** aceita em 30/09/2026
**Substitui:** a allowlist por variável de ambiente de D-049 (o escopo `private_pilot` e o comportamento fail-closed permanecem)

## Contexto

D-049 admitia parceiros reais somente por `PDF_PILOT_PARTNER_IDS`, uma lista fixa de identificadores na configuração. O responsável decidiu testar com a carteira de parceiros do escritório, cerca de dez, liberados aos poucos, em vez de um único parceiro piloto. Com a lista fixa, cada nova liberação exigiria editar um arquivo protegido na VPS e reiniciar a aplicação. Também não existia um fluxo para cadastrar parceiros reais: apenas o seed sintético e os parceiros técnicos inativos da homologação PDF-7.

## Decisão

- Parceiros reais são cadastrados no portal, em **Gerenciar parceiros**, por um usuário `portal_admin`, e somente quando `PDF_DATA_SCOPE=private_pilot`. Em `synthetic_only` a página não existe.
- O código técnico (`PRT-` seguido de 10 dígitos hexadecimais) é gerado aleatoriamente e não deriva do nome nem de identificador do Advbox. O nome é de uso interno.
- Um parceiro entra no escopo somente com `partners.pilot_enabled = true`, que é falso por padrão. Parceiros `SYNTHETIC-*` nunca entram no escopo real, mesmo com a marcação.
- Liberar e suspender exigem CSRF e confirmação explícita, e registram `partner_pilot_enabled` ou `partner_pilot_disabled` na auditoria. O cadastro registra `partner_created`.
- Suspender retira o parceiro do catálogo, do upload, da revisão, do worker e da geração, sem apagar lotes, versões ou auditoria.
- A regra de escopo fica em um único módulo (`partner_reports.partner_scope`), usado pelo portal, worker, revisão, reconciliação e geração.
- `PDF_PILOT_PARTNER_IDS` foi aposentada. Se ainda estiver preenchida, a aplicação recusa iniciar, para que uma configuração antiga não seja ignorada em silêncio.

## Consequências

- A ampliação do piloto passa a ser uma decisão operacional auditada, sem nova implantação.
- O plano recomendava não ampliar para toda a carteira antes de aceitar o primeiro ciclo. O responsável aceitou esse risco de forma consciente; a liberação gradual por parceiro é a mitigação adotada.
- O limite de concorrência do worker continua unitário (KVM 1). Liberar muitos parceiros ao mesmo tempo aumenta a fila, não o paralelismo.
