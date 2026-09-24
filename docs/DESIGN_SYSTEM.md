# Identidade visual da plataforma

**Definição do responsável:** 16/09/2026. Esta paleta orienta o relatório e o portal interno de prévia sintética.

| Papel | Cor | Aplicação |
|---|---|---|
| Dourado | `#F4AA27` | Títulos de seção, acentos, links, botão principal, foco visível e indicadores destacados |
| Dourado hover | `#FFC14D` | Exclusivamente o estado de passar o mouse sobre o botão principal |
| Preto | `#0A0A0A` | Fundo da plataforma e do PDF |
| Texto | `#EDEDED` | Texto do corpo e conteúdo principal |

Superfícies, divisórias e metadados secundários podem usar **transparências dessas mesmas cores** sobre o fundo preto; não introduzir outra cor opaca como identidade. O texto principal mantém `#EDEDED` e o dourado nunca substitui o texto corrido. O botão principal usa fundo `#F4AA27` com texto `#0A0A0A`; no hover, somente o fundo/borda muda para `#FFC14D`. Links permanecem `#F4AA27` também no hover, com sublinhado mais forte. Foco de teclado recebe contorno dourado independente do hover.

## Componentes e hierarquia

- Fundo e cabeçalho pretos; o dourado marca seções e elementos de navegação sem preencher grandes áreas.
- Cartões e painéis usam transparência dourada discreta e borda dourada; valores confirmados recebem destaque dourado.
- Tabelas usam cabeçalho dourado sobre superfície escura; linhas alternadas usam apenas uma transparência do texto claro.
- Estados pendentes usam dourado e rótulo textual. Cor sozinha não comunica status; ausência não vira zero.
- Em telas estreitas, cartões empilham e cada linha de processo vira um cartão com rótulos explícitos. O PDF mantém a tabela com cabeçalho repetido.
- A versão impressa preserva o fundo preto, o texto claro e o dourado, inclusive no rodapé. Isso consome mais tinta; uma alternativa clara para impressão precisaria de aprovação específica.

## Implementação e portão

Os tokens estão em `src/partner_reports/reports/assets/report.css` e `src/partner_reports/web/assets/portal.css`. HTML/PDF sintéticos e portal interno reutilizam exatamente os quatro tokens. Login, lista e detalhe foram inspecionados em 1280 e 375 px, sem rolagem horizontal; hover e foco de botão foram testados. Esta decisão visual não libera dados reais nem substitui os portões de autenticação, privacidade e implantação.
