# Proposta, escopo e regras — Forca Multiplayer

## 2. Proposta da aplicação

### 2.1. Nome
Forca Multiplayer. Repositório sugerido: `forca-multiplayer-sockets`.

### 2.2. Descrição
Jogo de forca competitivo em rede, desenvolvido em Python com a biblioteca nativa `socket`, TCP e interface no terminal. Cada sala terá de dois a seis jogadores e partidas de cinco rodadas.

### 2.3. Salas independentes
O servidor permitirá várias salas simultâneas. Cada sala manterá participantes, responsável, situação da partida, rodada, palavra secreta, categoria, letras utilizadas, erros, ordem de participação, jogador da vez, prazo do turno e pontuações. Uma ação não poderá alterar outra sala.

### 2.4. Participação em várias salas
Um jogador poderá participar de várias salas pelo mesmo cliente e uma única conexão. Cada ação identificará a sala. O cliente permitirá alternar a visualização e receber avisos das demais salas. Os cronômetros continuarão contando independentemente da sala visualizada.

Exemplo: Manu poderá jogar com Sofia e João na sala 1 e com Ana e Pedro na sala 2.

### 2.5. Objetivo
Acumular a maior pontuação ao longo de cinco rodadas. Pontos serão obtidos por letras e palavras corretas e perdidos por tentativas de palavra incorretas. Ao final, o servidor anunciará o placar e os vencedores.

### 2.6. Atendimento ao enunciado
- Múltiplos participantes: dois a seis jogadores por sala.
- Criação e entrada em partidas: criação e entrada em salas.
- Gerenciamento dos participantes: lista e ordem controladas pelo servidor.
- Gerenciamento do estado: palavras, rodadas, turnos, erros e pontos.
- Transmissão de ações: solicitações enviadas pelos clientes via sockets.
- Validação: servidor verifica dados, permissões e regras.
- Impedimento de ações inválidas: recusa de letras repetidas e jogadas fora da vez, entre outras.
- Sincronização: atualizações enviadas aos participantes de cada sala.
- Término: detecção do final das cinco rodadas ou interrupção por falta de jogadores.
- Resultados: resultado da rodada e placar final.
- Novas partidas: reutilização da sala com novo placar.
- Concorrência: atendimento a vários clientes e salas.
- Erros e desconexões: tratamento de operações inválidas e falhas de comunicação.
- Protocolo próprio: formato, campos, respostas e sequência de mensagens serão especificados.
- Transporte: TCP, com justificativa na documentação.

### 2.7. Pontos de atenção
A proposta se enquadra em jogo multiplayer. A interface de terminal é permitida pelo enunciado. Participação em várias salas é uma funcionalidade adicional. Formato do protocolo e mecanismo de concorrência serão definidos antes da comunicação. Orientações complementares do professor deverão ser verificadas antes de implementar decisões afetadas.

## 3. Escopo inicial

### 3.1. Interface
Terminal com identificação, criação/entrada/seleção/saída de salas, participantes, categoria, palavra escondida, letras utilizadas, erros, jogador da vez, prazo, placar, resultados, mensagens de erro e notificações de outras salas.

### 3.2. Participantes
De dois a seis jogadores por sala. A partida exige pelo menos dois para começar e continuar. Se restar apenas um, será encerrada por falta de participantes, sem vencedor.

### 3.3. Funcionalidades obrigatórias
- Vários clientes conectados e identificação por apelido.
- Criação de salas por código e entrada antes do início da partida.
- Consulta, seleção e saída das salas do jogador.
- Participação em várias salas simultaneamente.
- Partidas com cinco rodadas e dois a seis jogadores.
- Palavras sorteadas pelo servidor, categoria e palavra escondida.
- Turnos de 30 segundos.
- Tentativas de letra e palavra completa.
- Letras utilizadas e contador compartilhado de erros.
- Pontuação acumulada e atualização dos participantes.
- Resultado das rodadas, placar final, vencedores e novas partidas.
- Tratamento de mensagens inválidas, operações indevidas, desconexões e falhas de comunicação.

