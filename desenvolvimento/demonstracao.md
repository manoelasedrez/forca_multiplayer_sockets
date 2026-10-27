# Roteiro de demonstração

Passos para mostrar cada situação que a avaliação pode pedir. O servidor e os clientes rodam a partir da pasta `entrega/`; os testes e o cliente bruto, a partir da raiz do repositório.

## Preparação

1. Abra um terminal para o servidor e deixe-o visível: o log mostra cada mensagem recebida, cada jogada e cada desconexão.

   ```
   cd entrega
   python3 -m servidor.server
   ```

2. Abra um terminal para cada jogador (Ana, Bob e Caio):

   ```
   cd entrega
   python3 -m cliente.client                  # mesma máquina
   python3 -m cliente.client 192.168.0.10     # outra máquina: use o IP do servidor
   ```

   Para descobrir o IP do servidor: `ip addr` (Linux), `ipconfig` (Windows) ou `ifconfig` (macOS). O firewall da máquina do servidor precisa liberar a porta TCP 38905.

3. Para provocar mensagens inválidas, use o script `desenvolvimento/testes/cliente_bruto.py` (seção 5 deste roteiro).

## 1. Comunicação entre múltiplos participantes

1. **Ana:** 1 (Criar sala). Nome `Demo`, máximo 3 jogadores, 2 rodadas, `easy`, categoria 0 (qualquer). Anote o código.
2. **Bob** e **Caio:** 2 (Entrar em sala) com o código. Todos veem a lista de jogadores atualizada.
3. **Ana:** 3 (Iniciar partida). Os três recebem o painel com a forca, a categoria e de quem é a vez.
4. Joguem algumas letras. A jogada de cada um aparece para todos, com pontos, erros e letras usadas.

**O que mostrar:** cada evento sai do servidor para toda a sala; o log do servidor mostra a ordem em que as mensagens chegaram.

## 2. Execução simultânea de operações

- **Várias salas ao mesmo tempo:** enquanto a sala da Ana joga, abra mais dois clientes, crie outra sala e jogue nela. As duas partidas andam ao mesmo tempo, e uma não interfere na outra.
- **Jogadas ao mesmo tempo:** peça para Bob tentar jogar (opção 4) na vez da Ana. O servidor recusa (`nao e sua vez`) e a jogada da Ana segue normalmente.
- **Teste automatizado:** `python3 -m unittest discover desenvolvimento/testes -k simultaneas -k varias_salas` executa 5 partidas em paralelo, em threads diferentes, e duas jogadas enviadas no mesmo instante.

**O que explicar:** uma thread por cliente e um `Lock` que faz cada pedido ser aplicado por inteiro antes do próximo ([arquitetura.md](arquitetura.md), seção 4).

## 3. Mensagens e operações inválidas (pelo cliente normal)

| Ação | Resultado esperado |
| --- | --- |
| Entrar com o código `ABC` | `codigo invalido, use 4 caracteres` |
| Entrar com o código `ZZZZ` | `sala inexistente` |
| Criar uma sala estando em outra | O cliente avisa; o servidor recusaria com `JA_EM_SALA` |
| Bob digita 3 (Iniciar partida) | A opção não aparece no menu dele, mas o pedido é enviado e o servidor recusa: `apenas o dono da sala pode iniciar` |
| Entrar numa sala com partida em andamento | `partida em andamento, tente novamente quando terminar` |
| Na sua vez, jogar `ab` como letra | `envie uma unica letra` (a vez continua sua) |
| Na sua vez, repetir uma letra (ou `Ã` depois de `A`) | `letra ja usada` |
| Palpite `uva!` | `use apenas letras, espaco e hifen` |
| Criar sala `easy` na categoria Profissões | `so ha 0 palavras nesta categoria e dificuldade` |
| Conectar com um nome já em uso, ou com vírgula | Conexão recusada com o motivo |

## 4. Desconexão de um participante

Com a partida em andamento e três jogadores:

1. **Na vez de Bob, feche o terminal dele** (ou Ctrl+C). O servidor registra a desconexão, a vez passa para Caio e todos veem a lista atualizada. Os pontos de Bob saem do placar.
2. **Feche o terminal da Ana (dona).** Caio passa a ser o dono. Como sobra só um jogador, a partida termina como **interrompida**, sem vencedor.
3. **Derrube o servidor (Ctrl+C)** com clientes conectados. Cada cliente mostra "Conexão com o servidor perdida" e encerra ao apertar Enter.

Variação: sair pelo menu (opção 6) tem o mesmo efeito, com confirmação antes.

**Queda silenciosa** (opcional, com duas máquinas): desligue o Wi-Fi ou o cabo do cliente. Em cerca de 25 segundos o *keepalive* do TCP detecta a queda e o servidor aplica a desconexão. Enquanto isso, o prazo do turno continua passando a vez.

## 5. Mensagens fora do protocolo

O cliente normal só envia mensagens corretas. Para mostrar como o servidor reage a mensagens malformadas, use o cliente bruto, que envia bytes escolhidos à mão:

```
python3 desenvolvimento/testes/cliente_bruto.py [endereco] [porta]
```

Ele conecta, executa cada caso abaixo e mostra a resposta do servidor. Depois do `CONNECT` aceito, ele cifra os corpos com a chave da conexão (como o cliente normal), para o servidor conseguir decifrá-los e avaliar o conteúdo:

