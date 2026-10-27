# Regras do jogo

Este documento descreve as regras do jogo como estão implementadas.

- Mensagens trocadas entre cliente e servidor: [protocolo.md](protocolo.md).
- Arquitetura, execução e testes: [README](README.md).

O servidor é sempre quem decide. O cliente só orienta o jogador (por exemplo, avisa "Não é sua vez") e não calcula nada do jogo.

## Constantes

Definidas no início de `servidor/server.py`.

| Constante | Valor | Uso |
| --- | ---: | --- |
| `MIN_JOGADORES` | 2 | Mínimo para iniciar e para a partida continuar |
| `MAX_JOGADORES` | 6 | Máximo de jogadores por sala |
| `MIN_RODADAS` / `MAX_RODADAS` | 1 / 5 | Rodadas por partida, escolhidas na criação da sala |
| `MAX_ERROS` | 6 | Erros que encerram a rodada |
| `TEMPO_TURNO` | 30 s | Prazo de cada turno |
| `PAUSA_ENTRE_RODADAS` | 3 s | Tempo para ler o resultado antes da próxima rodada |
| `PONTOS_PALAVRA` | 5 | Pontos pelo palpite certo |
| `PENALIDADE_PALPITE` | 2 | Pontos perdidos pelo palpite errado |
| `MAX_SALAS` | 50 | Salas ao mesmo tempo no servidor |
| `DIFICULDADES` | `easy`, `medium`, `hard` | Valores aceitos ao criar a sala |
| `TAMANHO_CODIGO` | 4 | Tamanho do código da sala |
| `TAMANHO_MAX_NOME_SALA` | 20 | Tamanho máximo do nome da sala |
| `TAMANHO_MAX_NOME_USUARIO` | 15 | Tamanho máximo do nome do jogador |

## 1. Conexão e identificação

- O jogador se conecta e informa um **nome de usuário**.
- A conexão é recusada se:
  - a versão do protocolo não for `forca1.0`;
  - o nome estiver vazio ou tiver mais de 15 caracteres;
  - o nome tiver `,`, `:` ou `=` (esses caracteres separam listas no protocolo);
  - o nome já estiver em uso por outro jogador conectado;
  - a chave pública enviada não for válida.
- O nome identifica o jogador para todos: na lista da sala, na vez, no placar e nos vencedores.
- Ao conectar, o jogador recebe a lista de **categorias** do banco de palavras.
- Nenhuma outra ação é aceita antes da identificação (`NAO_CONECTADO`), e um segundo `CONNECT` na mesma conexão é recusado (`JA_CONECTADO`).
- Mensagens malformadas ou fora do protocolo são recusadas com `MENSAGEM_INVALIDA` sem afetar o jogo ([protocolo.md](protocolo.md), seção 5).

## 2. Salas

### 2.1. Uma sala por vez

Cada jogador está em **no máximo uma sala**.

| Situação do jogador | Pode fazer |
| --- | --- |
| Fora de sala | Criar sala ou entrar em sala |
| Dentro de sala | Iniciar partida (só o dono), jogar, sair da sala |

Para trocar de sala, o jogador precisa sair da atual primeiro. Consequentemente, cada jogador participa de uma partida por vez.

### 2.2. Criar sala

O jogador informa:

| Campo | Regra | Erro |
| --- | --- | --- |
| Nome da sala | 1 a 20 caracteres (espaços nas pontas são removidos). Não precisa ser único. | `NOME_SALA_INVALIDO` |
| Máximo de jogadores | 2 a 6 | `NUM_JOGADORES_INVALIDO` |
| Dificuldade | `easy`, `medium` ou `hard` (ver 4.1) | `DIFICULDADE_INVALIDA` |
| Rodadas | 1 a 5 | `RODADAS_INVALIDAS` |
| Categoria | Uma categoria do banco ou `qualquer` | `CATEGORIA_INVALIDA` |

Também é recusado:

| Condição | Erro |
| --- | --- |
| O jogador já está em uma sala | `JA_EM_SALA` |
| O servidor já tem 50 salas | `LIMITE_SALAS_SERVIDOR` |
| A combinação de categoria e dificuldade tem menos palavras que o número de rodadas | `PALAVRAS_INSUFICIENTES` |

