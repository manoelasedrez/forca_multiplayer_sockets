# Forca Multiplayer

Jogo de forca competitivo em rede, de 2 a 6 jogadores por sala, com cliente e servidor em Python, sockets TCP e interface no terminal.

## Integrantes

| Nome | Matrícula |
| Manoela Rodrigues Sedrez | 171896 |
| Richard de Assis | 169501 |
| Saulo Estrela | xxxxxxx |
| Sofia Botesini | xxxxxx |

## Linguagem

Python 3 — testado com **Python 3.10.12**.

## Descrição da aplicação

Os jogadores se conectam ao servidor com um apelido. Um deles cria uma **sala**, escolhendo o nome, o máximo de jogadores, o número de rodadas (1 a 5), a dificuldade e a categoria das palavras, e passa o **código** da sala (ex.: `K7XP`) para os outros entrarem. Com 2 ou mais jogadores, o dono inicia a partida.

A cada rodada o servidor sorteia uma palavra e mostra só a categoria e a quantidade de letras. Os jogadores se revezam em turnos de 30 segundos e, na sua vez, tentam **uma letra** ou **um palpite** da palavra inteira:

- letra certa: +1 ponto por ocorrência;
- palpite certo: +5 pontos e fim da rodada;
- palpite errado: −2 pontos;
- a rodada também termina quando a palavra é completada ou quando se chega a 6 erros, compartilhados por todos.

Ao fim das rodadas, vence quem tiver mais pontos (empates dividem a vitória). A sala continua aberta para uma nova partida.

O servidor é a autoridade do jogo: guarda a palavra, valida cada jogada, recusa ações inválidas, controla os prazos e mantém todos os jogadores sincronizados. Também trata mensagens malformadas e desconexões; se um jogador sair, a partida continua com os demais, ou é encerrada se sobrar só um.

Regras completas: [regras.md](regras.md).

## Arquitetura

**Cliente-servidor**, com o servidor como única autoridade sobre o jogo. Os clientes só falam com o servidor, nunca entre si.

Por que não P2P (nem híbrida):

- **A palavra é um segredo.** Em P2P, ela ficaria na máquina de algum jogador, que poderia trapacear. Aqui ela só sai do servidor no fim da rodada.
- **Um único dono do estado.** Vez, letras, erros e placar ficam num lugar só. Em P2P, as cópias do estado poderiam divergir (dois jogadores achando que é a vez deles), e seria preciso um algoritmo de consenso.
- **Validação centralizada.** Toda jogada passa pelo servidor, então um cliente alterado não consegue jogar fora da vez nem inventar pontos.
- **Conexão simples.** Cada cliente só precisa alcançar o servidor. Em P2P, os jogadores teriam que se conectar uns aos outros, o que costuma falhar atrás de NAT e firewall.
- Uma arquitetura híbrida não traria ganho: não há tráfego pesado entre jogadores (voz, vídeo) para tirar do servidor.

Custo aceito: o servidor é um ponto único de falha. Se ele cair, as partidas em andamento se perdem, já que não há persistência.

### Concorrência

| Thread | Quantidade | Função |
| --- | --- | --- |
| Aceite | 1 | Fica em `accept()` e cria uma thread para cada conexão nova |
| Cliente | 1 por conexão | Fica em `recv()`; aplica as regras e responde a cada mensagem |
| Timer | 1 por sala, quando há prazo | Encerra o turno no fim do prazo ou inicia a próxima rodada (`threading.Timer`) |

- **Por que threads e não `select`.** Cada cliente passa quase todo o tempo esperando o jogador. Com uma thread por cliente, quem está pensando não atrasa os outros, e o código de cada conexão fica sequencial: ler, tratar, responder. Com `select`, seria preciso remontar as mensagens que chegam em pedaços para cada socket e verificar os prazos dentro do laço. Na escala do jogo (até 50 salas), o custo das threads é pequeno.
- **Um único `threading.Lock`** protege todo o estado. Cada pedido é aplicado por inteiro antes do próximo, e com um Lock só não há risco de *deadlock*. O trabalho feito com ele em mãos é curto (validar e enviar mensagens pequenas).
- **Jogada e fim do prazo ao mesmo tempo:** os dois pegam o mesmo Lock, então um acontece antes do outro. Cada turno é numerado, e um timer que dispara depois do fim do turno é ignorado.
- **No cliente**, uma thread lê o teclado e outra recebe e mostra os eventos do servidor.

