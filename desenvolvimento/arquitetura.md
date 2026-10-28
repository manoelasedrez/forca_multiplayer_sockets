# Arquitetura e decisões de projeto

> Versão detalhada, para estudo do grupo. O resumo que vai na entrega está no [README da entrega](../entrega/README.md).

Este documento justifica as decisões: arquitetura, protocolo de transporte e mecanismo de concorrência. Também descreve como os erros e as desconexões são tratados.

- Regras do jogo: [regras.md](../entrega/regras.md).
- Protocolo de aplicação: [protocolo.md](../entrega/protocolo.md).

## 1. Visão geral

```
 ┌───────────┐      TCP       ┌──────────────────────────────────────────┐
 │ Cliente A │◄──────────────►│ Servidor                                 │
 └───────────┘                │                                          │
 ┌───────────┐      TCP       │  thread de aceite ── accept()            │
 │ Cliente B │◄──────────────►│  1 thread por cliente ── recv() + regras │
 └───────────┘                │  timers (turnos e pausas)                │
 ┌───────────┐      TCP       │  estado: usuários, salas, partidas       │
 │ Cliente C │◄──────────────►│  (protegido por um Lock)                 │
 └───────────┘                └──────────────────────────────────────────┘
```

| Componente | Arquivo | Responsabilidade |
| --- | --- | --- |
| Protocolo | `protocol/protocol.py` | Classes das mensagens, codificação, enquadramento e leitura do socket. Usado pelos dois lados. |
| Servidor | `servidor/server.py` | Aceita conexões, guarda todo o estado do jogo, valida e aplica as jogadas, envia os eventos às salas. |
| Banco de palavras | `servidor/banco_palavras.py` | Carga e validação do arquivo de palavras, sorteio, comparação sem acentos. |
| Cliente | `cliente/client.py` | Menu no terminal, painel da partida e exibição dos eventos. Não decide nada do jogo. |

## 2. Arquitetura: cliente-servidor

**Decisão:** cliente-servidor, com o servidor como única autoridade sobre o estado do jogo.

**Justificativa:**

- **Um jogo de forca precisa de um segredo.** A palavra não pode ficar com nenhum jogador. Em P2P, algum participante (ou todos) teria a palavra na sua máquina e poderia trapacear. No cliente-servidor, a palavra só sai do servidor no fim da rodada.
- **Um único dono do estado.** Vez, letras usadas, erros e placar ficam em um lugar só. Não é preciso resolver conflitos entre cópias do estado, como "dois jogadores acham que é a vez deles", que em P2P exigiria um algoritmo de consenso.
- **Validação centralizada.** Toda jogada passa pelo servidor, que aplica as regras. Um cliente alterado não consegue jogar fora da vez nem inventar pontos.
- **Conexão simples para o jogador.** Cada cliente conhece só o endereço do servidor. Em P2P, cada jogador precisaria alcançar os outros diretamente, o que costuma falhar atrás de NAT e firewalls.
- **Sincronização natural.** O servidor recebe a jogada e envia o resultado para toda a sala, na mesma ordem para todos.

**Custo aceito:** o servidor é um ponto único de falha. Se ele cair, as partidas em andamento são perdidas (não há persistência, ver [pendencias.md](pendencias.md)). Para um jogo de partidas curtas, isso é aceitável.

Uma arquitetura **híbrida** não traria vantagem: não há tráfego pesado entre jogadores (como voz ou vídeo) que valesse a pena tirar do servidor.

## 3. Transporte: TCP

**Decisão:** somente TCP, com uma conexão por cliente mantida aberta durante toda a sessão.

**Justificativa:**

| Necessidade do jogo | TCP | UDP |
| --- | --- | --- |
| Nenhuma jogada pode se perder (uma letra perdida dessincroniza a partida) | Entrega garantida | Seria preciso implementar confirmação e reenvio |
| A ordem importa ("letra A" antes de "vez de Bob") | Entrega em ordem | Seria preciso numerar e reordenar |
| Mensagens sem duplicação (uma jogada não pode valer duas vezes) | Garantido | Seria preciso detectar duplicatas |
| Saber quando um jogador saiu | Fechamento da conexão é detectado; *keepalive* detecta quedas silenciosas | Não há conexão: seria preciso um "ping" próprio |
| Baixa latência a cada milissegundo | Desnecessário: o jogo é por turnos de 30 s | Vantagem do UDP, sem uso aqui |