A última verificação existe porque as palavras não se repetem na partida, e algumas combinações têm poucas palavras (Profissões e Comidas e bebidas não têm nenhuma palavra `easy`).

Quem cria:
- entra automaticamente na sala e passa a ser o **dono**;
- recebe o **código da sala**, que deve repassar aos outros jogadores por fora do jogo (não há lista pública de salas).

### 2.3. Código da sala

- 4 caracteres de `ABCDEFGHJKMNPQRSTUVWXYZ23456789`. Ficam de fora `I`, `L`, `O`, `0` e `1`, que se confundem.
- Único e **nunca reaproveitado** enquanto o servidor estiver rodando.
- Aceito em maiúsculas ou minúsculas, com espaços nas pontas.

### 2.4. Entrar em sala

As verificações acontecem nesta ordem. A primeira que falhar define a recusa, e a recusa não altera nada.

| Ordem | Condição | Erro |
| ---: | --- | --- |
| 1 | Código fora do formato (tamanho ou caracteres) | `CODIGO_INVALIDO` |
| 2 | Não existe sala com o código | `SALA_INEXISTENTE` |
| 3 | O jogador já está em alguma sala | `JA_EM_SALA` |
| 4 | A sala está com partida em andamento | `PARTIDA_EM_ANDAMENTO` |
| 5 | A sala atingiu o máximo de jogadores | `SALA_CHEIA` |

Ao entrar, o jogador vai para o **fim da ordem** da sala, recebe a configuração da sala (rodadas, dificuldade e categoria) e todos os participantes recebem a lista atualizada.

### 2.5. Início da partida

- Com **2 jogadores ou mais**, todos recebem o aviso de que a partida já pode começar. Não é preciso esperar a sala encher.
- A partida **não começa sozinha**: o dono precisa iniciá-la.
- O pedido de início é verificado nesta ordem:

| Condição | Erro |
| --- | --- |
| Quem pede não está na sala | `SALA_NAO_PARTICIPA` |
| Quem pede não é o dono | `APENAS_DONO` |
| Já há partida em andamento | `PARTIDA_EM_ANDAMENTO` |
| Menos de 2 jogadores | `JOGADORES_INSUFICIENTES` |

### 2.6. Sair da sala

O jogador pode sair a qualquer momento. Fechar o cliente ou perder a conexão tem o mesmo efeito.

Ao sair:
- o jogador é removido e os demais recebem a lista atualizada;
- se era o **dono**, o próximo da ordem de entrada vira dono;
- se a sala ficou **vazia**, ela é removida;
- se havia **partida em andamento**:
  - os **pontos** de quem saiu são descartados: ele some do placar e não pode vencer;
  - restando 2 ou mais jogadores, a partida continua; se era a vez de quem saiu, a vez passa ao próximo;
  - restando 1 jogador, a rodada e a partida terminam como **interrompidas**, sem vencedor.

O cliente pede confirmação antes de sair durante uma partida.

### 2.7. Estados da sala

```
aguardando ──(dono inicia)──> em andamento ──(fim da partida)──> finalizada
                                    ^                                │
                                    └───────(dono inicia de novo)────┘
```

| Estado | Entrada de jogadores | Iniciar partida |
| --- | --- | --- |
| `aguardando` | Permitida, se houver vaga | Permitido (dono, 2 ou mais jogadores) |
| `em andamento` | Recusada | Recusado |
| `finalizada` | Permitida, se houver vaga | Permitido (dono, 2 ou mais jogadores) |

Uma sala sai de qualquer estado quando fica vazia (é removida).

## 3. Partida

Uma partida tem de **1 a 5 rodadas** (definido na criação da sala). Cada rodada tem uma palavra. Os pontos se acumulam entre as rodadas.

### 3.1. Início da partida

- O placar de todos os jogadores da sala é **zerado**.
- A primeira rodada começa imediatamente.
- Quem entra na sala depois que a partida terminou não aparece no placar dela; só participa da próxima.

### 3.2. Rodadas

No início de cada rodada:
1. O servidor sorteia uma palavra da dificuldade e da categoria da sala que **ainda não saiu nesta partida** (4.1).
2. Erros e letras usadas são zerados. O placar **não** é zerado.
3. Todos recebem o número da rodada, a **categoria** da palavra e a palavra escondida.
4. Começa o primeiro turno.

