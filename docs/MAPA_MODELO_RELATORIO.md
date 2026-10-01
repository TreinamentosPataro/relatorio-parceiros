# Mapa do modelo de relatório para a API (F2)

**Data:** 01/10/2026
**Estado:** proposta para confirmação do responsável; base para a F3 (ADR-007)
**Fontes:** estrutura dos 7 dashboards e PDFs de setembro (lidos só localmente; nenhum nome, valor ou identificador foi copiado), fórmulas das abas financeiras e uma leitura GET única de `/settings` em 01/10/2026 (somente catálogos de fases, tipos de ação e categorias financeiras).

## 1. Estrutura do modelo atual

Cada dashboard tem três abas:

| Aba | Conteúdo |
|---|---|
| Resumo do parceiro | Título, data-base do relatório Advbox; cartões **Total de clientes**, **Benefícios concedidos**, **Em financeiro**, **Em judicial**; bloco "Financeiro do parceiro": cliente com financeiro detalhado, recebido pelo parceiro (entrada), a receber pelo parceiro (parcelas futuras), total do parceiro (recebido + a receber) e receita do escritório registrada |
| Clientes | Uma linha por processo: Cliente, Pasta, Ação/benefício, Fase atual, Status executivo, Responsável, Contingenciamento, Valor informado, Status resumido |
| Financeiro (prestação de contas) | Por parcela: Tipo da parcela, Valor pago, Taxa de boleto, Taxa de imposto, Valor líquido, % parceria, Valor líquido a pagar; total da parceria, valores já pagos ao parceiro e saldo |

As fórmulas dos modelos que têm prestação de contas são:

- `Valor líquido = Valor pago − Taxa de boleto − Taxa de imposto`, com **imposto = 7,5% do valor pago**;
- `Valor a pagar ao parceiro = Valor líquido × % parceria`;
- `Saldo = Total da parceria − valores já pagos ao parceiro`.

O percentual incide sobre o **valor líquido**. O "Total de clientes" estava quebrado (`#REF!`) em cinco dos sete modelos, e os cartões de indicadores eram digitados à mão.

## 2. Origem de cada campo na API

| Campo do modelo | Origem oficial | Observação |
|---|---|---|
| Cliente | `/lawsuits[].customers[]` → `/customers` (nome) | Um processo pode ter mais de um cliente; todos são listados |
| Pasta | `/lawsuits[].folder` | |
| Número do processo | `/lawsuits[].process_number` | Também usado na conferência com o PDF |
| Ação/benefício | `/lawsuits[].type` (`type_lawsuit_id` → catálogo `lawsuit_types`) | |
| Fase atual | `/lawsuits[].stage` e etapa `step` | Catálogo de 56 fases em 7 etapas, ver seção 4 |
| Status executivo / resumido | Último andamento: `/last_movements` (data e título) | O modelo usava texto manual; o relatório passa a mostrar a fase e o último andamento oficial |
| Responsável | `/lawsuits[].responsible` | Integrante da equipe |
| Contingenciamento | `/lawsuits[].contingency` | Nulo na amostra da auditoria; ausência aparece como "não informado" |
| Valor informado | `/lawsuits[].fees_expec` | Nulo na amostra da auditoria; ausência não vira zero |
| Lançamentos financeiros | `/transactions` com `lawsuit_id` do processo, `is_internal = false` | Categoria, vencimento, pagamento, valor e tipo de entrada/saída |

## 3. Regras propostas

### Indicadores

Os cartões continuam podendo se sobrepor, como nos modelos (um processo pode estar "Em judicial", com "Benefício concedido" e "Em financeiro").

| Indicador | Regra proposta |
|---|---|
| Total de clientes | Clientes distintos dos processos da carteira |
| Processos | Processos distintos da carteira (novo cartão; o modelo contava linhas) |
| Em judicial | Etapa atual `JUDICIAL`, `RECURSAL` ou `EXECUÇÃO/COBRANÇA` |
| Benefício concedido | Fase atual em `EXECUÇÃO/COBRANÇA` ou `AGUARDANDO PAGAMENTO DOS HONORÁRIOS` / `HONORÁRIOS QUITADOS` (etapa `RH/FINANCEIRO`) |
| Em financeiro | Fase `AGUARDANDO PAGAMENTO DOS HONORÁRIOS` **ou** honorário de entrada não interno ainda sem pagamento |