O UDP só compensaria em jogos de ação em tempo real, em que um pacote atrasado já não serve e é melhor perdê-lo. Na forca, toda mensagem precisa chegar, e na ordem. Usar UDP obrigaria a reimplementar justamente o que o TCP já oferece.

**Consequência:** como o TCP é um fluxo de bytes sem fronteiras entre mensagens, o protocolo prefixa cada mensagem com seu tamanho em 4 bytes ([protocolo.md](../entrega/protocolo.md), seção 2.1). A leitura repete o `recv()` até completar o tamanho anunciado, porque uma leitura pode devolver só parte da mensagem.

## 4. Concorrência: uma thread por cliente e um Lock

**Decisão:**

| Thread | Quantidade | O que faz |
| --- | --- | --- |
| Principal | 1 | Inicia o servidor e espera o Ctrl+C |
| Aceite | 1 | Fica em `accept()`; para cada conexão nova, cria a thread do cliente |
| Cliente | 1 por conexão | Fica em `recv()`; para cada mensagem, aplica as regras e responde |
| Timer | 1 por sala, quando há prazo correndo | Encerra o turno quando o tempo acaba, ou inicia a próxima rodada depois da pausa (`threading.Timer`) |

Todo o estado compartilhado (usuários, salas, partidas) é protegido por **um único `threading.Lock`**. Cada mensagem é tratada inteira com o Lock em mãos, assim como cada disparo de timer.

**Justificativa:**

- **Por que threads.** Cada cliente passa a maior parte do tempo bloqueado em `recv()`, esperando o jogador. Com uma thread por cliente, um jogador pensando não atrasa os outros. O código de cada conexão fica sequencial e fácil de ler: ler, tratar, responder.
- **Por que não `select`.** Multiplexar com `select` num laço único evitaria threads, mas exigiria guardar, para cada socket, os bytes de mensagens incompletas e montar as mensagens aos pedaços. Os prazos de turno também teriam que ser verificados dentro do laço. Para até 50 salas e poucas centenas de jogadores, o custo das threads é pequeno e o código fica mais simples de explicar e de manter.
- **Por que um Lock só.** Uma jogada mexe em várias estruturas ao mesmo tempo (vez, placar, letras, timer). Um Lock global garante que cada pedido é aplicado por inteiro antes do próximo, sem risco de *deadlock* entre locks diferentes. O trabalho feito com o Lock em mãos é curto (validar e enviar poucas mensagens pequenas), então a disputa pelo Lock não é um gargalo nesta escala. Locks por sala só compensariam com muito mais salas ativas.
- **Timers e jogadas simultâneas.** Uma jogada e o fim do prazo podem acontecer quase juntos. Os dois pegam o Lock, então um acontece antes do outro. Cada turno tem um número; um timer que dispara depois que o turno já acabou percebe que o número mudou e não faz nada.
- **No cliente**, há duas threads: a principal lê o teclado (`input()`) e a outra fica em `recv()`, mostrando os eventos do servidor assim que chegam.

**Limitação conhecida:** o envio é feito com o Lock em mãos. Um cliente que pare de ler os dados (sem fechar a conexão) poderia, em tese, encher o buffer de envio do TCP e travar o servidor no `sendall()`. Com mensagens de poucas centenas de bytes isso exigiria milhares de eventos acumulados, o que não ocorre em uso normal. Está registrado em [pendencias.md](pendencias.md).

## 5. Tratamento de erros e desconexões

| Situação | Tratamento |
| --- | --- |
| Pedido que viola uma regra | `ERROR` com código; o estado não muda ([regras.md](../entrega/regras.md)) |
| Mensagem malformada | `ERROR` com `MENSAGEM_INVALIDA`; a conexão continua ([protocolo.md](../entrega/protocolo.md), seção 5) |
| Mensagem que não pode ser decifrada (em claro, outra chave, adulterada) | `ERROR` com `MENSAGEM_INVALIDA`; a mensagem é descartada e a conexão continua |
| Tamanho anunciado acima de 16 KB | `ERROR` e fechamento da conexão, porque não há como achar a próxima mensagem |
| Erro inesperado no servidor | `ERROR` com `ERRO_INTERNO`; a thread do cliente continua viva |
| Cliente fecha a conexão ou ela cai | O `recv()` falha; o jogador sai da sala como se tivesse pedido (passa a vez, transfere o dono, interrompe a partida se sobrar um) |
| Cliente some sem fechar (cabo, travamento) | *Keepalive* do TCP: depois de 10 s sem tráfego, o sistema testa a conexão a cada 5 s; após 3 falhas (cerca de 25 s), o `recv()` falha e o caso anterior se aplica. Enquanto isso, o prazo do turno faz a partida andar. |
| Envio para um cliente que já caiu | O erro é ignorado; a thread daquele cliente percebe a queda e faz a limpeza |
| Servidor cai | O cliente avisa o jogador e encerra |
| Encerramento do servidor (Ctrl+C) | Cancela os timers e fecha todas as conexões com o Lock em mãos, para não competir com as threads dos clientes |

