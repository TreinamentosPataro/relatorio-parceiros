# ADR-007 — Relatório completo no formato dos modelos e fluxo simplificado

**Status:** aceita em 01/10/2026 pelo responsável do projeto; regras dos indicadores e do percentual pendentes (F2)
**Altera:** a seção "Conteúdo do MVP" do ADR-004, a matriz `docs/MATRIZ_CONTEUDO_PDF5.md` e o fluxo de telas do portal

## Contexto

No primeiro contato com o portal em produção, o responsável considerou o fluxo confuso para uso diário e esperava um relatório no formato dos modelos que o escritório já envia aos parceiros (dashboards e PDFs analisados em setembro). Pelo ADR-004, o relatório trazia só contagens de clientes, processos e a data do último andamento. A minimização impediu o produto de cumprir a finalidade.

A API pública do Advbox não indica a qual parceiro pertence um processo (auditoria da etapa 11, confirmada pelo suporte). O PDF exportado do módulo Parceiros continua sendo a única fonte da composição da carteira.

## Decisão

1. **Fonte:** o PDF define quais processos pertencem ao parceiro. Todo o conteúdo do relatório vem da API oficial, lido e persistido **somente** para os processos conciliados dessa carteira.
2. **Conteúdo liberado** no portal interno e no relatório gerado:
   - identificação do parceiro, período e data da consulta;
   - indicadores: clientes únicos, processos, benefícios concedidos, em judicial e em financeiro;
   - por processo: nome do cliente, número do processo e pasta, tipo de ação, fase do Advbox, data e título do último andamento;
   - financeiro por processo: lançamentos não internos (descrição/categoria, vencimento, pagamento e valor) e prestação de contas do parceiro.
3. **Continua bloqueado:** CPF completo, contatos, dados de saúde, credenciais, observações e anotações internas, lançamentos `is_internal` e textos de andamento além do título do último andamento.
4. **Uso:** o portal permanece interno. As advogadas (contas `portal_admin` individuais) enviam o PDF, aprovam e geram o relatório; o envio ao parceiro continua manual, fora da plataforma.
5. **Fluxo simplificado (F1):** uma tela "Novo relatório", o andamento do lote em uma página, aprovação e geração em um único botão, "Ver" e "Baixar PDF" na página do parceiro. Telas e termos técnicos saem da frente do usuário; a trilha de auditoria continua. O botão de ação com rótulo explícito ("Aprovar e gerar relatório", "Descartar envio") passa a ser a confirmação exigida pelo ADR-004, no lugar da caixa de seleção; CSRF e revisão atual continuam obrigatórios.

## Pendências desta decisão (F2)

Atualização de 01/10/2026: as regras dos indicadores, o cálculo sobre o valor líquido (imposto de 7,5% e taxas bancárias), as colunas Responsável/Contingenciamento/Valor informado e a troca do status executivo por fase + último andamento foram confirmados (ver `docs/MAPA_MODELO_RELATORIO.md`, seção 5). Continua em aberto apenas a forma de cadastro do percentual da parceria. Registro original das pendências:

- Regras dos indicadores. Proposta: "Benefício concedido" e "Em judicial" a partir de um mapa de fases do Advbox classificado uma vez no portal (com número CNJ como sinal de judicial); "Em financeiro" para processo com honorário de entrada não interno ainda sem pagamento.
- Prestação de contas. Proposta: percentual cadastrado por parceiro sobre os honorários recebidos; lançamentos de saída "Honorários de Parceiros" contam como repasse já pago. Falta decidir se o percentual incide sobre o valor bruto ou líquido de taxas.
- Retenção dos dados financeiros agora persistidos. Proposta: o mesmo prazo da carteira normalizada (12 meses após substituição), a confirmar.

## Consequências

- O relatório passa a conter dados pessoais e financeiros. Os testes de privacidade deixam de exigir ausência de nome e número e passam a garantir a ausência dos campos do item 3.
- O título do último andamento é texto livre e pode conter dado sensível digitado no Advbox. A advogada confere o relatório antes de enviá-lo ao parceiro.
- A leitura da API passa a incluir clientes, últimos andamentos e lançamentos financeiros dos processos da carteira, sempre GET-only, com o limite de 20 GET/min.