### 3.4. Melhorias opcionais
Cores, desenho da forca, destaque do turno e das letras reveladas, placar visual mais elaborado, ajuda e atalhos. As funções básicas não dependerão dessas melhorias.

### 3.5. Fora do escopo
Cadastro, senha, recuperação de conta, banco de dados, ranking permanente, histórico persistente, recuperação de sessão, interface gráfica, chat, espectadores e entrada durante uma partida.

Dados serão mantidos em memória; palavras virão de arquivo local. Quem tentar entrar durante uma partida será avisado para tentar novamente ao final. Não haverá fila automática na primeira versão.

## 4. Regras da forca

### 4.1. Sorteio
O servidor sorteará uma palavra por rodada, sem repetição dentro da partida. O conjunto terá pelo menos cinco respostas distintas segundo a normalização definida abaixo.

### 4.2. Informações visíveis
No início: rodada, categoria, palavra escondida, zero erros, lista de letras vazia, placar acumulado e primeiro jogador. A palavra completa permanecerá no servidor até o encerramento. Espaços e hífens serão visíveis desde o início.

### 4.3. Ordem
A ordem de entrada na sala definirá a ordem dos turnos. O primeiro da lista começará a primeira rodada. Após jogada válida ou tempo esgotado, a vez passará ao próximo, de forma circular. Somente o jogador da vez poderá tentar.

### 4.4. Alternância do primeiro jogador
Cada rodada começará com o próximo participante ainda presente após quem iniciou a rodada anterior. Se esse jogador tiver saído, será usada sua posição na ordem original para localizar o próximo ainda presente. A ordem relativa dos demais será preservada.

### 4.5. Prazo
Cada turno terá 30 segundos controlados pelo servidor, inclusive enquanto o jogador visualizar outra sala. O servidor informará o prazo ao cliente.

### 4.6. Passagem da vez
Uma tentativa válida de letra ou palavra, correta ou incorreta, encerra o turno. Acertar não concede jogada adicional. Se a tentativa encerrar a rodada, não será aberto outro turno nela. Tempo esgotado também passa a vez.

### 4.7. Operações inválidas
Letras repetidas, entradas vazias, caracteres não permitidos, várias letras no comando de letra, jogadas fora da vez, em sala da qual não participa ou sem rodada ativa serão recusadas. Não alteram palavra, pontos ou erros. O jogador da vez poderá corrigir dentro do prazo restante, sem reiniciar o tempo.

### 4.8. Tempo esgotado
Passa a vez, sem desconto de pontos e sem erro compartilhado. Todos serão avisados. Tentativas recebidas após o prazo serão recusadas.

### 4.9. Erros compartilhados
Cada rodada admite até seis erros, compartilhados entre todos. Letra ausente e palavra completa incorreta somam um erro cada. O contador zera a cada rodada.

### 4.10. Fim da rodada
Ocorre ao acertar a palavra completa, revelar todas as letras ou atingir seis erros. O servidor revela a resposta, informa o motivo e atualiza o placar. Atingir o limite não concede bônus e preserva os pontos já obtidos.

### 4.11. Fim da partida
Após a quinta rodada, será anunciado o placar final e quem obteve mais pontos. Encerramento antecipado por falta de jogadores será informado como interrupção, sem vencedor. Nova partida na sala exige pelo menos dois jogadores e zera o placar.

### 4.12. Empates
Todos os jogadores com a maior pontuação serão vencedores empatados. Não haverá desempate. Empates nas demais posições também serão preservados.

## 5. Pontuação

### 5.1. Letra correta
Um ponto por ocorrência da letra. Em BANANA, A concede três pontos e revela as três ocorrências.

### 5.2. Letra incorreta
Zero pontos ganhos ou perdidos, um erro compartilhado e passagem da vez.

### 5.3. Palavra correta
Cinco pontos fixos e encerramento da rodada, independentemente de quantas letras restavam.

### 5.4. Sem acúmulo pelas letras restantes
A palavra correta concede apenas o bônus de cinco pontos. Pontos anteriores são preservados, mas letras ainda escondidas não rendem pontos adicionais.

### 5.5. Palavra incorreta
Menos dois pontos, um erro compartilhado e passagem da vez. Entrada vazia ou malformada é inválida e não recebe essa penalidade.