## 6. Cifragem

**Decisão:** cifrar o corpo de todas as mensagens depois do `CONNECT OK`, com o `Box` do PyNaCl (Curve25519 + XSalsa20 + Poly1305). Detalhes do formato em [protocolo.md](../entrega/protocolo.md), seção 7.

**Onde fica no código:**

| Parte | Onde |
| --- | --- |
| Cifrar e decifrar um corpo | `cifrar` e `decifrar` em `protocol/protocol.py` |
| Enviar e receber com ou sem cifra | `send_message(sock, msg, box)` e `receive_message(sock, box)`: com `box = None`, texto puro |
| Uma `Box` por conexão no servidor | `self.boxes` (socket → `Box`), criada ao aceitar o `CONNECT`, usada em `responder()` e em `handle_cliente()` |
| `Box` do cliente | `self.box`, criada ao receber o `CONNECT OK`, usada em `enviar()` e na thread de recebimento |

**Justificativa:**

- **Por que chave pública, e não uma senha combinada.** Não há como os jogadores e o servidor combinarem um segredo antes. Com chaves públicas, cada lado manda só a sua chave pública, e o acordo Diffie-Hellman dá aos dois a mesma chave secreta sem que ela trafegue.
- **Por que o `Box` e não montar a cifra à mão.** O `Box` junta cifra e autenticação numa operação só, com nonce aleatório. Montar isso à mão (escolher cifra, modo, nonce e autenticação) é fácil de errar.
- **Por que só o corpo.** O tamanho precisa ficar em claro para quem recebe saber quantos bytes ler; o enquadramento continua igual ao da versão sem cifra.
- **Por que o `CONNECT` em claro.** É nele que as chaves são trocadas; antes disso, nenhum lado tem a chave do outro.
- **Concorrência:** a `Box` de uma conexão é usada pela thread daquele cliente (para decifrar o que chega) e pelas threads que enviam com o `Lock` em mãos (para cifrar). O `Box` não guarda estado entre chamadas (a chave secreta é fixa e cada mensagem sorteia o próprio nonce), então pode ser usado por duas threads ao mesmo tempo sem proteção extra.

**Limitações** (registradas em [pendencias.md](pendencias.md)): o cliente não confere a identidade do servidor (*man-in-the-middle*) e o servidor não impede o reenvio de uma mensagem cifrada capturada.

## 7. Endereçamento

- O servidor escuta em `0.0.0.0` (todas as interfaces), na porta `38905` ou na porta passada como argumento. Assim, aceita conexões da própria máquina e da rede local.
- Se a porta estiver ocupada, o servidor tenta a seguinte.
- O cliente recebe o endereço e a porta do servidor como argumentos (padrão `127.0.0.1:38905`).
- Cada conexão é identificada no servidor pelo par `IP:porta` do cliente, que é único enquanto a conexão existir.

## 8. Bibliotecas

| Biblioteca | Tipo | Uso |
| --- | --- | --- |
| `socket` | Padrão | Toda a comunicação: `bind`, `listen`, `accept`, `connect`, `sendall`, `recv`, `setsockopt` |
| `struct` | Padrão | Prefixo de tamanho de 4 bytes (`"!I"`, big-endian) |
| `threading` | Padrão | Threads, `Lock` e `Timer` |
| `json` | Padrão | Leitura do banco de palavras |
| `random` | Padrão | Sorteio de palavras e de códigos de sala |
| `unittest` | Padrão | Testes automatizados |
| PyNaCl | Externa | Criptografia: pares de chaves Curve25519 e cifragem/autenticação do corpo das mensagens com `Box` ([protocolo.md](../entrega/protocolo.md), seção 7). Só transforma bytes; a rede é feita só com `socket`. |
