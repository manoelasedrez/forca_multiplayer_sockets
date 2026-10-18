# Participação em várias salas — Forca Multiplayer

Planejamento do item 9. Complementa [regras.md](regras.md) 2.4 e [salas.md](salas.md).

Os nomes de comandos, operações e códigos são **provisórios** até a especificação do protocolo.

## 9.1. Uma conexão, várias salas

- Cada cliente abre **uma única conexão TCP** com o servidor, e essa conexão fica associada a **todas** as salas do jogador (no máximo 5; ver [salas.md](salas.md) 8.11).
- O servidor mantém, por jogador conectado: a conexão, o apelido e o conjunto de códigos das salas em que ele está. Cada sala mantém a lista de seus participantes (referências aos jogadores).
- O servidor **nunca deduz a sala a partir da conexão**: toda mensagem referente a uma sala informa o código dela (9.3), e toda mensagem enviada pelo servidor sobre uma sala também o informa.
- Quando a conexão cai, o servidor percorre as salas do jogador e aplica a cada uma a regra de saída ([salas.md](salas.md) 8.3).

**Consequências para a concorrência** (proposta, a confirmar quando o mecanismo for escolhido):
- Vários eventos (turno em uma sala, tempo esgotado em outra, jogada de um adversário) podem tentar escrever na mesma conexão ao mesmo tempo. Cada conexão precisa de **um único ponto de escrita** (um bloqueio de envio ou uma fila de saída atendida por uma só thread), para que mensagens de salas diferentes não se misturem no meio do fluxo TCP.
- Cada sala tem seu próprio bloqueio. Regra para evitar impasses: **nunca manter bloqueios de duas salas ao mesmo tempo**; a ordem de aquisição é sala → jogador → escrita da conexão.
- O recebimento é feito por uma thread por conexão, que despacha cada mensagem para a sala indicada nela.

## 9.2. Escolha da sala visualizada

- A **sala visualizada** é um conceito **só do cliente**. O servidor não sabe qual sala está na tela e envia eventos de todas as salas do jogador.
- Isso elimina qualquer disputa entre "trocar de sala" e "receber evento": trocar a tela é uma decisão local.
- O cliente guarda, para cada sala, o último estado conhecido e os últimos 20 eventos. Ao trocar, mostra imediatamente esse estado. Se houver dúvida, `/estado` pede um retrato atual ao servidor.
- A troca é feita **somente por comando do jogador**:
  - `/salas`: mostra a lista (9.4).
  - `/sala K7XP` ou `/sala 2`: passa a visualizar a sala pelo código ou pelo número da lista.
  - `/proxima`: vai para a sala com ação pendente e menos tempo restante (9.8).
- Trocas automáticas acontecem apenas em dois casos: logo após o jogador criar ou entrar em uma sala (ela passa a ser a visualizada) e quando a sala visualizada deixa de existir para ele (saída, remoção). Nesse segundo caso, o cliente escolhe a sala com ação pendente e, se não houver, a primeira da lista; sem salas, mostra o menu.
- **Nunca** há troca automática enquanto o jogador está digitando um comando (9.7).

## 9.3. Associação de cada comando à sala correta

Comandos do jogador no cliente:

| Comando | Efeito | Sala usada |
| --- | --- | --- |
| `/criar` | Cria uma sala | Nenhuma (global) |
| `/entrar K7XP` | Entra na sala | A do código digitado |
| `/salas` | Lista as salas do jogador | Nenhuma (global) |
| `/sala K7XP` ou `/sala 2` | Muda a visualização | Só no cliente |
| `/proxima` | Visualiza a sala com ação mais urgente | Só no cliente |
| `/iniciar` | Inicia partida | Visualizada, ou `@COD` |
| `/letra X` (atalho `/l X`) | Tenta uma letra | Visualizada, ou `@COD` |
| `/palavra TEXTO` (atalho `/p TEXTO`) | Tenta a palavra completa | Visualizada, ou `@COD` |
| `/estado` | Pede o retrato da sala | Visualizada, ou `@COD` |
| `/sair` | Sai da sala (com confirmação) | Visualizada, ou `@COD` |
| `/ajuda`, `/fechar` | Ajuda; encerra o cliente | Nenhuma |

Regras:
1. Antes de qualquer comando de uma sala, o jogador pode escrever `@K7XP` para escolher outra sala **apenas naquele comando**, sem mudar a visualização. Exemplo: `@M3QB /letra A`.
2. Sem `@`, o comando vai para a sala visualizada.
3. Toda mensagem de rede referente a uma sala carrega o campo com o código dela. O servidor valida em cada pedido: se o jogador não participa da sala, a resposta é `SALA_NAO_PARTICIPA`, sem efeito.
4. Toda resposta e todo evento do servidor também carregam o código. O cliente usa esse código para decidir se a informação aparece na tela (sala visualizada) ou como aviso (9.5).
5. Pedidos e respostas devem ter um identificador de pedido para casar uma resposta com o comando que a originou, mesmo quando os eventos de várias salas chegam intercalados. O formato será definido no protocolo.

