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

## Revisão de 02/10/2026: portal mais simples, claro e com movimento

- **Tema claro (decisão do responsável, 02/10/2026):** no portal, o branco puro `#FFFFFF` substitui o preto como fundo; o texto passa a `#0A0A0A`. O dourado `#F4AA27` continua em botões, menu ativo e preenchimentos (com texto preto) e `#FFC14D` no hover. Texto em dourado sobre branco usa `#8A5A00` por contraste. O relatório HTML/PDF do parceiro mantém a paleta escura até nova decisão.
- **Navegação:** "Relatórios prontos" virou aba própria (`/portal/reports`), ao lado de Início e Envios; o Início não lista mais os prontos.

- **Início:** "Novo relatório" é o cartão principal, com três passos numerados (parceiro, mês, PDF) e área para arrastar o PDF. Abaixo, "Precisa da sua atenção" (pendências e envios em andamento) e, por último, a lista de parceiros com busca na mesma linha do título.
- **Envio:** etapas em círculos ligados por uma linha; a etapa atual pulsa e as concluídas mostram ✓. O cartão de situação tem ícone por tom (processando, atenção, pronto). Nomes longos ficam em até duas linhas.
- **Movimento:** entrada suave dos blocos, brilho dourado lento no fundo, elevação de cartões e botões ao passar o mouse, brilho no botão principal e indicador de envio em andamento. Tudo é CSS, exceto `portal.js` (só realça a área do PDF e mostra o nome do arquivo); sem o script, os formulários funcionam igual. `prefers-reduced-motion` desliga as animações.
- A paleta continua com os quatro tokens; as novas superfícies usam apenas transparências deles. Sem fontes ou scripts externos, compatível com a CSP `default-src 'self'`.