A classificação vem de um **mapa de fases** guardado no banco e editável no portal. A tabela da seção 4 é a proposta inicial. Fase nova criada no Advbox aparece como "não classificada" até alguém marcar.

### Prestação de contas do parceiro

- **Entradas do processo:** lançamentos de entrada não internos das categorias de honorários (`HONORÁRIOS INICIAIS`, `HONORÁRIOS FINAIS`, `HONORÁRIOS POR MENSALIDADE`, `HONORÁRIO ADVOCATÍCIO*`, `RPVS`, `HONORÁRIOS DE SUCUMBÊNCIA`).
- **Taxa de boleto:** lançamentos `TAXAS BANCÁRIAS` do mesmo processo.
- **Imposto:** 7,5% do valor pago, percentual configurável por versão de regra.
- **Valor líquido:** valor pago − taxas − imposto.
- **Valor do parceiro:** valor líquido × percentual da parceria, cadastrado por parceiro (10%, 20%…), com possibilidade de exceção por processo.
- **Recebido pelo parceiro:** saídas da categoria `HONORÁRIOS DE PARCEIROS` do processo.
- **A receber pelo parceiro:** parcelas de honorários com vencimento futuro × percentual sobre o líquido estimado.
- **Saldo:** valor do parceiro sobre o que já foi pago − recebido pelo parceiro.
- **Receita do escritório:** valor líquido − valor do parceiro.

## 4. Mapa inicial de fases (configuração do escritório)

| Etapa (`step`) | Fases | Classificação proposta |
|---|---|---|
| MARKETING, NEGOCIAÇÃO | Análise de resultados; Relacionamento; Venda em andamento; Aguardando fechamento | Fora dos indicadores |
| CONSULTORIA | 25%, 50%, 75% aguardando documentos; 100% aguardando petição; Diagnóstico previdenciário; Aguardando preencher requisito | Administrativo |
| ADMINISTRATIVO | Parecer jurídico; Setor de provas; Aguardando distribuição; Requerimento protocolado/aguardando decisão; Recurso administrativo protocolado/aguardando decisão; Plano de ação executado/não executado | Administrativo |
| JUDICIAL | Aguardando distribuição da ação; Ação protocolada; Aguardando perícia, audiência, julgamento, sentença; Sentença proferida; Desenvolvendo recurso; Trânsito em julgado/finalizado | Em judicial |
| RECURSAL | Aguardando protocolo/julgamento do recurso; Recurso protocolado; Recurso julgado; Trânsito em julgado | Em judicial |
| EXECUÇÃO/COBRANÇA | Elaboração de cálculo; Aguardando decisão do tribunal, emissão de RPV, implantação da decisão, pagamento de condenação, penhora, julgamento/sentença de liquidação; RPV emitido; Citação; Execução julgada; Recurso/resposta | Em judicial + Benefício concedido |
| RH/FINANCEIRO | Aguardando pagamento dos honorários | Benefício concedido + Em financeiro |
| RH/FINANCEIRO | Honorários quitados | Benefício concedido |
| RH/FINANCEIRO | Venda concluída (à vista/recorrente) | Fora dos indicadores (consultoria vendida) |
| ARQUIVAMENTO | Analisado e não distribuído; Arquivado por determinação judicial; Arquivado/encerrado; Arquivado por desinteresse | Arquivado |

## 5. Pontos para confirmação

1. As regras dos três indicadores (seção 3) e o mapa de fases (seção 4).
2. Imposto fixo de 7,5% sobre o valor pago, e taxas bancárias descontadas antes do percentual.
3. Percentual por parceiro com exceção por processo; os modelos tinham parceiro com mais de um percentual.
4. Exibir "Responsável", "Contingenciamento" e "Valor informado", que estavam no modelo.
5. "Status executivo" substituído por fase oficial + último andamento (data e título).