## 9.4. Informações da lista de salas

Exemplo de tela do jogador Manu:

```
Suas salas (3)
 #  Código  Situação          Jogadores                          Seus pontos   Vez
 1  K7XP    Em partida 2/5    Manu, Sofia(dono), João            4             VOCÊ (22s)
 2  M3QB    Em partida 4/5    Ana(dono), Pedro, Manu             -1            Pedro  +3
 3  R9TD    Aguardando        Manu(dono)                         -             -
                                       Sala visualizada: 1 (K7XP)    Ação pendente: K7XP
```

| Coluna | Conteúdo |
| --- | --- |
| Código | Código da sala |
| Situação | `Aguardando`, `Em partida n/5` (rodada atual), `Encerrada` ou `Interrompida` |
| Jogadores | Todos os apelidos, na ordem de entrada, com `(dono)` para o responsável |
| Seus pontos | Pontuação do jogador na sala (`-` se não há partida) |
| Vez | Apelido do jogador da vez; `VOCÊ (segundos)` quando é a vez dele; `-` fora de partida |
| Linha final | Qual sala está visualizada e em quais há ação pendente |
| Indicador `+n` | Quantidade de avisos de baixa prioridade não vistos naquela sala (9.5) |

O servidor envia, a cada sala, os **segundos restantes** do turno (e não o horário do fim), para que os relógios do cliente e do servidor não precisem estar sincronizados. O cliente conta o tempo localmente e se corrige a cada evento recebido; a decisão final é sempre do relógio do servidor (9.6).

## 9.5. Avisos sobre salas não visualizadas

Eventos da sala visualizada são exibidos normalmente, na tela dela. Eventos de **outras** salas viram avisos, em três níveis:

| Nível | Quando | O que o cliente faz | Exemplos |
| --- | --- | --- | --- |
| **Alto** | Exige ou muda a ação do jogador | Imprime na hora, em linha própria | "É a sua vez" · "Restam 10 s da sua vez" · "Sua vez passou por tempo esgotado" · "Partida iniciada" · "Rodada encerrada" (resumo em uma linha) · "Partida encerrada/interrompida" · "Você é o novo responsável" |
| **Médio** | Muda quem está na sala | Imprime na hora, em linha curta | "Sofia entrou" · "João saiu" |
| **Baixo** | Andamento entre outros jogadores | Não imprime; só soma ao indicador `+n` da lista | Letras e palavras tentadas por outros, passagem de vez entre outros jogadores |

Formato: `[K7XP] É a sua vez! 30 s. Use @K7XP /letra X ou /sala K7XP.`

Regras:
- O aviso nunca apaga o que o jogador estava digitando: o cliente imprime o aviso em linha própria e reexibe o prompt com o texto parcial (por exemplo, usando o buffer de linha do `readline`).
- Ao entrar em uma sala, o cliente mostra o estado atual e os últimos eventos guardados (9.2), para que nada de baixa prioridade se perca.
- O aviso "Restam 10 s" só é enviado para quem está com a vez em sala **não visualizada**; na sala visualizada o contador já está na tela.

## 9.6. Cronômetros continuam em todas as salas

- O prazo de 30 segundos pertence à **sala** e é controlado pelo **servidor**; nenhum cliente o inicia, pausa ou reinicia. Trocar a sala visualizada não tem nenhum efeito sobre ele.
- Duas salas têm dois cronômetros independentes, ambos contando ao mesmo tempo, mesmo que o jogador esteja olhando uma só.
- Esgotado o prazo, vale a regra de [regras.md](regras.md) 4.8: a vez passa, sem perda de pontos nem erro, e o jogador recebe o aviso de nível alto (9.5).
- Uma jogada que chegue ao servidor depois do prazo é recusada, ainda que tenha sido enviada antes; vale o relógio do servidor.
- A contagem na tela do cliente é apenas informativa.

## 9.7. Evitar que uma entrada vá para a sala errada

Nenhuma medida elimina totalmente o erro do próprio jogador (uma letra certa enviada à sala errada é, para o servidor, uma jogada válida). Por isso a proteção está em várias camadas:

