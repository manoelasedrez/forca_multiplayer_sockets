# Especificação do protocolo forca1.0

Este documento descreve o protocolo de aplicação usado entre o cliente e o servidor da Forca Multiplayer. Ele foi escrito para que seja possível implementar um cliente ou um servidor compatível **sem consultar o código-fonte**.

- Regras do jogo (o que o servidor valida e decide): [regras.md](regras.md).
- Arquitetura e justificativa do TCP e da concorrência: [README](README.md).
- Implementação de referência: `protocol/protocol.py`.

Sumário:

1. [Transporte e conexão](#1-transporte-e-conexão)
2. [Formato das mensagens](#2-formato-das-mensagens)
3. [Mensagens](#3-mensagens)
4. [Sequências de interação](#4-sequências-de-interação)
5. [Mensagens inválidas e erros](#5-mensagens-inválidas-e-erros)
6. [Códigos de erro](#6-códigos-de-erro)
7. [Cifragem (planejada)](#7-cifragem-planejada)

---

## 1. Transporte e conexão

| Item | Valor |
| --- | --- |
| Transporte | TCP |
| Arquitetura | Cliente-servidor. Os clientes só falam com o servidor, nunca entre si. |
| Porta padrão | `38905` (se estiver ocupada, o servidor tenta a seguinte) |
| Conexões por cliente | Uma, mantida aberta durante toda a sessão |
| Versão | `forca1.0` |

- O cliente abre a conexão e envia `CONNECT` como **primeira** mensagem. Até o `CONNECT` ser aceito, qualquer outro pedido é recusado com `NAO_CONECTADO`.
- A conexão fica aberta enquanto o jogador usa o jogo. As mensagens vão nos dois sentidos a qualquer momento: além de responder aos pedidos, o servidor envia **eventos** (por exemplo, "é a vez de Bob") sem que o cliente peça.
- Fechar a conexão equivale a sair da sala em que o jogador estiver (seção 4.7).
- O servidor ativa o *keepalive* do TCP em cada conexão: um cliente que some sem fechar a conexão (cabo desligado, máquina travada) é detectado em cerca de 25 segundos e tratado como desconexão.

## 2. Formato das mensagens

### 2.1. Enquadramento

O TCP entrega um fluxo contínuo de bytes, sem marcar onde uma mensagem termina e a próxima começa. Por isso, cada mensagem é precedida pelo seu tamanho:

```
+--------------------------+-----------------------------+
| tamanho (4 bytes)        | corpo (tamanho bytes)       |
| inteiro sem sinal,       | texto UTF-8                 |
| big-endian               |                             |
+--------------------------+-----------------------------+
```

- O **tamanho** conta apenas o corpo, sem os 4 bytes do próprio tamanho.
- O tamanho máximo do corpo é **16384 bytes** (`MAX_TAMANHO_MENSAGEM`). As mensagens do jogo têm poucas centenas de bytes.
- Quem recebe lê exatamente 4 bytes, depois lê exatamente `tamanho` bytes. Uma única leitura do socket pode devolver menos bytes do que o pedido, então a leitura é repetida até completar.

### 2.2. Corpo

O corpo é texto em UTF-8, dividido em linhas terminadas por `\r\n`:

```
COMANDO\r\n
chave1: valor1\r\n
chave2: valor2\r\n
```

- A **1ª linha** é o comando, que identifica o tipo da mensagem (ex.: `ROOM JOIN`).
- As **demais linhas** são atributos no formato `chave: valor`. A ordem dos atributos não importa.
- As chaves são comparadas **sem diferenciar maiúsculas de minúsculas** (`USERS` e `users` são a mesma chave).
- Os espaços nas pontas dos valores são removidos.
- O valor vai até o fim da linha e pode conter `:`. Não pode conter `\r\n`.
- Uma mensagem sem atributos tem só a 1ª linha.

Exemplo completo de uma mensagem `ROOM JOIN`, em bytes:

```
00 00 00 1A                         tamanho = 26
52 4F 4F 4D 20 4A 4F 49 4E 0D 0A    "ROOM JOIN\r\n"
72 6F 6F 6D 2D 69 64 3A 20          "room-id: "
4B 37 58 50 0D 0A                   "K7XP\r\n"
```

### 2.3. Tipos de valores

| Tipo | Formato | Exemplo |
| --- | --- | --- |
| Texto | Texto livre, sem quebra de linha | `Sala da Ana` |
| Inteiro | Número em decimal, com `-` se negativo | `-2` |
| Booleano | `true` ou `false` | `true` |
| Lista | Itens separados por `, `. Lista vazia = valor vazio. | `ana, bob` |
| Placar | Itens `nome=pontos` separados por `, `, do maior para o menor | `ana=8, bob=-2` |
| Código de sala | 4 caracteres de `ABCDEFGHJKMNPQRSTUVWXYZ23456789` | `K7XP` |

Por causa das listas e do placar, nomes de usuário não podem conter `,`, `:` nem `=`.

## 3. Mensagens

Sentidos:
- **C→S**: do cliente para o servidor (pedido).
- **S→C**: do servidor para um cliente (resposta ao pedido, só para quem pediu).
- **S→sala**: do servidor para todos os jogadores da sala (evento).

Resumo:

| Comando | Sentido | Resposta de sucesso | Seção |
| --- | --- | --- | --- |
| `CONNECT` | C→S | `CONNECT OK` | 3.1 |
| `CONNECT OK` | S→C | — | 3.1 |
| `CONNECT ERROR` | S→C | — | 3.1 |
| `ROOM CREATE` | C→S | `ROOM CREATE OK` | 3.2 |
| `ROOM CREATE OK` | S→C | — | 3.2 |
| `ROOM JOIN` | C→S | `ROOM JOIN OK` | 3.3 |
| `ROOM JOIN OK` | S→C | — | 3.3 |
| `ROOM UPDATE` | S→sala | — | 3.4 |
| `ROOM LEAVE` | C→S | `ROOM LEAVE OK` | 3.5 |
| `ROOM LEAVE OK` | S→C | — | 3.5 |
| `ROOM START` | C→S | `ROOM START OK` | 3.6 |
| `ROOM START OK` | S→C | — | 3.6 |
| `ROOM STARTED` | S→sala | — | 3.6 |
| `ROUND START` | S→sala | — | 3.7 |
| `TURN` | S→sala | — | 3.8 |
| `TURN TIMEOUT` | S→sala | — | 3.8 |
| `TURN RESPONSE` (pedido) | C→S | `TURN RESPONSE OK` | 3.9 |
| `TURN RESPONSE OK` | S→C | — | 3.9 |
| `TURN RESPONSE` (resultado) | S→sala | — | 3.9 |
| `ROUND END` | S→sala | — | 3.10 |
| `GAME OVER` | S→sala | — | 3.10 |
| `ERROR` | S→C | — | 3.11 |

Todo pedido recusado recebe `ERROR` (seção 3.11), exceto o `CONNECT`, que é recusado com `CONNECT ERROR`.

### 3.1. Conexão

#### `CONNECT <versão>` (C→S)

Primeira mensagem do cliente. Identifica o jogador. A versão vai na 1ª linha: `CONNECT forca1.0`.

| Atributo | Tipo | Significado |
| --- | --- | --- |
| `public-key` | Texto | Chave pública Curve25519 do cliente (32 bytes), em Base64. Reservada para a cifragem (seção 7). Precisa ser uma chave válida. |
| `username` | Texto | Nome do jogador: de 1 a 15 caracteres, sem `,` `:` `=`, e diferente do nome de todos os jogadores conectados. |

Respostas: `CONNECT OK`, `CONNECT ERROR` ou, se o cliente já estiver conectado, `ERROR` com `JA_CONECTADO`.

#### `CONNECT OK <versão>` (S→C)

O jogador foi aceito. A partir daqui o cliente pode enviar os demais pedidos.

| Atributo | Tipo | Significado |
| --- | --- | --- |
| `public-key` | Texto | Chave pública Curve25519 do servidor, em Base64. Reservada para a cifragem (seção 7). |
| `categorias` | Lista | Categorias de palavras disponíveis no servidor. Usadas no `ROOM CREATE`. |

#### `CONNECT ERROR <versão>` (S→C)

O `CONNECT` foi recusado. Diferente das outras mensagens, depois da 1ª linha vem **um texto livre** com o motivo, sem atributos. A conexão continua aberta e o cliente pode enviar outro `CONNECT`.

Motivos possíveis:

| Texto | Causa |
| --- | --- |
| `versao nao suportada, use forca1.0` | A versão do `CONNECT` não é `forca1.0` |
| `nome de usuario deve ter de 1 a 15 caracteres` | Nome vazio ou longo demais |
| `nome de usuario nao pode ter , : =` | Nome com caractere proibido |
| `nome de usuario ja em uso` | Outro jogador conectado usa o mesmo nome |
| `chave publica invalida` | `public-key` não é uma chave Curve25519 em Base64 |

### 3.2. Criar sala

#### `ROOM CREATE` (C→S)

Cria uma sala. Quem cria entra nela automaticamente e é o **dono**.

| Atributo | Tipo | Significado |
| --- | --- | --- |
| `num-players` | Inteiro | Máximo de jogadores da sala, de 2 a 6. A partida pode começar antes de encher. |
| `dificuldade` | Texto | `easy` (palavras de até 5 letras), `medium` (6 a 8) ou `hard` (9 ou mais). |
| `room-name` | Texto | Nome da sala, de 1 a 20 caracteres. Só para exibição; não precisa ser único. |
| `rounds` | Inteiro | Número de rodadas da partida, de 1 a 5. |
| `categoria` | Texto | Uma das categorias do `CONNECT OK`, ou `qualquer` para sortear de todas. |

Recusas (`ERROR`): `JA_EM_SALA`, `LIMITE_SALAS_SERVIDOR`, `NOME_SALA_INVALIDO`, `NUM_JOGADORES_INVALIDO`, `DIFICULDADE_INVALIDA`, `RODADAS_INVALIDAS`, `CATEGORIA_INVALIDA`, `PALAVRAS_INSUFICIENTES`, verificados nesta ordem.

#### `ROOM CREATE OK` (S→C)

A sala foi criada.

| Atributo | Tipo | Significado |
| --- | --- | --- |
| `room-id` | Código de sala | Código da sala, que o dono repassa aos outros jogadores para que entrem. |

### 3.3. Entrar em sala

#### `ROOM JOIN` (C→S)

| Atributo | Tipo | Significado |
| --- | --- | --- |
| `room-id` | Código de sala | Código da sala. Aceito em minúsculas e com espaços nas pontas. |

Recusas (`ERROR`), verificadas nesta ordem: `CODIGO_INVALIDO`, `SALA_INEXISTENTE`, `JA_EM_SALA`, `PARTIDA_EM_ANDAMENTO`, `SALA_CHEIA`.

Em caso de sucesso, o servidor responde `ROOM JOIN OK` a quem entrou e envia `ROOM UPDATE` para toda a sala (inclusive para quem entrou).

#### `ROOM JOIN OK` (S→C)

| Atributo | Tipo | Significado |
| --- | --- | --- |
| `USERS` | Lista | Jogadores da sala, em ordem de entrada. O primeiro é o dono. |
| `dificuldade` | Texto | Dificuldade da sala. |
| `room-name` | Texto | Nome da sala. |
| `rounds` | Inteiro | Rodadas por partida. |
| `categoria` | Texto | Categoria da sala, ou `qualquer`. |

### 3.4. `ROOM UPDATE` (S→sala)

A lista de jogadores da sala mudou (alguém entrou ou saiu) ou uma partida terminou.

| Atributo | Tipo | Significado |
| --- | --- | --- |
| `room-id` | Código de sala | Sala que mudou. |
| `USERS` | Lista | Jogadores atuais, em ordem de entrada. O primeiro é o dono (muda quando o dono sai). |
| `dificuldade` | Texto | Dificuldade da sala. |
| `ready` | Booleano | `true` se o dono já pode iniciar uma partida: 2 ou mais jogadores e nenhuma partida em andamento. |

### 3.5. Sair da sala

#### `ROOM LEAVE` (C→S)

| Atributo | Tipo | Significado |
| --- | --- | --- |
| `room-id` | Código de sala | Sala da qual o jogador quer sair. |

Recusa (`ERROR`): `SALA_NAO_PARTICIPA`. Efeitos da saída na sala: seção 4.7.

#### `ROOM LEAVE OK` (S→C)

Saída confirmada. Sem atributos. O jogador fica fora de qualquer sala e pode criar ou entrar em outra.

### 3.6. Iniciar partida

#### `ROOM START` (C→S)

Pedido do dono para iniciar uma partida.

| Atributo | Tipo | Significado |
| --- | --- | --- |
| `room-id` | Código de sala | Sala onde a partida começa. |

Recusas (`ERROR`), nesta ordem: `SALA_NAO_PARTICIPA`, `APENAS_DONO`, `PARTIDA_EM_ANDAMENTO`, `JOGADORES_INSUFICIENTES`.

#### `ROOM START OK` (S→C)

Início aceito. Sem atributos. Enviado só para o dono, antes do `ROOM STARTED`.

#### `ROOM STARTED` (S→sala)

A partida começou. O placar de todos os participantes começa em 0. Logo em seguida vem o `ROUND START` da rodada 1.

| Atributo | Tipo | Significado |
| --- | --- | --- |
| `room-id` | Código de sala | Sala da partida. |
| `USERS` | Lista | Participantes da partida, em ordem de entrada (que é a ordem dos turnos). |
| `rounds` | Inteiro | Número de rodadas da partida. |

### 3.7. `ROUND START` (S→sala)

Começou uma rodada. Logo em seguida vem o primeiro `TURN`.

| Atributo | Tipo | Significado |
| --- | --- | --- |
| `room-id` | Código de sala | Sala da partida. |
| `round` | Inteiro | Número desta rodada, começando em 1. |
| `rounds` | Inteiro | Total de rodadas da partida. |
| `categoria` | Texto | Categoria da palavra sorteada (a dica da rodada). |
| `word` | Texto | Palavra escondida: `_` para cada letra, espaços e hífens visíveis. Ex.: `______-_____`. |

### 3.8. Turnos

#### `TURN` (S→sala)

Começou um turno.

| Atributo | Tipo | Significado |
| --- | --- | --- |
| `room-id` | Código de sala | Sala da partida. |
| `user-turn` | Texto | Nome do jogador da vez. Só ele pode jogar. |
| `tempo` | Inteiro | Segundos que ele tem para jogar. |

#### `TURN TIMEOUT` (S→sala)

O tempo do jogador da vez acabou. Ele não perde pontos e não soma erro. O próximo `TURN` vem em seguida.

| Atributo | Tipo | Significado |
| --- | --- | --- |
| `room-id` | Código de sala | Sala da partida. |
| `user-turn` | Texto | Jogador que perdeu a vez. |

### 3.9. Jogadas

#### `TURN RESPONSE` (C→S, pedido)

Jogada do jogador da vez.

| Atributo | Tipo | Significado |
| --- | --- | --- |
| `room-id` | Código de sala | Sala da partida. |
| `guess` | Booleano | `false`: tentativa de **letra**. `true`: **palpite** da palavra inteira. |
| `answer` | Texto | A letra (uma só, com ou sem acento) ou o palpite (letras, espaços e hífens, de qualquer tamanho). |

Recusas (`ERROR`), nesta ordem: `SALA_NAO_PARTICIPA`, `SEM_RODADA_ATIVA`, `NAO_E_SUA_VEZ`, `RESPOSTA_VAZIA` e depois, para letra, `LETRA_INVALIDA` e `LETRA_REPETIDA`; para palpite, `PALPITE_INVALIDO`. Uma recusa não passa a vez nem reinicia o prazo.

#### `TURN RESPONSE OK` (S→C)

Jogada aceita. Sem atributos. Enviado só para quem jogou, antes do resultado.

#### `TURN RESPONSE` (S→sala, resultado)

Resultado de uma jogada aceita. Tem a mesma 1ª linha do pedido; os dois são diferenciados pelo atributo `user-turn`, que só existe nesta mensagem.

| Atributo | Tipo | Significado |
| --- | --- | --- |
| `room-id` | Código de sala | Sala da partida. |
| `user-turn` | Texto | Quem jogou. |
| `guess` | Booleano | `false`: foi uma letra. `true`: foi um palpite. |
| `answer` | Texto | A letra ou o palpite enviado. |
| `accepted` | Booleano | `true` se acertou (a letra está na palavra, ou o palpite está certo). |
| `word` | Texto | Palavra escondida depois da jogada. |
| `pontos` | Inteiro | Pontos que o jogador ganhou (positivo) ou perdeu (negativo) nesta jogada. Letra: +1 por ocorrência, ou 0. Palpite: +5 ou −2. |
| `erros` | Inteiro | Erros da rodada até agora (de 0 a 6). |
| `letras` | Lista | Letras já tentadas na rodada, em maiúsculas e sem acento, na ordem em que foram jogadas. |

Depois desta mensagem vem um novo `TURN` ou, se a rodada acabou, o `ROUND END`.

### 3.10. Fim de rodada e de partida

#### `ROUND END` (S→sala)

A rodada terminou.

| Atributo | Tipo | Significado |
| --- | --- | --- |
| `room-id` | Código de sala | Sala da partida. |
| `round` | Inteiro | Número da rodada que terminou. |
| `word` | Texto | Palavra completa, revelada, com acentos. |
| `motivo` | Texto | `PALPITE` (alguém acertou a palavra), `PALAVRA_COMPLETA` (uma letra revelou a última letra), `LIMITE_ERROS` (6 erros) ou `INTERROMPIDA` (sobrou 1 jogador). |
| `placar` | Placar | Pontuação acumulada na partida, do maior para o menor. |

Se ainda há rodadas, o próximo `ROUND START` vem cerca de 3 segundos depois. Se era a última, ou se a rodada foi interrompida, vem o `GAME OVER`.

#### `GAME OVER` (S→sala)

A partida terminou. Logo depois vem um `ROOM UPDATE` (a sala pode iniciar outra partida).

| Atributo | Tipo | Significado |
| --- | --- | --- |
| `room-id` | Código de sala | Sala da partida. |
| `winners` | Lista | Vencedores: todos os que têm a maior pontuação (mais de um em caso de empate). Vazia se ninguém venceu. |
| `placar` | Placar | Placar final, do maior para o menor. Empatados aparecem na ordem de entrada. Quem saiu durante a partida não aparece. |
| `motivo` | Texto | `NORMAL` (todas as rodadas foram jogadas) ou `INTERROMPIDA` (sobrou 1 jogador; `winners` vem vazia). |

### 3.11. `ERROR` (S→C)

Um pedido foi recusado, ou a mensagem recebida era inválida. **Nada muda no servidor.** A conexão continua aberta, exceto no caso da seção 5.3.

| Atributo | Tipo | Significado |
| --- | --- | --- |
| `code` | Texto | Código fixo do erro (seção 6). O cliente deve decidir o que fazer pelo código. |
| `error` | Texto | Descrição do erro para mostrar ao jogador. Pode mudar entre versões. |

## 4. Sequências de interação

### 4.1. Conexão

```
Cliente                         Servidor
   │── CONNECT forca1.0 ──────────>│
   │<───────── CONNECT OK forca1.0 ─│   (ou CONNECT ERROR: o cliente pode tentar de novo)
```

### 4.2. Criar sala e entrar

```
Ana                             Servidor                        Bob
   │── ROOM CREATE ──────────────>│                               │
   │<──────────── ROOM CREATE OK ─│                               │
   │       (Ana passa o código para Bob por fora do jogo)         │
   │                              │<──────────────── ROOM JOIN ───│
   │                              │── ROOM JOIN OK ──────────────>│
   │<────── ROOM UPDATE (ready) ──│── ROOM UPDATE (ready) ───────>│
```

### 4.3. Início da partida

```
Ana (dono)                      Servidor                        Bob
   │── ROOM START ───────────────>│                               │
   │<───────────── ROOM START OK ─│                               │
   │<────────────── ROOM STARTED ─│── ROOM STARTED ──────────────>│
   │<─────────────── ROUND START ─│── ROUND START ───────────────>│
   │<───────────── TURN (Ana) ────│── TURN (Ana) ────────────────>│
```

### 4.4. Jogada

```
Ana (da vez)                    Servidor                        Bob
   │── TURN RESPONSE ────────────>│                               │
   │<────────── TURN RESPONSE OK ─│                               │
   │<──── TURN RESPONSE (result.) ─│── TURN RESPONSE (result.) ───>│
   │<───────────── TURN (Bob) ────│── TURN (Bob) ────────────────>│   (ou ROUND END)
```

Jogada recusada: só `ERROR` para quem jogou. O turno e o prazo continuam correndo.

### 4.5. Tempo esgotado

```
Ana                             Servidor                        Bob
   │<────────────── TURN TIMEOUT ─│── TURN TIMEOUT ──────────────>│
   │<───────────── TURN (Bob) ────│── TURN (Bob) ────────────────>│
```

### 4.6. Fim de rodada e de partida

```
Ana                             Servidor                        Bob
   │<───────────────── ROUND END ─│── ROUND END ─────────────────>│
   │                       (pausa de 3 s)                         │
   │<─────────────── ROUND START ─│── ROUND START ───────────────>│   se faltam rodadas
   │<───────────────────── TURN ──│── TURN ──────────────────────>│

   na última rodada:
   │<───────────────── GAME OVER ─│── GAME OVER ─────────────────>│
   │<─────────────── ROOM UPDATE ─│── ROOM UPDATE ───────────────>│   ready: pode jogar de novo
```

Para jogar de novo, o dono envia outro `ROOM START` (seção 4.3).

### 4.7. Saída e desconexão

```
Bob                             Servidor                        Ana
   │── ROOM LEAVE ───────────────>│                               │
   │<───────────── ROOM LEAVE OK ─│                               │
   │                              │── (eventos abaixo) ──────────>│
```

O que os jogadores que ficaram recebem:

| Situação | Eventos |
| --- | --- |
| Sem partida em andamento | `ROOM UPDATE` |
| Partida em andamento, restam 2 ou mais | `ROOM UPDATE`; se era a vez de quem saiu, um novo `TURN` |
| Partida em andamento, resta 1 | `ROUND END` (motivo `INTERROMPIDA`, se havia rodada em andamento), `GAME OVER` (motivo `INTERROMPIDA`) e `ROOM UPDATE` |
| A sala ficou vazia | Nada: a sala é removida |

Se quem saiu era o dono, o próximo da lista passa a ser o dono (é o primeiro de `USERS` no `ROOM UPDATE`).

A **desconexão** (o cliente fecha a conexão, ou ela cai) tem o mesmo efeito, sem o `ROOM LEAVE OK`.

## 5. Mensagens inválidas e erros

O servidor nunca confia no cliente: toda mensagem é verificada e toda recusa é respondida. Os casos, do mais grave para o mais simples:

### 5.1. Pedido válido, recusado pelas regras

A mensagem está bem formada, mas o pedido não pode ser atendido (sala cheia, não é a vez do jogador, letra repetida...).

- Resposta: `ERROR` com o código da regra (seção 6).
- Nada muda no servidor. A conexão continua.

### 5.2. Mensagem malformada

O enquadramento está correto (o tamanho bate), mas o corpo não pode ser interpretado. Exemplos:
- comando desconhecido (`PULAR VEZ`);
- atributo obrigatório faltando (`ROOM JOIN` sem `room-id`);
- linha de atributo sem `:`;
- número inválido (`num-players: dois`);
- corpo que não é UTF-8, ou vazio;
- uma mensagem que só o servidor envia, mandada pelo cliente (ex.: `ROOM CREATE OK`).

Resposta: `ERROR` com `MENSAGEM_INVALIDA` e a descrição do problema. Como o corpo foi lido inteiro, a próxima mensagem começa no lugar certo e **a conexão continua**.

### 5.3. Tamanho acima do limite

O tamanho anunciado passa de 16384 bytes.

- Resposta: `ERROR` com `MENSAGEM_INVALIDA`, e o servidor **fecha a conexão**.
- Motivo: o servidor não lê o corpo (seriam bytes demais), então não sabe onde começa a próxima mensagem e não consegue continuar lendo o fluxo.
- O fechamento é tratado como desconexão (seção 4.7).

### 5.4. Erro interno

Uma falha inesperada no servidor ao tratar um pedido. A resposta é `ERROR` com `ERRO_INTERNO`, e a conexão continua. Esse caso não deve acontecer; se acontecer, é um defeito a corrigir.

### 5.5. Do lado do cliente

- Uma mensagem malformada vinda do servidor é ignorada e o cliente avisa o jogador.
- Se a conexão cai, o cliente avisa o jogador e encerra.

## 6. Códigos de erro

| Código | Pedido | Quando |
| --- | --- | --- |
| `MENSAGEM_INVALIDA` | Qualquer um | Mensagem malformada ou acima do tamanho máximo (seção 5) |
| `ERRO_INTERNO` | Qualquer um | Falha inesperada do servidor |
| `NAO_CONECTADO` | Qualquer um, exceto `CONNECT` | O cliente ainda não enviou um `CONNECT` aceito |
| `JA_CONECTADO` | `CONNECT` | O cliente já está conectado |
| `JA_EM_SALA` | `ROOM CREATE`, `ROOM JOIN` | O jogador já está em uma sala |
| `LIMITE_SALAS_SERVIDOR` | `ROOM CREATE` | O servidor já tem 50 salas |
| `NOME_SALA_INVALIDO` | `ROOM CREATE` | `room-name` vazio ou com mais de 20 caracteres |
| `NUM_JOGADORES_INVALIDO` | `ROOM CREATE` | `num-players` fora de 2 a 6 |
| `DIFICULDADE_INVALIDA` | `ROOM CREATE` | `dificuldade` diferente de `easy`, `medium` e `hard` |
| `RODADAS_INVALIDAS` | `ROOM CREATE` | `rounds` fora de 1 a 5 |
| `CATEGORIA_INVALIDA` | `ROOM CREATE` | `categoria` não existe e não é `qualquer` |
| `PALAVRAS_INSUFICIENTES` | `ROOM CREATE` | A categoria e a dificuldade têm menos palavras que o número de rodadas |
| `CODIGO_INVALIDO` | `ROOM JOIN` | `room-id` fora do formato de código de sala |
| `SALA_INEXISTENTE` | `ROOM JOIN` | Não existe sala com o código |
| `PARTIDA_EM_ANDAMENTO` | `ROOM JOIN`, `ROOM START` | A sala está no meio de uma partida |
| `SALA_CHEIA` | `ROOM JOIN` | A sala atingiu `num-players` |
| `SALA_NAO_PARTICIPA` | `ROOM LEAVE`, `ROOM START`, `TURN RESPONSE` | O jogador não está na sala informada |
| `APENAS_DONO` | `ROOM START` | Quem pediu não é o dono |
| `JOGADORES_INSUFICIENTES` | `ROOM START` | A sala tem menos de 2 jogadores |
| `SEM_RODADA_ATIVA` | `TURN RESPONSE` | Não há rodada em andamento (antes do início, na pausa entre rodadas ou depois do fim) |
| `NAO_E_SUA_VEZ` | `TURN RESPONSE` | Não é a vez do jogador |
| `RESPOSTA_VAZIA` | `TURN RESPONSE` | `answer` vazio |
| `LETRA_INVALIDA` | `TURN RESPONSE` (letra) | Mais de um caractere, ou um caractere que não é letra |
| `LETRA_REPETIDA` | `TURN RESPONSE` (letra) | A letra já foi tentada na rodada (com ou sem acento) |
| `PALPITE_INVALIDO` | `TURN RESPONSE` (palpite) | O palpite tem algo além de letras, espaço e hífen |

## 7. Cifragem (planejada)

A cifragem das mensagens **ainda não está implementada**: hoje todo o tráfego vai em texto puro. O protocolo já está preparado para ela:

- No `CONNECT` e no `CONNECT OK`, cliente e servidor trocam chaves públicas Curve25519 (biblioteca PyNaCl). O servidor já recusa uma chave inválida.
- Plano para a próxima versão:
  - `CONNECT`, `CONNECT OK` e `CONNECT ERROR` continuam em texto puro, porque é nelas que as chaves são trocadas.
  - Depois do `CONNECT OK`, o **corpo** de todas as mensagens passa a ser cifrado com `nacl.public.Box` (chave privada própria + chave pública do outro lado). O `Box` inclui um *nonce* aleatório e uma etiqueta de autenticação, o que também impede que alguém altere a mensagem no caminho.
  - O enquadramento não muda: os 4 bytes de tamanho continuam em claro e passam a contar o tamanho do corpo cifrado.
  - Um corpo que não puder ser decifrado será tratado como mensagem malformada (seção 5.2).
  - A versão do protocolo deverá mudar (por exemplo, `forca1.1`), para que cliente e servidor saibam se a cifragem está em uso.
