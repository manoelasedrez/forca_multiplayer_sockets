# Regras das salas — Forca Multiplayer

Planejamento do item 8. Complementa [regras.md](regras.md) (seções 2.3, 3.2, 3.5, 4.3, 4.4 e 4.11).

Os nomes de operações e de códigos de erro usados aqui (`CRIAR_SALA`, `SALA_CHEIA` etc.) são **provisórios**. Os nomes e formatos definitivos serão fixados na especificação do protocolo.

## Visão geral

### Estados de uma sala

| Estado | Significado | Entrada de novos jogadores | Início de partida |
| --- | --- | --- | --- |
| `AGUARDANDO` | Sala criada, nenhuma partida disputada ainda | Permitida | Permitida (responsável, com 2 ou mais jogadores) |
| `EM_PARTIDA` | Partida em andamento | **Recusada** | Recusada |
| `ENCERRADA` | A última partida terminou (normal ou interrompida); o placar final continua visível | Permitida | Permitida (responsável, com 2 ou mais jogadores) |

Transições:
- `AGUARDANDO` → `EM_PARTIDA`: o responsável inicia a partida.
- `EM_PARTIDA` → `ENCERRADA`: fim da quinta rodada, ou interrupção por restar um só jogador (sem vencedor).
- `ENCERRADA` → `EM_PARTIDA`: o responsável inicia nova partida (8.9).
- Qualquer estado → removida: quando o último jogador sai (8.8).

### Informações guardadas por sala

Além das listadas em [regras.md](regras.md) 2.3: código, estado, lista de participantes em ordem de entrada e motivo do encerramento da última partida (`NORMAL` ou `INTERROMPIDA`).

**Invariante:** o responsável da sala é sempre o primeiro da lista de participantes. Isso simplifica a regra de 8.7.

### Limites (constantes configuráveis no servidor)

| Constante | Valor | Seção |
| --- | ---: | --- |
| Jogadores por sala | 2 a 6 | [regras.md](regras.md) 3.2 |
| `MAX_SALAS_POR_JOGADOR` | 5 | 8.11 |
| `MAX_SALAS_SERVIDOR` | 50 | 8.11 |
| Tamanho do código | 4 caracteres | 8.1 |

## 8.1. Criação da sala e código

- O jogador (já identificado por apelido) envia `CRIAR_SALA`. Não há parâmetros nesta versão (sem nome, senha ou categoria).
- O servidor gera um **código de 4 caracteres** tirados de `ABCDEFGHJKMNPQRSTUVWXYZ23456789` (sem `I`, `L`, `O`, `0` e `1`, que se confundem). São 31⁴ = 923.521 combinações.
- O código é único entre as salas existentes e **não é reaproveitado** enquanto o servidor estiver em execução, para que um código antigo nunca leve a uma sala diferente.
- O código é aceito sem diferenciar maiúsculas de minúsculas, e espaços nas pontas são removidos.
- Quem cria entra automaticamente na sala, passa a ser o responsável (primeiro da ordem) e a sala nasce em `AGUARDANDO`.
- A resposta traz o código; o criador o repassa aos outros jogadores por outro meio (a aplicação não tem chat).
- Não há lista pública de salas: **só se entra por código**. Quem não conhece o código não encontra a sala.
- Se o limite do jogador (8.11) ou do servidor (8.11) estiver esgotado, a criação é recusada.

## 8.2. Consulta das salas do jogador

- Operação `LISTAR_SALAS`, sem parâmetros: devolve apenas as salas **das quais o jogador participa**.
- Cada item traz: código, estado, número da rodada, participantes (com marca do responsável), jogador da vez, segundos restantes do turno e pontuação do próprio jogador. O que o cliente exibe está em [multiplas-salas.md](multiplas-salas.md), 9.4.
- Fora essa consulta, o servidor envia eventos sempre que algo relevante muda em uma sala do jogador, então a lista permanece atualizada sem consultas repetidas.
- Sem salas, a resposta é uma lista vazia (não é erro).

## 8.3. Entrar e sair

**Entrar** (`ENTRAR_SALA` com o código):
1. O jogador passa a ser o último da ordem de entrada.
2. Todos os participantes recebem o evento de entrada.
3. O novo jogador recebe o estado atual da sala.

Entrar em uma sala em que já se está é recusado (`JA_NA_SALA`), sem efeito.