1. **Prompt com a sala:** o prompt sempre mostra o código da sala visualizada, por exemplo `[K7XP] 22s> `.
2. **Sala fixada ao exibir o prompt:** o comando sem `@` usa a sala que aparecia no prompt **no momento em que ele foi exibido**, e não a que estiver visualizada quando o jogador apertar Enter. Assim, nenhuma troca interna altera um comando em digitação.
3. **Sem troca automática durante a digitação** (9.2), e avisos não alteram a sala do prompt.
4. **Comando explícito obrigatório:** texto sem `/` ou `@` **nunca** é enviado ao servidor; o cliente mostra "Comando desconhecido, digite /ajuda". Uma letra solta jamais vira jogada.
5. **`@COD` para agir em outra sala**, sem mudar a visualização.
6. **Confirmação** antes de `/sair` durante partida, mostrando o código da sala.
7. **Servidor valida sempre:** sala inexistente ou da qual o jogador não faz parte → `SALA_NAO_PARTICIPA`; fora da vez → recusado sem penalidade ([regras.md](regras.md) 4.7).
8. **Eco do código na resposta:** a confirmação de cada jogada sempre aparece com o código da sala (`[K7XP] Letra A: 3 ocorrências, +3 pontos`), facilitando perceber o engano.

Risco residual: o jogador digita `/letra A` olhando a sala errada, em um momento em que também é a vez dele naquela sala. O servidor não tem como saber que foi engano.

## 9.8. Duas salas exigindo ação do mesmo jogador ao mesmo tempo

**Decisão:** as salas são totalmente independentes. O servidor **não coordena, não enfileira e não prioriza** entre salas ([regras.md](regras.md) 2.3: uma sala não pode alterar outra).

- Cada sala mantém seu prazo de 30 segundos. Os dois cronômetros correm ao mesmo tempo.
- O jogador pode agir em qualquer ordem, em qualquer das duas, inclusive com `@COD` sem trocar de tela (9.3).
- Se não conseguir agir em uma a tempo, ela segue a regra de tempo esgotado (a vez passa, sem penalidade) sem afetar a outra.
- Para ajudar o jogador:
  - A linha de status mostra **todas** as salas com ação pendente e o tempo de cada uma, ordenadas pela menor: `Sua vez em: M3QB (9s), K7XP (22s)`.
  - `/proxima` leva à sala com menos tempo restante.
  - Os avisos de nível alto (9.5) chegam para todas as salas pendentes.
- Os dois eventos de turno podem ser gerados em threads diferentes no servidor e escritos na mesma conexão; o ponto único de escrita (9.1) garante que as mensagens saiam inteiras e em sequência.

## Decisões novas a confirmar pelo grupo

1. Sala visualizada é apenas do cliente; o servidor envia eventos de todas as salas (9.2).
2. Comandos exigem `/` ou `@`; texto solto nunca vira jogada (9.7).
3. Prefixo `@COD` para agir em outra sala (9.3).
4. Três níveis de aviso e aviso de 10 segundos para salas não visualizadas (9.5).
5. Nenhuma coordenação entre salas quando duas exigem ação ao mesmo tempo (9.8).
6. Proposta de concorrência: uma thread por conexão, bloqueio por sala e ponto único de escrita por conexão (9.1).

## Testes planejados

| Cenário | Seção |
| --- | --- |
| Um cliente em duas salas com uma só conexão recebe eventos de ambas, cada um com o código correto | 9.1 |
| Jogada em sala da qual o jogador não participa: `SALA_NAO_PARTICIPA`, sem alterar nada | 9.3 |
| `@M3QB /letra A` age em M3QB enquanto K7XP está na tela, sem trocar a visualização | 9.3 |
| Trocar de sala não altera os cronômetros | 9.6 |
| Sala não visualizada: o tempo esgota, a vez passa sem penalidade e o aviso chega | 9.5, 9.6 |
| Aviso de 10 s chega só para sala não visualizada com a vez do jogador | 9.5 |
| Aviso chega enquanto o jogador digita: o texto parcial é preservado e o comando segue para a sala do prompt | 9.7 |
| Texto sem `/` ou `@` não gera nenhuma mensagem de rede | 9.7 |
| Duas salas na vez do jogador ao mesmo tempo: ambas contam, ele joga nas duas, nenhuma interfere | 9.8 |
| Linha de status lista as duas salas ordenadas por tempo; `/proxima` vai para a mais urgente | 9.8 |
| Eventos de salas diferentes gerados simultaneamente chegam inteiros (nenhuma mensagem misturada) | 9.1 |
| Cliente com 3 salas se desconecta: servidor aplica a saída em cada uma, sem impasse | 9.1 |
| Saída da sala visualizada: o cliente passa à sala com ação pendente ou ao menu | 9.2 |
