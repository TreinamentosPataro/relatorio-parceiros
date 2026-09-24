# Validação integral do vínculo parceiro–carteira

**Execução UTC:** 2026-09-15T17:07:34.410664+00:00 a 2026-09-15T17:11:56.553949+00:00  
**Modo:** API somente leitura; nenhum valor de campo ou resposta bruta foi persistido

## Cobertura das coleções

| Recurso | Total | Páginas | IDs duplicados | Campo direto de parceiro |
|---|---:|---:|---:|---:|
| Clientes | 4210 | 43 | 0 | 0 |
| Processos | 4350 | 44 | 0 | 0 |

## Candidatos indiretos

| Medida | Contagem |
|---|---:|
| Clientes com origem | 4210 |
| Clientes sem origem | 0 |
| Origens distintas (valores descartados) | 109 |
| Processos com ao menos uma origem de cliente | 4350 |
| Processos sem origem de cliente | 0 |
| Processos com uma única origem de cliente | 183 |
| Processos com múltiplas origens de clientes | 4167 |
| Processos com pasta preenchida | 4200 |
| Processos com responsável técnico | 4350 |
| Relações processo–cliente | 8957 |
| IDs de cliente relacionados e ausentes da coleção | 21 |

## Validador com mapeamento ainda vazio

| Entidade | Total | Vinculados | Sem vínculo | Múltiplos vínculos |
|---|---:|---:|---:|---:|
| Clientes | 4210 | 0 | 4210 | 0 |
| Processos | 4350 | 0 | 4350 | 0 |

Referências inexistentes no mapeamento: 0.

## Conclusão técnica

A coleção integral não deve ser associada por nome ou texto livre. Origem, pasta e responsável permanecem candidatos sem equivalência funcional aprovada; uma única fotografia da API também não prova estabilidade temporal. Até a carga de um mapeamento governado, todos os registros são classificados explicitamente como `sem vínculo` e nenhum relatório de parceiro pode ser publicado.
