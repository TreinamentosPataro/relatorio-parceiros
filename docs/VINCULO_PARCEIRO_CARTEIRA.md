# Vínculo parceiro–carteira no Advbox

**Classificação:** INCONCLUSIVO

## Evidência técnica sanitizada

- A amostra estrutural não expôs campo direto partner/parceiro.
- Amostragem mínima não prova ausência em toda a carteira nem unicidade do vínculo.

## Campos candidatos observados

| Recurso | Caminho do campo |
|---|---|
| settings | `origins` |
| settings | `origins[]` |
| settings | `origins[].id` |
| settings | `origins[].origin` |
| settings | `stages` |
| settings | `stages[]` |
| settings | `stages[].id` |
| settings | `stages[].stage` |
| settings | `stages[].step` |
| customers | `data[].origin` |
| lawsuits | `data[].customers[].origin` |
| lawsuits | `data[].folder` |
| lawsuits | `data[].responsible` |
| lawsuits | `data[].responsible_id` |
| lawsuits | `data[].stage` |
| lawsuits | `data[].stages_id` |
| transactions | `data[].responsible` |
| history | `data[].responsible` |

## Regra do gate

Somente um campo direto e tecnicamente estável de parceiro permite classificar o vínculo como confirmado nesta etapa. Campos de origem, indicação, responsável, tag, pasta ou carteira são candidatos, não equivalências presumidas. A ausência em amostra mínima não prova ausência na coleção completa.

## Próxima ação

Se a classificação permanecer `INCONCLUSIVO`, não avançar para banco, sincronização ou portal. Validar o significado do campo candidato com o responsável funcional ou definir um mapeamento governado na etapa 3.