**Quem começa:** na rodada 1, o primeiro da ordem (o dono). Em cada rodada seguinte, o **próximo** depois de quem começou a anterior. Se quem começou a anterior saiu da sala, começa quem estava logo depois dele.

Depois que uma rodada termina, há uma **pausa de 3 segundos** antes da próxima, para os jogadores verem o resultado. Durante a pausa nenhuma jogada é aceita (`SEM_RODADA_ATIVA`).

### 3.3. Turnos

- A ordem de entrada na sala define a ordem dos turnos. A vez passa de forma circular.
- Só o jogador da vez pode jogar.
- Em cada turno o jogador escolhe **uma** destas jogadas:
  - **letra**: tenta uma letra;
  - **palpite**: tenta a palavra inteira.
- Uma jogada válida, certa ou errada, **encerra o turno**. Acertar não dá jogada extra.
- **Tempo esgotado** (30 s): todos são avisados e a vez passa ao próximo, sem erro e sem perder pontos.
- Uma jogada inválida (3.4) é recusada sem passar a vez e **sem reiniciar o prazo**: o jogador pode corrigir no tempo que resta.

### 3.4. Jogadas inválidas

Verificadas nesta ordem. Nenhuma altera a palavra, os erros ou os pontos.

| Condição | Erro |
| --- | --- |
| O jogador não está na sala informada | `SALA_NAO_PARTICIPA` |
| Não há rodada em andamento (antes de iniciar, na pausa ou depois do fim) | `SEM_RODADA_ATIVA` |
| Não é a vez do jogador | `NAO_E_SUA_VEZ` |
| Resposta vazia | `RESPOSTA_VAZIA` |
| Letra: mais de um caractere, ou caractere que não é letra | `LETRA_INVALIDA` |
| Letra: já usada nesta rodada | `LETRA_REPETIDA` |
| Palpite: contém algo além de letras, espaço e hífen | `PALPITE_INVALIDO` |

### 3.5. Letra

| Resultado | Pontos | Erros |
| --- | --- | --- |
| A letra aparece na palavra | **+1 por ocorrência** (em BANANA, `A` vale +3) | — |
| A letra não aparece | 0 | +1 |

- Todas as ocorrências são reveladas, incluindo as variantes com acento (4.2).
- A letra entra na lista de letras usadas nos dois casos.
- A letra que revela a última letra escondida vale só as suas ocorrências, sem bônus, e encerra a rodada.

### 3.6. Palpite

| Resultado | Pontos | Erros |
| --- | --- | --- |
| Correto | **+5** e a rodada termina | — |
| Incorreto | **−2** | +1 |

- O palpite certo vale só os 5 pontos: as letras que ainda estavam escondidas não rendem pontos extras.
- **Qualquer tamanho é aceito.** Um palpite curto ou longo demais simplesmente está errado e conta como erro.
- Na comparação são ignorados: maiúsculas/minúsculas, acentos e cedilha, espaços nas pontas e espaços repetidos.
- Espaços internos e hífens continuam obrigatórios: `guarda chuva` **não** corresponde a `GUARDA-CHUVA`.
- A pontuação pode ficar negativa.
- Se o palpite errado causar o sexto erro, a penalidade é aplicada e depois a rodada termina.
- O cliente pede confirmação antes de enviar um palpite, avisando o custo de errar.

### 3.7. Fim da rodada

| Motivo | Código |
| --- | --- |
| Palpite correto | `PALPITE` |
| Uma letra revelou a última letra escondida | `PALAVRA_COMPLETA` |
| 6 erros | `LIMITE_ERROS` |
| Sobrou 1 jogador na sala | `INTERROMPIDA` |

Ao terminar, todos recebem a **palavra revelada**, o motivo e o placar atualizado.

### 3.8. Fim da partida

- **Normal:** depois da última rodada. Vence quem tem **mais pontos**. Se houver empate, **todos** os empatados vencem (não há desempate).
- **Interrompida:** quando sobra 1 jogador. Não há vencedor.

Todos recebem o placar final, ordenado por pontos. Empatados aparecem na ordem de entrada na sala e ocupam a mesma posição.

A sala vai para `finalizada` e os jogadores continuam nela. O dono pode iniciar outra partida, que zera o placar e sorteia palavras novas.

## 4. Palavras e letras

### 4.1. Banco de palavras