| Caso | Resposta esperada |
| --- | --- |
| Pedido antes do `CONNECT` | `ERROR` `NAO_CONECTADO` |
| `CONNECT` com a versão antiga (`forca1.0`, sem cifragem) | `CONNECT ERROR` `versao nao suportada, use forca1.1` |
| `CONNECT` com chave pública inválida | `CONNECT ERROR` `chave publica invalida` |
| Pedido válido, mas enviado sem cifrar depois do `CONNECT` | `ERROR` `MENSAGEM_INVALIDA` ("nao pode ser decifrada"), conexão continua |
| Pedido cifrado com a chave de outra pessoa | `ERROR` `MENSAGEM_INVALIDA`, conexão continua |
| Pedido cifrado e adulterado no caminho (um bit trocado) | `ERROR` `MENSAGEM_INVALIDA`, conexão continua |
| Comando desconhecido (`PULAR VEZ`) | `ERROR` `MENSAGEM_INVALIDA`, conexão continua |
| `ROOM JOIN` sem `room-id` | `ERROR` `MENSAGEM_INVALIDA`, conexão continua |
| Corpo que não é UTF-8 | `ERROR` `MENSAGEM_INVALIDA`, conexão continua |
| Mensagem que só o servidor envia (`ROOM CREATE OK`) | `ERROR` `MENSAGEM_INVALIDA` |
| `CONNECT` repetido | `ERROR` `JA_CONECTADO` |
| Tamanho anunciado de 2 GB | `ERROR` `MENSAGEM_INVALIDA` e a conexão é fechada |

## 5.1. Cifragem

Para mostrar que o tráfego vai cifrado:

1. **Log do servidor:** cada conexão aceita aparece como `Conexão com ... estabelecida. Usuário: ana (mensagens cifradas)`.
2. **Captura de tráfego** (Linux, com permissão de administrador), durante uma partida:

   ```
   sudo tcpdump -i any -A port 38905
   ```

   Só o `CONNECT` e o `CONNECT OK` aparecem legíveis, com as chaves públicas em Base64. Todo o resto (salas, letras, palpites, placar) aparece como bytes sem sentido. O Wireshark mostra o mesmo, com filtro `tcp.port == 38905`.
3. **Casos 5 a 7 do cliente bruto:** mensagem em claro, cifrada com outra chave e adulterada. As três são recusadas e a conexão continua.
4. **Teste automatizado:** `python3 -m unittest discover desenvolvimento/testes -k cifr -k claro -k adulterada` verifica que os bytes no fio não contêm o texto, que cada cliente tem sua própria chave e que mensagens em claro, com outra chave ou adulteradas são recusadas.

**O que explicar:** troca de chaves públicas no `CONNECT`; cada lado combina a própria chave privada com a pública do outro e chega à mesma chave secreta (Diffie-Hellman) sem que ela trafegue; o `Box` cifra e autentica cada corpo, com um nonce aleatório por mensagem ([protocolo.md](../entrega/protocolo.md), seção 7).

## 6. Novas conexões e novas partidas

- Com uma partida em andamento, conecte um cliente novo: ele entra normalmente no servidor, cria uma sala ou espera a partida acabar para entrar.
- Ao fim da partida, a sala volta a aceitar jogadores. O novo jogador entra e o dono inicia **outra partida** (opção 3), com placar zerado e palavras novas.

## 7. Situações de erro previstas no protocolo

Todas as recusas estão listadas, com código, em [protocolo.md](../entrega/protocolo.md), seção 6. Os testes automatizados cobrem cada uma:

```
python3 -m unittest discover desenvolvimento/testes
```

## Perguntas que podem surgir

| Pergunta | Onde está a resposta |
| --- | --- |
| Por que cliente-servidor e não P2P? | [arquitetura.md](arquitetura.md), seção 2 |
| Por que TCP e não UDP? | [arquitetura.md](arquitetura.md), seção 3 |
| Como o servidor sabe onde termina cada mensagem? | [protocolo.md](../entrega/protocolo.md), seção 2.1; `receive_exact` em `entrega/protocol/protocol.py` |
| Por que threads e não `select`? O que o Lock protege? | [arquitetura.md](arquitetura.md), seção 4 |
| O que acontece se um jogador cair na vez dele? | `sair_sala` em `entrega/servidor/server.py` |
| Como o turno expira? | `enviar_turno` e `tempo_esgotado` em `entrega/servidor/server.py` |
| Para que serve o PyNaCl? Como funciona a cifragem? | [protocolo.md](../entrega/protocolo.md), seção 7; `cifrar` e `decifrar` em `entrega/protocol/protocol.py` |
| Por que o `CONNECT` não é cifrado? | É nele que as chaves públicas são trocadas: antes disso, nenhum lado tem a chave do outro |
| A chave privada trafega? | Não. Só as públicas; a chave secreta de cada conexão é calculada dos dois lados (Curve25519) |
| A cifragem tem limitações? | Sim: não confere a identidade do servidor (*man-in-the-middle*) nem impede reenvio de mensagens capturadas ([protocolo.md](../entrega/protocolo.md), seção 7.6) |

## Gerar o pacote de entrega

Na raiz do repositório, com as matrículas do grupo:

```
sh desenvolvimento/empacotar.sh 171896 MATRICULA2
```

O script copia o conteúdo de `entrega/` (sem arquivos de cache) para uma pasta com o nome do pacote e gera `171896_MATRICULA2.tar.gz` na raiz do repositório.