### Erros e desconexões

| Situação | Tratamento |
| --- | --- |
| Pedido contra as regras (fora da vez, sala cheia...) | `ERROR` com um código; nada muda no servidor |
| Mensagem malformada ou fora do protocolo | `ERROR` com `MENSAGEM_INVALIDA`; a conexão continua |
| Mensagem acima de 16 KB | `ERROR` e fechamento da conexão (não há como achar a próxima mensagem no fluxo) |
| Falha inesperada no servidor | `ERROR` com `ERRO_INTERNO`; a conexão continua |
| Cliente sai ou a conexão cai | O jogador sai da sala: a vez passa, o dono é transferido e a partida é interrompida se sobrar um |
| Cliente some sem fechar (cabo, travamento) | *Keepalive* do TCP detecta em cerca de 25 s; enquanto isso, o prazo do turno faz a partida andar |
| Servidor cai | O cliente avisa o jogador e encerra |

Detalhes de cada caso: [protocolo.md](protocolo.md), seção 5.

## Protocolos de transporte

**TCP**, com uma conexão por cliente aberta durante toda a sessão.

| O jogo precisa de | TCP | UDP |
| --- | --- | --- |
| Que nenhuma jogada se perca | Garantido | Exigiria confirmação e reenvio próprios |
| Ordem ("letra A" antes de "vez de Bob") | Garantido | Exigiria numerar e reordenar |
| Saber quando um jogador sai | Fechamento detectado; *keepalive* para quedas silenciosas | Sem conexão: exigiria "ping" próprio |
| Latência mínima | Desnecessária: turnos de 30 s | Única vantagem do UDP, sem uso aqui |

Usar UDP obrigaria a reimplementar justamente o que o TCP oferece.

Sobre o TCP roda um **protocolo de aplicação próprio** (forca1.0). Como o TCP entrega um fluxo de bytes sem fronteiras entre mensagens, cada mensagem é precedida pelo seu tamanho em 4 bytes; o corpo é texto com um comando e atributos `chave: valor`. Especificação completa: [protocolo.md](protocolo.md).

## Bibliotecas