**Sair** (`SAIR_SALA` com o código; ou perda da conexão):
- Fora de partida (`AGUARDANDO` ou `ENCERRADA`): o jogador é removido e os demais são avisados.
- Em partida: o jogador é removido da sala e **não pode voltar enquanto a partida durar** (a sala recusa entradas). Os pontos que acumulou **deixam de contar**: ele não aparece no placar final nem pode vencer. O cliente pede confirmação antes de enviar a saída durante uma partida.
  - Se era a vez dele, a vez passa imediatamente ao próximo, sem perda de pontos nem erro acrescentado.
  - Restando 2 ou mais jogadores, a partida segue. A ordem relativa dos demais é preservada e a próxima rodada começa conforme [regras.md](regras.md) 4.4.
  - Restando 1 jogador, a partida é interrompida: estado `ENCERRADA`, motivo `INTERROMPIDA`, sem vencedor ([regras.md](regras.md) 3.2 e 4.11).
- **Desconexão** (cliente fechou, cabo desconectado, erro de comunicação) equivale a sair de **todas** as salas do jogador, cada uma tratada pelas regras acima. Não há recuperação de sessão nesta versão ([regras.md](regras.md) 3.5).

## 8.4. Tentativa de entrar em sala inexistente, cheia ou já iniciada

As verificações ocorrem nesta ordem; a primeira que falhar define a resposta, e **nenhuma recusa altera o estado de nenhuma sala**.

| Ordem | Condição | Código | Mensagem sugerida ao jogador |
| ---: | --- | --- | --- |
| 1 | Código fora do formato (tamanho ou caracteres) | `CODIGO_INVALIDO` | "Código inválido. Use 4 caracteres, como K7XP." |
| 2 | Não existe sala com o código | `SALA_INEXISTENTE` | "Não existe sala com o código K7XP. Confira o código." |
| 3 | O jogador já está na sala | `JA_NA_SALA` | "Você já está na sala K7XP." |
| 4 | Sala em `EM_PARTIDA` | `PARTIDA_EM_ANDAMENTO` | "A sala K7XP está em partida. Tente novamente quando ela terminar." |
| 5 | Sala com 6 jogadores | `SALA_CHEIA` | "A sala K7XP está cheia (6 de 6)." |
| 6 | O jogador já participa de `MAX_SALAS_POR_JOGADOR` salas | `LIMITE_SALAS_JOGADOR` | "Você já participa de 5 salas. Saia de uma para entrar em outra." |

## 8.5. Espera de quem chega durante uma partida

**Decisão:** não haverá fila de espera nesta versão, em linha com [regras.md](regras.md) 3.5. Quem tenta entrar durante uma partida recebe `PARTIDA_EM_ANDAMENTO` e **precisa tentar de novo depois**.

- O servidor não guarda a tentativa e não avisa quando a partida terminar.
- Como a sala volta a aceitar entradas assim que termina, a nova tentativa funciona no estado `ENCERRADA`.
- Se a sala for removida nesse meio tempo, a nova tentativa resulta em `SALA_INEXISTENTE`.

Evolução possível (fora do escopo): fila vinculada à sala, com entrada automática ao término da partida e aviso ao jogador. Exigiria definir limite da fila, o que fazer se ela exceder as vagas e como cancelar.

## 8.6. Quem pode iniciar a partida

- Somente o **responsável** da sala, com `INICIAR_PARTIDA`.
- A sala tem de estar em `AGUARDANDO` ou `ENCERRADA` e ter **2 a 6 jogadores**.
- Recusas, sem efeito sobre a sala:

| Condição | Código |
| --- | --- |
| Quem pede não participa da sala | `SALA_NAO_PARTICIPA` |
| Quem pede não é o responsável | `APENAS_RESPONSAVEL` |
| Sala em `EM_PARTIDA` | `PARTIDA_EM_ANDAMENTO` |
| Menos de 2 jogadores | `JOGADORES_INSUFICIENTES` |

- Aceito o pedido, todos os participantes recebem o aviso de início, a partida passa a `EM_PARTIDA`, o placar é zerado (8.10) e começa a rodada 1.
- Não há votação nem início automático. Se o responsável não iniciar, a sala fica em espera; ele só passa a outro jogador ao sair (8.7).

## 8.7. Saída do criador com jogadores na sala

- A sala **não é encerrada**. A responsabilidade passa ao **primeiro dos jogadores restantes na ordem de entrada**, que passa a ser o primeiro da lista (invariante).
- Todos recebem o evento de troca de responsável.
- Vale em qualquer estado e também em caso de desconexão.
- Durante a partida, a troca de responsável não altera turnos, ordem nem pontuação. Só afeta quem pode iniciar a próxima partida.

## 8.8. Remoção de sala vazia

- A sala é removida **imediatamente quando o último jogador sai ou se desconecta**, em qualquer estado.
- Ao remover: cancelam-se os cronômetros da sala, descartam-se palavra, sorteio e placar, e o código não será reaproveitado (8.1).
- Uma sala `ENCERRADA` com um só jogador **não** é removida; ela permanece (o jogador ainda pode esperar outros entrarem e iniciar nova partida).
- Não há período de tolerância: sem persistência nem recuperação de sessão, uma sala vazia não tem como ser retomada.
- Ponto em aberto: salas com jogadores conectados, mas sem atividade, ocupam espaço indefinidamente. Se isso virar problema, pode-se acrescentar um tempo de inatividade (por exemplo, 30 minutos) com aviso aos participantes.

