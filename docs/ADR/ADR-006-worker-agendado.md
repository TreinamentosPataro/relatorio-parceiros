# ADR-006 — Worker agendado na VPS

**Status:** aceita em 30/09/2026
**Altera:** o "processamento manual no MVP" previsto no prompt PDF-8

## Contexto

Na VPS, o worker só rodava por comando manual (`work-once`, perfil `operations`) executado pelo operador com `sudo`. O responsável quer testar em cenário real, com duas advogadas usando o portal como se a ferramenta estivesse pronta. Com processamento manual, um PDF enviado ficaria parado até alguém acessar o servidor, o que não representa o uso real e depende do operador único.

## Decisão

- A unidade `partner-reports-worker.service` (`oneshot`) executa `automation_cli drain` no serviço `worker` do Compose. Cada execução processa até 10 itens: primeiro a fila de importações PDF, depois a de relatórios, sempre limitadas ao escopo de dados configurado.
- O `partner-reports-worker.timer` dispara 1 minuto depois do término da execução anterior (`OnUnitInactiveSec`), e nunca por horário fixo. Assim nunca há duas execuções simultâneas, mesmo quando uma fotografia GET-only demora vários minutos pelo limite de 20 GET/min.
- O timeout da unidade é de 45 minutos. Lease, heartbeat, três tentativas e recuperação de abandono do worker continuam valendo.
- O token do Advbox continua carregado somente pelo serviço `worker`, a partir de `deploy/advbox.env`.
- O script de promoção pausa o timer do worker durante a troca, recusa promover com o worker em execução e reativa o timer ao final ou no rollback.
- A instalação é separada e explícita (`ops/install-worker-timer.sh`), como a do backup.

## Consequências

- O fluxo upload → processamento → revisão → geração deixa de depender de acesso ao servidor.
- A cada minuto sobe um contêiner de curta duração. No KVM 1 isso é aceitável para o volume do piloto, e o uso de CPU e memória deve ser acompanhado na conferência diária.
- Em `private_pilot`, a ausência do token faz a unidade falhar a cada execução, e a falha aparece no `systemctl --failed` da conferência diária.