| Biblioteca | Tipo | Uso |
| --- | --- | --- |
| `socket` | Padrão | Toda a comunicação em rede |
| `struct` | Padrão | Prefixo de tamanho das mensagens |
| `threading` | Padrão | Threads, `Lock` e `Timer` |
| `json`, `random`, `os`, `sys`, `time` | Padrão | Banco de palavras, sorteios, argumentos e pausas |
| [PyNaCl](https://pypi.org/project/PyNaCl/) 1.5.0 | **Externa** | Gera e troca chaves públicas no `CONNECT`, como preparação para a cifragem das mensagens, que está planejada. Não substitui nem abstrai os sockets. |

## Dependências

- Python 3.10 ou mais recente.
- PyNaCl:

  ```
  pip install pynacl
  ```

## Execução

Todos os comandos são executados na **raiz do projeto** (a pasta deste README).

**Servidor:**

```
python3 -m servidor.server            # porta padrão 38905
python3 -m servidor.server 40000      # outra porta
```

O servidor aceita conexões da própria máquina e da rede local. O log no terminal mostra as conexões, as mensagens recebidas, as jogadas e as desconexões. Encerre com Ctrl+C.

**Cliente** (um terminal por jogador):

```
python3 -m cliente.client                          # servidor na mesma máquina
python3 -m cliente.client 192.168.0.10             # servidor em outra máquina
python3 -m cliente.client 192.168.0.10 40000       # endereço e porta
```

- Para jogar em máquinas diferentes, use o IP da máquina do servidor (veja com `ip addr` no Linux, `ipconfig` no Windows ou `ifconfig` no macOS) e libere a porta TCP no firewall dela.
- No cliente, informe o apelido e use o menu numérico:
  - **fora de sala:** criar ou entrar;
  - **na sala:** iniciar, se for o dono, ou sair;
  - **em partida:** letra, palpite ou sair.
- Durante a partida, a tela é redesenhada a cada turno, com a forca, a palavra, o placar e as últimas jogadas. Em terminais sem suporte a códigos ANSI, desligue as cores e a limpeza de tela com `USAR_CORES = False` e `LIMPAR_TELA = False` em `cliente/client.py`.

## Como testar

Abra um servidor e três clientes (Ana, Bob e Caio) e siga os passos abaixo. O log do servidor mostra cada mensagem recebida, cada jogada e cada desconexão.

1. **Vários participantes:** Ana cria uma sala (máximo 3, 2 rodadas); Bob e Caio entram com o código; Ana inicia. Cada jogada aparece para todos.
2. **Operações inválidas:** Bob joga na vez da Ana (`nao e sua vez`); alguém repete uma letra, joga `ab` como letra ou entra com o código `ZZZZ`.
3. **Simultaneidade:** abra mais dois clientes e jogue outra partida em outra sala ao mesmo tempo.
4. **Desconexão:** feche o terminal de Bob na vez dele (a vez passa a Caio e os pontos de Bob saem do placar); depois feche o da Ana (Caio vira dono e a partida termina como interrompida).
5. **Nova partida e nova conexão:** ao fim, conecte um cliente novo, entre na sala e o dono inicia outra partida.
6. **Queda do servidor:** encerre o servidor com Ctrl+C; os clientes avisam e encerram.

## Estrutura

```
README.md                    este arquivo
protocolo.md                 especificação do protocolo de aplicação
regras.md                    regras do jogo
protocol/protocol.py         mensagens, enquadramento e leitura do socket
servidor/server.py           conexões, salas, partidas e validação
servidor/banco_palavras.py   banco de palavras, sorteio e tratamento de acentos
cliente/client.py            menu, painel da partida e eventos
dados/palavras.json          321 palavras em 10 categorias
```

## Uso de Inteligência Artificial

Foram utilizadas ferramentas de Inteligência Artificial (ChatGPT, da OpenAI, e Claude Code, da Anthropic) nas seguintes etapas:

- **Concepção da ideia:** discussão da proposta do jogo e busca de aplicações parecidas como referência.
- **Estudo de protocolos:** entender como funciona o protocolo HTTP, que serviu de inspiração para o formato das mensagens (comando na primeira linha e atributos `chave: valor`).
- **Chaves públicas e privadas:** entender o funcionamento da criptografia de chave pública, para avaliar se fazia sentido usá-la e como encaixá-la no protocolo criado, e entender o funcionamento da biblioteca PyNaCl (geração e troca de chaves, cifragem com `Box`) para aplicá-la no protocolo.
- **Desenho do protocolo:** perguntas sobre o protocolo para definir as mensagens e o fluxo de comunicação entre cliente e servidor.
- **Concorrência:** entender como usar um *mutex* para proteger o estado compartilhado entre as threads, como evitar condições de disputa (*race conditions*) e *deadlocks* neste servidor, e como fazer isso em Python com `threading.Lock`.
- **Testes:** criação de testes do código para encontrar erros em situações específicas, como mensagens malformadas, jogadas simultâneas, tempo esgotado e desconexões no meio da partida. Os testes foram usados durante o desenvolvimento e não fazem parte desta entrega.
- **Interface no terminal:** design e estruturação da exibição das informações do jogo no terminal, como o painel da partida (forca, palavra, letras usadas, erros, placar e últimas jogadas), as telas de fim de rodada e de fim de jogo, o espaçamento e as cores.
- **Documentação:** documentação geral do código e redação dos documentos de regras ([regras.md](regras.md)), da especificação do protocolo ([protocolo.md](protocolo.md)) e deste README.

As regras do jogo, o fluxo da interface e o funcionamento da partida foram definidos pelo grupo antes de serem passados às ferramentas, que foram usadas para organizá-los e descrevê-los.