- As palavras ficam em `dados/palavras.json`, agrupadas por categoria (321 palavras em 10 categorias).
- Ao iniciar, o servidor **descarta**, com um aviso no terminal, as palavras que:
  - têm algo além de letras, espaço e hífen;
  - têm menos de 3 ou mais de 20 letras (sem contar espaços e hífens), ou mais de 30 caracteres;
  - começam ou terminam com espaço ou hífen, ou têm dois separadores seguidos;
  - repetem outra palavra já carregada (comparando sem acentos e sem diferenciar maiúsculas).
- A dificuldade é definida pelo **número de letras**:

| Dificuldade | Letras | Palavras no banco |
| --- | --- | ---: |
| `easy` | até 5 | 50 |
| `medium` | 6 a 8 | 170 |
| `hard` | 9 ou mais | 101 |

- Com a categoria `qualquer`, o sorteio usa todas as categorias.
- Dentro de uma partida a palavra **não se repete**. Entre partidas, pode repetir.

### 4.2. Acentos e cedilha

Na comparação, as variantes valem como a mesma letra:

| Letra | Variantes |
| --- | --- |
| A | Á À Â Ã |
| E | É Ê |
| I | Í |
| O | Ó Ô Õ |
| U | Ú Ü |
| C | Ç |

- Em `MAÇÃ`, a letra `C` revela o `Ç`, e `A` revela tanto o `A` quanto o `Ã` (+2 pontos).
- Tentar `Ã` depois de `A` (ou o contrário) é **letra repetida**.
- A grafia original é mantida na exibição: a palavra revelada aparece como `MAÇÃ`, não `MACA`.

### 4.3. Palavra escondida

- Cada letra não descoberta aparece como `_`.
- Espaços e hífens aparecem desde o início.
- Tudo é exibido em maiúsculas.

Exemplo: `guarda-chuva` depois da letra `A` → `__A__A-____A`.

## 5. Interface do cliente

O cliente é um menu numérico no terminal. As opções mudam conforme a situação do jogador:

| Situação | Opções |
| --- | --- |
| Fora de sala | 1 - Criar sala, 2 - Entrar em sala, 0 - Sair |
| Na sala, sem partida | 3 - Iniciar partida (só para o dono), 6 - Sair da sala, 0 - Sair |
| Em partida | 4 - Letra, 5 - Palpite, 6 - Sair da sala, 0 - Sair |

Durante a partida, a tela é **redesenhada a cada turno**, em vez de acumular mensagens. O painel mostra tudo o que importa naquele momento:

```
============================================================
  Sala do Bot  (VGWE)                        Rodada 1 de 3
============================================================

  Categoria:  Frutas

      +---+
      |   O         _ E _ _ _ E _
      |
      |             Letras usadas:  A  E
     ===            Erros:  X . . . . .  (1 de 6)

  Placar:   bot 0    rich 2

  Últimas jogadas:
    - bot tentou a letra A: errou (0)
    - Você tentou a letra E: acertou (+2)
    - bot: tempo esgotado

------------------------------------------------------------
  >>> SUA VEZ!  Você tem 30 segundos.
      4 - Letra     5 - Palpite     6 - Sair da sala
------------------------------------------------------------
```

- A forca ganha uma parte a cada erro.
- **Últimas jogadas** mostra as 4 jogadas mais recentes da rodada (acertos, erros, tempo esgotado e saída de jogadores).
- No fim de cada rodada aparece uma tela com a palavra revelada, o motivo e o placar. No turno seguinte, o painel lembra o resultado em "Rodada anterior".
- No fim da partida, o placar final é mostrado com as posições (empatados na mesma posição) e os vencedores.
- Fora da partida (menus, entrada e saída de jogadores, erros), cada aviso aparece separado por uma linha em branco.
- Cores (ANSI): verde para acerto, vermelho para erro, amarelo para "sua vez" e avisos, ciano no cabeçalho.
- Depois de cada sequência de avisos do servidor, o cliente repete o texto que o jogador estava respondendo (por exemplo, `Escolha uma opção:`), para indicar onde continuar digitando.
- Em terminais sem suporte a códigos ANSI, as cores e a limpeza de tela podem ser desligadas em `cliente/client.py` (`USAR_CORES = False` e `LIMPAR_TELA = False`).