## 8.9. Outra partida na mesma sala

- Com a sala em `ENCERRADA`, o responsável envia `INICIAR_PARTIDA` (8.6), com pelo menos 2 jogadores.
- Participam quem estiver na sala nesse momento, inclusive quem entrou depois do fim da partida anterior, na ordem de entrada.
- O servidor cria um novo sorteio de palavras (as palavras da partida anterior podem aparecer de novo; ver [banco-de-palavras.md](banco-de-palavras.md) 7.5), zera o placar (8.10) e começa a rodada 1 com o primeiro jogador da ordem.
- A sala mantém código e responsável.

## 8.10. Quando o placar é zerado

| Momento | Placar |
| --- | --- |
| Início de **cada partida** (aceitação de `INICIAR_PARTIDA`) | **Zerado** para todos os participantes |
| Fim de partida (normal ou interrompida) | Mantido e visível como placar final (sem vencedor se interrompida) |
| Início de cada rodada | **Não** é zerado; é acumulado ([regras.md](regras.md) 4.2) |
| Entrada de novo jogador | O novo jogador aparece com 0; o placar dos demais não muda |
| Saída de jogador | A pontuação dele é descartada (8.3) |
| Remoção da sala | Descartado |

Durante `ENCERRADA`, quem acabou de entrar aparece com zero, mas **não conta como participante da partida que terminou**: o resultado dela não muda.

## 8.11. Limites de salas

| Limite | Valor | Verificado em | Código |
| --- | ---: | --- | --- |
| Salas simultâneas por jogador (criadas **ou** em que entrou) | 5 | `CRIAR_SALA`, `ENTRAR_SALA` | `LIMITE_SALAS_JOGADOR` |
| Salas simultâneas no servidor | 50 | `CRIAR_SALA` | `LIMITE_SALAS_SERVIDOR` |

- Os valores são constantes no servidor, fáceis de alterar para testes.
- O limite do servidor só impede **criar**; entrar em sala existente continua possível.
- Os limites são verificados dentro da mesma região protegida que altera a lista de salas, para que dois pedidos simultâneos não ultrapassem o máximo.
- Com 5 salas por jogador e 6 jogadores por sala, o servidor suporta cenários de teste amplos sem risco de esgotar recursos na demonstração.

## Decisões novas a confirmar pelo grupo

Estas decisões **não** estavam em [regras.md](regras.md) e foram propostas aqui:
1. Os pontos de quem sai durante a partida deixam de contar (8.3).
2. Desconexão equivale a sair de todas as salas (8.3).
3. Quem sai durante uma partida não pode voltar até o fim dela (8.3).
4. Sem lista pública de salas; só se entra por código (8.1).
5. Código de 4 caracteres, sem reaproveitamento durante a execução (8.1).
6. Limites de 5 salas por jogador e 50 no servidor (8.11).

## Testes planejados

| Cenário | Seção |
| --- | --- |
| Criar sala devolve código válido e único; criador é responsável | 8.1 |
| Criar 6 salas seguidas: a 6ª é recusada (`LIMITE_SALAS_JOGADOR`) | 8.11 |
| Criar sala com o servidor no limite: recusada (`LIMITE_SALAS_SERVIDOR`) | 8.11 |
| `LISTAR_SALAS` mostra só as salas do jogador; lista vazia sem erro | 8.2 |
| Entrar com código inválido, inexistente, repetido, em partida, em sala cheia: cada código de erro, sem alterar a sala | 8.4 |
| Código em minúsculas e com espaços é aceito | 8.1 |
| Tentar entrar em partida e depois do fim: a segunda tentativa funciona | 8.5 |
| Só o responsável inicia; com 1 jogador é recusado | 8.6 |
| Responsável sai: o próximo na ordem assume e todos são avisados | 8.7 |
| Último jogador sai: sala removida e cronômetro cancelado | 8.8 |
| Sala `ENCERRADA` com 1 jogador permanece | 8.8 |
| Nova partida: placar zerado, novo sorteio, quem entrou depois participa | 8.9, 8.10 |
| Sair durante a própria vez: vez passa, sem penalidade | 8.3 |
| Sair deixando 1 jogador: partida interrompida, sem vencedor | 8.3 |
| Desconectar o cliente com 3 salas: sai de todas e cada uma segue suas regras | 8.3 |
| Dois pedidos simultâneos de entrada na última vaga: um entra, outro recebe `SALA_CHEIA` | 8.4, 8.11 |
