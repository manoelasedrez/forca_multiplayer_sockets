# Pendências

O que ainda falta decidir ou implementar.

Como usar este documento: quando o grupo decidir um item, implemente, descreva a regra em [regras.md](../entrega/regras.md) (e em [protocolo.md](../entrega/protocolo.md), se mudar mensagens) e mova o item para o histórico no fim deste arquivo.

## 1. Em aberto

| # | Tema | Situação hoje | A decidir |
| ---: | --- | --- | --- |
| 5 | Várias salas por jogador | Cada jogador fica em 1 sala por vez | A proposta original previa até 5 salas com uma só conexão. Manter 1? Se não, como o cliente alterna entre salas? |
| 9 | Consulta de salas (`LISTAR_SALAS`) | Não há | Só faz sentido com várias salas por jogador (item 5). |
| 27 | Identidade do servidor | O cliente aceita qualquer chave pública que chegue no `CONNECT OK`; um atacante que intercepte a conexão desde o início poderia trocar as chaves (*man-in-the-middle*) | Fixar a chave pública do servidor no cliente (gerada uma vez e guardada em arquivo), ou mostrar a "impressão digital" da chave para o jogador conferir? |
| 28 | Reenvio de mensagens | O servidor não guarda os nonces recebidos: uma mensagem cifrada capturada pode ser reenviada (as regras do jogo limitam o efeito) | Numerar as mensagens de cada conexão e recusar números repetidos? |
| 20 | Terminal do cliente | O prompt é repetido depois de cada aviso, mas os avisos ainda aparecem no meio do que o jogador está digitando | Basta para o projeto, ou vale uma interface que separe a área de avisos da de digitação? |
| 24 | Recusa no `CONNECT` | O `CONNECT ERROR` traz só um texto livre, sem código | Dar um código também (como no `ERROR`)? |
| 25 | Envio com o Lock em mãos | Um cliente que pare de ler (sem fechar a conexão) poderia, em tese, travar o servidor no `sendall()` ([arquitetura.md](arquitetura.md), seção 4) | Pôr um prazo no envio, ou enviar fora do Lock por uma fila por cliente? |
| 26 | Persistência | Se o servidor cair, salas e partidas são perdidas | Fora do escopo da proposta original; manter assim? |

## 2. Decisões registradas

| # | Tema | Decisão |
| ---: | --- | --- |
| 21 | Concorrência | Um único `threading.Lock` no servidor protege todas as salas. É suficiente para o volume do projeto (até 50 salas). A proposta original sugeria um lock por sala, que só compensaria com muito mais salas ou jogadores. |

## 3. Histórico

Resolvidos na etapa seguinte ao piloto:

| # | Tema | Como ficou |
| ---: | --- | --- |
| 1, 2 | Rodadas e pontuação | 1 a 5 rodadas, escolhidas na criação da sala. +1 por ocorrência da letra, +5 pelo palpite certo, −2 pelo errado. Empates dividem a vitória. |
| 3 | Quem começa | Alterna a cada rodada. |
| 4 | Início da partida | Com 2 ou mais jogadores; `num-players` é o máximo. |
| 6 | Categoria | Quem cria a sala escolhe uma categoria ou `qualquer`. |
| 7 | Repetição de palavras | Não se repete dentro da partida. |
| 8 | Limites do palpite | Qualquer tamanho é aceito; se não bater, é erro. |
| 10 | Limite de salas | 50 salas no servidor. |
| 11 | Erros e letras no cliente | O `TURN RESPONSE` do servidor traz `pontos`, `erros` e `letras`. |
| 12 | Prazo do turno | O `TURN` traz `tempo`, e há a mensagem `TURN TIMEOUT`. |
| 13 | Códigos de erro | O `ERROR` traz `code` além do texto. |
| 14 | Versão | O servidor recusa versões diferentes de `forca1.0`. |
| 16 | Formato do código | Erro próprio, `CODIGO_INVALIDO`. |
| 17, 18, 19 | Nome de usuário | 1 a 15 caracteres, sem `,` `:` `=`. Os vencedores vão numa lista, então nenhum nome conflita com "ninguém venceu". |
| 22 | Banco de palavras | Validado ao carregar; palavras inválidas ou repetidas são descartadas com aviso. |
| 23 | Testes | Testes automatizados em `desenvolvimento/testes/`. |
| — | Forca desenhada e cores | Painel com a forca, cores ANSI e confirmação do palpite. |

Resolvidos na revisão dos requisitos do trabalho:

| Tema | Como ficou |
| --- | --- |
| Rede local | O servidor escuta em `0.0.0.0`; o cliente recebe o endereço e a porta como argumentos. |
| Mensagens malformadas | `MENSAGEM_INVALIDA` com a conexão mantida; limite de 16 KB por mensagem; chave pública inválida recusada no `CONNECT`; `CONNECT` repetido recusado (`JA_CONECTADO`). |
| Erros inesperados no servidor | `ERRO_INTERNO`, sem derrubar a thread do cliente. |
| Queda silenciosa de cliente | *Keepalive* do TCP (cerca de 25 s para detectar). |
| Queda do servidor | O cliente avisa e encerra. |
| Justificativas | Arquitetura, TCP e concorrência em [arquitetura.md](arquitetura.md). |
| Demonstração | Roteiro em [demonstracao.md](demonstracao.md) e `desenvolvimento/testes/cliente_bruto.py`. |
| Organização | O repositório foi dividido em `entrega/` (o que vai para o professor) e `desenvolvimento/` (testes e documentos internos). A proposta original (`docs/deprecated/`) foi apagada. |

Resolvidos na versão forca1.1:

| # | Tema | Como ficou |
| ---: | --- | --- |
| 15 | Cifragem das mensagens | Implementada. Depois do `CONNECT OK`, o corpo de todas as mensagens vai cifrado com o `Box` do PyNaCl; mensagens em claro, com outra chave ou adulteradas são recusadas com `MENSAGEM_INVALIDA`. Clientes da `forca1.0` são recusados no `CONNECT`. |