### 5.6. Sexto erro
Se a palavra incorreta causar o sexto erro, a penalidade será aplicada antes do encerramento da rodada.

### 5.7. Pontuação negativa
Permitida, sem limite mínimo. De zero, uma palavra incorreta leva a menos dois pontos.

### 5.8. Última letra
Concede somente os pontos das ocorrências da letra, sem bônus por terminar. Em C A _ A, tentar S concede um ponto e encerra a rodada.

### 5.9. Ordem do placar
Pontuação decrescente. Empatados ocupam a mesma posição e aparecem na ordem de entrada na sala apenas para apresentação, sem desempate.

### 5.10. Exemplos
1. BANANA, tentativa A: +3 pontos.
2. BANANA, tentativa Z: zero pontos e +1 erro.
3. B A _ A _ A, tentativa BANANA: +5 pontos e fim da rodada, sem bônus pelas letras N.
4. Jogador com 1 ponto tenta palavra incorreta: fica com -1 ponto, soma um erro e passa a vez.
5. A já utilizada, nova tentativa A: recusa, sem alteração e sem reiniciar o prazo.
6. C A _ A, tentativa S: +1 ponto e fim da rodada.
7. Manu 12, Sofia 12 e João 8: Manu e Sofia vencem empatadas.

## 6. Palavras e letras

### 6.1. Maiúsculas e minúsculas
Equivalentes na comparação. A apresentação será em maiúsculas.

### 6.2. Acentos e cedilha
Comparação sem distinção de acentos e cedilha: A corresponde a Á, À, Â, Ã; E a É, Ê; I a Í; O a Ó, Ô, Õ; U a Ú, Ü; C a Ç. As variantes serão consideradas a mesma letra para repetição. Tentar A após Ã será repetição, assim como o contrário. Todas as ocorrências equivalentes contam para a pontuação.

### 6.3. Grafia original
A grafia correta será armazenada e preservada na revelação. A normalização servirá apenas à comparação. Em MAÇÃ, C revela Ç e A revela A e Ã.

### 6.4. Espaços e hífens
Permitidos em palavras ou expressões, conforme cadastrados. Serão visíveis desde o início. Exemplo: GUARDA-CHUVA terá as letras escondidas e o hífen visível.

### 6.5. Caracteres automáticos
Somente espaços e hífens serão revelados automaticamente, sem pontos e sem contar como letras restantes. O banco não aceitará números ou outros sinais de pontuação na primeira versão.

### 6.6. Limites
De três a 20 letras, excluindo espaços e hífens, e no máximo 30 caracteres no total. O arquivo será validado segundo esses limites.

### 6.7. Letra válida
Uma única letra de A a Z ou uma das formas acentuadas ou com cedilha previstas. Espaços nas extremidades serão removidos. Números, emojis, pontuação, espaço, hífen, múltiplas letras e entrada vazia serão recusados. Letra já usada será recusada como repetida.

### 6.8. Palavra completa
O servidor removerá espaços nas extremidades, reduzirá espaços internos consecutivos a um e desconsiderará caixa, acentos e cedilha. Espaços internos e hífens continuam obrigatórios nas posições corretas.

Exemplos: MACA corresponde a MAÇÃ; guarda-chuva corresponde a GUARDA-CHUVA; GUARDA CHUVA não corresponde a GUARDA-CHUVA.

Tentativas deverão ter de três a 20 letras e até 30 caracteres após o tratamento dos espaços, usando letras e separadores permitidos. Uma tentativa nesse formato que não corresponda à resposta contará como palavra incorreta.

### 6.9. Espaços e entradas vazias
Entradas vazias após remoção dos espaços serão recusadas sem pontos ou erros. Correções não reiniciam o prazo do turno.

### 6.10. Validação uniforme
O servidor terá a decisão definitiva sobre validade e acerto. O cliente poderá orientar o usuário, sem decidir pontos. As mesmas regras de normalização serão usadas na validação do banco, comparação de letras e palavras, detecção de repetição, contagem de ocorrências e prevenção de respostas repetidas na partida. Essas decisões deverão constar na documentação e nos testes.
