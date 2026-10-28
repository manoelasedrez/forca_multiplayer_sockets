"""
Servidor da Forca Multiplayer: aceita as conexoes dos jogadores, GUARDA todo o estado
(salas, placar, de quem e a vez) e DECIDE tudo. O cliente so pede e mostra na tela.

Resumao de como a gente montou isso (a versao completa esta em desenvolvimento/arquitetura.md):

  - TCP: cada jogador abre UMA conexao e ela fica aberta a sessao inteira. O TCP garante
    que nada se perde, nada duplica e tudo chega na ordem. Mas ele entrega um FLUXO de
    bytes, ñ "mensagens" separadinhas (quem resolve isso e o protocol/protocol.py).
  - PORTA: o "guiche" da maquina onde o servidor atende (padrao 38905). O servidor
    escuta nela, e cada jogador que chega vira um SOCKET: a "tomada" por onde passa a
    conversa com ele.
  - THREADS: "atendentes" que rodam ao mesmo tempo. Tem 1 so pra aceitar gente nova, 1
    POR JOGADOR (fica esperando ele mandar algo) e 1 timer por sala (conta os 30 s do turno).
  - LOCK: como todos os atendentes mexem nas MESMAS salas, existe UM Lock so, tipo uma
    chave unica: quem esta com ela mexe no estado, os outros esperam. Sem isso, dois
    atendentes poderiam mudar o placar ao mesmo tempo e embaralhar tudo (race condition).
  - CIFRAGEM: depois do CONNECT, tudo vai embaralhado com chave publica/privada (PyNaCl).
    Ver protocolo.md, secao 7.

Por que threads e ñ select (um laco unico vigiando varios sockets)? O select obrigaria a
remontar mensagens que chegam em pedacos, socket por socket, e a conferir os prazos no
mesmo laco. Com uma thread por jogador o codigo de cada conexao fica sequencial (le,
trata, responde). Na escala do jogo (ate 50 salas) o custo das threads e pequeno.

Por que UM Lock e ñ um por sala? A proposta original sugeria um por sala, mas so
compensaria com MUITO mais salas, e com um so ñ existe risco de deadlock (duas threads
travadas esperando uma a chave da outra). Ver pendencias.md, item 21.

Por que cliente-servidor e ñ P2P? A palavra e um SEGREDO: em P2P ela ficaria na maquina
de algum jogador, que poderia trapacear. Aqui ela so sai do servidor no fim da rodada.

O enunciado (secao 4) pede sockets, protocolo proprio, tratar mensagens invalidas e
desconexoes, concorrencia e estado correto: tudo isso passa por este arquivo.

Ordem do arquivo: constantes -> Sala (o estado de UMA sala, sem rede) -> Server (rede + regras).
"""

# socket, threading, time, sys e random sao da biblioteca padrao. A unica EXTERNA e a nacl
# (PyNaCl), que so embaralha bytes: a rede em si e feita so com 'socket', como o enunciado
# exige (secao 2). 'protocol' e o nosso protocolo de aplicacao (protocol/protocol.py).
import socket
import sys
import time
import threading

from nacl.encoding import Base64Encoder
from nacl.exceptions import CryptoError
from protocol import protocol
from servidor import banco_palavras
import random
from nacl.public import Box, PrivateKey, PublicKey

# "0.0.0.0" = escuta em TODAS as placas de rede da maquina. Assim entra gente da propria
# maquina (127.0.0.1) E da rede local. Com "127.0.0.1" so a propria maquina conectaria.
HOST = "0.0.0.0"
# Porta TCP padrao. Da pra passar outra na linha de comando (ver o fim do arquivo).
PORT = 38905

# Keepalive do TCP: o sistema fica perguntando pro outro lado "ainda ta ai?". Sem isso, um
# cliente que some sem fechar a conexao (cabo desligado, maquina travada) nao avisa nada
# e o servidor esperaria pra sempre. Valores em segundos.
# Conta: 10 s parado + 3 tentativas de 5 s = ~25 s pra perceber (README, "Erros e desconexoes").
KEEPALIVE_OCIOSO = 10
KEEPALIVE_INTERVALO = 5
KEEPALIVE_TENTATIVAS = 3

# Regras do jogo. A tabela com o que cada uma significa esta em regras.md ("Constantes").
# CUIDADO: mexeu em algum valor? Atualiza o regras.md e o README tb, que citam esses numeros.
MIN_JOGADORES = 2
MAX_JOGADORES = 6
MIN_RODADAS = 1
MAX_RODADAS = 5
MAX_ERROS = 6
MAX_SALAS = 50
TEMPO_TURNO = 30  # segundos
PAUSA_ENTRE_RODADAS = 3  # segundos
DIFICULDADES = ["easy", "medium", "hard"]

# Pontuacao
PONTOS_PALAVRA = 5
PENALIDADE_PALPITE = 2

# Codigo da sala: sem I, L, O, 0 e 1, que se confundem
# (sobram 31 caracteres, entao 31^4 = ~920 mil codigos possiveis)
CARACTERES_CODIGO = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
TAMANHO_CODIGO = 4
TAMANHO_MAX_NOME_SALA = 20

# Nome de usuario: estes caracteres quebrariam as listas do protocolo
# (',' separa itens de uma lista, ':' separa chave de valor e '=' separa nome de pontos no placar)
TAMANHO_MAX_NOME_USUARIO = 15
CARACTERES_PROIBIDOS_NOME = ",:="


def pegar_pontos(item):
    """
    Devolve os pontos de um item (id, pontos). Existe so pra servir de 'key' do sorted().

    Pegadinha legal: o sorted(reverse=True) MANTEM a ordem original entre empatados (a
    ordenacao do Python e estavel). E isso que faz os empatados ficarem na ordem de
    entrada na sala, como o regras.md (3.8) promete.
    """
    # usado para ordenar o placar: item = (id, pontos)
    return item[1]


class Sala:
    """
    Tudo que o servidor sabe de UMA sala: quem esta nela, de quem e a vez, a palavra da
    rodada, o placar...

    Aq dentro ñ tem rede nenhuma: a Sala so guarda o estado e aplica as regras do jogo
    (regras.md). Quem fala com os jogadores e a classe Server, que chama os metodos daqui.
    Por isso da pra testar sem abrir socket (desenvolvimento/testes/test_sala.py).

    CUIDADO, nome enganoso: os jogadores sao guardados pelo ID "ip:porta" da conexao
    (ex.: "127.0.0.1:52344"), ñ pelo nome. Entao 'dono_addr' e as listas de jogadores
    NAO tem so o endereco: e o ID inteiro. O nome que o jogador ve vem do Server.nome(id).
    """

    def __init__(self, sala_id, nome, dono_addr, dificuldade, numero_jogadores, rodadas, categoria):
        self.nome = nome  # apelido da sala
        self.dono_addr = dono_addr
        self.dificuldade = dificuldade
        self.max_jogadores = numero_jogadores
        self.rodadas = rodadas
        self.categoria_escolhida = categoria  # categoria da sala ou "qualquer"
        # A ORDEM desta lista e a ordem dos turnos (regras.md 3.3). O primeiro e o dono.
        self.jogadores = [dono_addr]
        self.num_jogadores = 1
        self.estado = "aguardando"  # ou "em andamento", "finalizada" (regras.md 2.7)
        self.id = sala_id  # o codigo de 4 caracteres que o dono passa pros amigos

        # Estado da partida (zera a cada ROOM START)
        self.placar = {}  # id do jogador -> pontos
        self.rodada_atual = 0
        self.rodada_ativa = False  # False tambem na pausa entre rodadas
        self.palavras_usadas = []  # normalizadas, para nao repetir na partida
        self.inicio_rodada = -1  # indice de quem comecou a rodada

        # Estado da rodada (zera a cada ROUND START)
        self.palavra = ""
        self.categoria = ""  # categoria da palavra sorteada
        self.letras_usadas = []  # letras ja normalizadas
        self.erros = 0
        self.vez = 0  # indice em self.jogadores
        self.timer = None
        self.numero_turno = 0  # usado para ignorar timers antigos (ver Server.enviar_turno)

    def adicionar_jogador(self, jogador_addr):
        """Coloca o jogador no FIM da fila de turnos. Devolve False se a sala ja esta cheia."""
        if self.num_jogadores < self.max_jogadores:
            self.jogadores.append(jogador_addr)
            self.num_jogadores += 1
            return True
        return False

    def remover_jogador(self, jogador_addr):
        """
        Tira o jogador da sala e ARRUMA os indices que dependem da posicao dele na fila.

        Esse e o metodo mais esquisitinho da classe, pq 'vez' e 'inicio_rodada' guardam
        POSICOES (indices), e quando alguem sai da lista todo mundo depois dele anda um
        lugar pra tras. Sem o ajuste, a vez pularia ou cairia na pessoa errada.
        CUIDADO: ñ mexe nisso sem rodar os testes (desenvolvimento/testes/test_sala.py).
        """
        indice = self.jogadores.index(jogador_addr)
        self.jogadores.remove(jogador_addr)
        self.num_jogadores -= 1

        # Os pontos de quem sai deixam de contar (regras.md 2.6)
        if jogador_addr in self.placar:
            del self.placar[jogador_addr]

        # Mantem a vez no mesmo jogador (ou no proximo, se era a vez de quem saiu)
        if indice < self.vez:
            self.vez -= 1
        if self.num_jogadores > 0 and self.vez >= self.num_jogadores:
            self.vez = 0  # era o ultimo da fila: volta pro primeiro

        # Se quem comecou a rodada saiu, a proxima rodada comeca
        # com quem ocupava a posicao seguinte a dele
        if indice <= self.inicio_rodada:
            self.inicio_rodada -= 1

        # O proximo da lista vira dono
        if self.dono_addr == jogador_addr and self.num_jogadores > 0:
            self.dono_addr = self.jogadores[0]

    def esta_cheia(self):
        return self.num_jogadores >= self.max_jogadores

    def pode_iniciar(self):
        """So diz se o dono PODERIA iniciar (2+ jogadores, sem partida rodando). Vai no campo 'ready' do ROOM UPDATE."""
        return self.num_jogadores >= MIN_JOGADORES and self.estado != "em andamento"

    def iniciar_partida(self):
        """Zera TUDO da partida anterior: placar, rodadas, palavras ja sorteadas (regras.md 3.1)."""
        self.placar = {}
        for jogador in self.jogadores:
            self.placar[jogador] = 0
        self.rodada_atual = 0
        self.palavras_usadas = []
        self.inicio_rodada = -1  # a primeira rodada comeca com o primeiro da lista
        self.estado = "em andamento"

    def iniciar_rodada(self, palavra, categoria):
        """
        Prepara uma rodada nova com a palavra que o Server sorteou.

        O placar NAO zera aqui (os pontos acumulam entre as rodadas). Quem comeca vai
        girando: cada rodada comeca com o PROXIMO de quem comecou a anterior (regras.md 3.2).
        """
        self.rodada_atual += 1
        self.palavra = palavra
        self.categoria = categoria
        # Guarda NORMALIZADA, pq o sortear_palavra() compara assim
        self.palavras_usadas.append(banco_palavras.normalizar(palavra))
        self.letras_usadas = []
        self.erros = 0
        # Cada rodada comeca com o proximo depois de quem comecou a anterior
        self.inicio_rodada = (self.inicio_rodada + 1) % self.num_jogadores
        self.vez = self.inicio_rodada
        self.rodada_ativa = True

    def jogador_da_vez(self):
        return self.jogadores[self.vez]

    def passar_vez(self):
        """Passa pro proximo da fila, de forma circular (depois do ultimo volta pro primeiro)."""
        self.vez = (self.vez + 1) % self.num_jogadores

    def mascara(self):
        """A palavra escondida (ex.: '__A__A-____A'). E SO isso que os clientes recebem durante a rodada."""
        return banco_palavras.mascarar(self.palavra, self.letras_usadas)

    def tentar_letra(self, jogador, letra):
        """
        Aplica uma jogada de LETRA e devolve os pontos ganhos (0 se errou).

        CUIDADO: a letra tem que chegar ja normalizada (minuscula, sem acento); o Server
        faz isso antes de chamar. A validacao (letra repetida, etc.) tambem e la, ñ aqui.
        """
        # letra ja normalizada; devolve os pontos ganhos (0 se errou)
        self.letras_usadas.append(letra)  # entra na lista tanto se acertou quanto se errou
        pontos = banco_palavras.contar_ocorrencias(self.palavra, letra)
        if pontos == 0:
            self.erros += 1
        self.placar[jogador] += pontos
        return pontos

    def tentar_palpite(self, jogador, texto):
        """
        Aplica um PALPITE (a palavra inteira). Devolve +5 se acertou ou -2 se errou
        (o placar pode ficar negativo, regras.md 3.6).

        Na comparacao sao ignorados acento, maiuscula e espaco repetido. Ja espaco
        interno e hifen continuam valendo: "guarda chuva" ñ acerta "guarda-chuva".
        """
        # devolve os pontos ganhos (positivo) ou perdidos (negativo)
        texto = " ".join(texto.split())  # junta espacos repetidos
        if banco_palavras.normalizar(texto) == banco_palavras.normalizar(self.palavra):
            # Revela a palavra inteira: joga todas as letras que faltavam na lista de usadas,
            # assim a mascara() e a lista de letras mostradas ficam completas.
            for c in banco_palavras.normalizar(self.palavra):
                if c not in self.letras_usadas and c not in banco_palavras.SEPARADORES:
                    self.letras_usadas.append(c)
            self.placar[jogador] += PONTOS_PALAVRA
            return PONTOS_PALAVRA
        # Palpite errado conta como erro da rodada E tira pontos
        self.erros += 1
        self.placar[jogador] -= PENALIDADE_PALPITE
        return -PENALIDADE_PALPITE

    def palavra_completa(self):
        """True quando ñ sobrou nenhum '_' na mascara, ou seja, todas as letras foram reveladas."""
        return "_" not in self.mascara()

    def placar_ordenado(self):
        """
        Lista de (id, pontos), do maior pro menor. Quem saiu da sala ñ aparece.

        Percorre self.jogadores (e ñ o dicionario do placar) de proposito: assim os
        empatados saem na ordem de entrada na sala. Ver pegar_pontos().
        """
        # Lista de (id, pontos), do maior para o menor.
        # Empatados ficam na ordem de entrada na sala.
        lista = []
        for jogador in self.jogadores:
            if jogador in self.placar:
                lista.append((jogador, self.placar[jogador]))
        return sorted(lista, key=pegar_pontos, reverse=True)

    def vencedores(self):
        """Todos que empataram na maior pontuacao (ñ tem desempate, regras.md 3.8)."""
        # Todos os que tem a maior pontuacao
        lista = self.placar_ordenado()
        if len(lista) == 0:
            return []
        maior = lista[0][1]
        resultado = []
        for jogador, pontos in lista:
            if pontos == maior:
                resultado.append(jogador)
        return resultado

    def letras_para_mostrar(self):
        """Letras ja tentadas na rodada, em MAIUSCULAS e na ordem em que foram jogadas (campo 'letras' do protocolo)."""
        letras = []
        for letra in self.letras_usadas:
            letras.append(letra.upper())
        return letras

    def cancelar_timer(self):
        """
        Cancela o timer da sala (prazo do turno ou pausa entre rodadas), se tiver algum.

        CUIDADO: cancelar ñ garante que o timer ñ vai rodar. Se ele JA disparou e so esta
        esperando o Lock, o cancel() ñ adianta. Por isso existe o 'numero_turno'.
        """
        if self.timer is not None:
            self.timer.cancel()
            self.timer = None


class Server(socket.socket):
    """
    O servidor em si. Repara que ele HERDA de socket.socket: o proprio objeto Server e o
    socket que fica escutando (bind/listen/accept), por isso aqui se usa self.bind(),
    self.accept() e self.close().

    Cada jogador conectado e identificado por um ID "ip:porta" (ex.: "127.0.0.1:52344"),
    que e unico enquanto a conexao existir (desenvolvimento/arquitetura.md, secao 7).
    """

    def __init__(self, host, port):
        super().__init__(socket.AF_INET, socket.SOCK_STREAM)  # AF_INET = IPv4; SOCK_STREAM = TCP
        self.host = host
        self.port = port
        self.public_key = None
        self.private_key = None

        # id "ip:porta" -> dados da conexao (socket do jogador, ip, porta)
        self.clientes = {}
        # Box de cada conexao aceita (socket -> nacl.public.Box). Sem Box, a conexao
        # ainda nao passou do CONNECT e as mensagens vao em texto puro.
        self.boxes = {}

        self.users = {}  # id -> {"name": ..., "public_key": ...}. So tem quem ja fez CONNECT com sucesso.

        self.salas = {}  # codigo da sala -> Sala
        self.codigos_usados = []  # codigos nunca sao reaproveitados
        self.encerrando = False  # vira True no Ctrl+C; as threads olham pra saber que e o fim

        # O banco de palavras e carregado UMA vez, aqui. Depois o servidor so le.
        self.palavras = banco_palavras.carregar_palavras()
        self.categorias = banco_palavras.listar_categorias(self.palavras)
        # O Lock unico (ver o resumao la em cima). Tem que ser pego em TUDO que le ou muda salas/users.
        self.lock = threading.Lock()  # protege salas e users entre as threads

    def print(self, msg):
        print(msg)

    def iniciar(self):
        """
        Liga o servidor: reserva a porta, comeca a escutar e dispara a thread que aceita jogadores.

        E a sequencia classica de servidor TCP:
          bind()   -> "essa porta e minha" (reserva IP + porta pra este programa)
          listen() -> "pode chegar gente": o sistema guarda numa fila ate ~10 conexoes
                      esperando atendimento
          accept() -> (na outra thread) pega a proxima da fila e devolve um socket NOVO,
                      so daquele jogador

        CUIDADO (parece bug): o 'e.errno == 98' so significa "porta ocupada" no LINUX. No
        Windows e 10048 e no Mac e 48 (num teste no Windows deu 10048, fiquei gag). Nesses
        sistemas o ramo "tenta a proxima porta", que o README promete, ñ roda: cai no else,
        imprime o erro e desiste. E tem mais: depois de desistir, este metodo so volta, e
        o main continua no while/sleep. O processo fica VIVO, mas sem servidor escutando.
        """
        try:
            self.bind((self.host, self.port))
        except OSError as e:
            if e.errno == 98:
                self.print(f"Porta {self.port} já está em uso. Tentando outra porta...")
                self.port += 1
                self.iniciar()
            else:
                self.print(f"Erro ao iniciar o servidor: {e} \n Encerrando o servidor.")
            return
        self.port = self.getsockname()[1]  # porta real (caso tenha sido 0)
        self.print(f"Servidor iniciado em {self.host}:{self.port}")
        if self.host == "0.0.0.0":
            self.print("Aceitando conexões de qualquer interface. Os clientes devem usar o IP desta máquina")
            self.print("(veja com 'ip addr' no Linux ou 'ipconfig' no Windows) ou 127.0.0.1 na mesma máquina.")
        self.listen(10)
        self.print(f"{len(self.palavras)} palavras carregadas em {len(self.categorias)} categorias")
        self.print("Servidor aguardando conexão...")

        # Par de chaves do servidor (cifragem). A privada ñ sai daqui; so a publica e
        # mandada pros clientes. CUIDADO com a ORDEM: isso tem que existir ANTES de
        # iniciar a thread abaixo, pq o primeiro CONNECT ja usa a chave privada.
        self.private_key = PrivateKey.generate()
        self.public_key = self.private_key.public_key

        # daemon=True: thread "de segundo plano", morre junto com o programa em vez de
        # segurar o Ctrl+C esperando ela terminar.
        threading.Thread(target=self.aceitar_conexao_thread, daemon=True).start()

    def aceitar_conexao_thread(self):
        """
        Thread que SO aceita jogadores novos, pra sempre. Pra cada um, cria uma thread so dele.

        O accept() BLOQUEIA: a thread fica parada ali ate alguem conectar. Quando chega, ele
        devolve (conn, addr): 'conn' e um socket NOVO, so desse jogador, e 'addr' e o
        (ip, porta) dele. Esse e o modelo "uma thread por cliente" (ver o resumao la em cima).
        """
        while True:
            try:
                conn, addr = self.accept()
            except OSError:
                # Quando o fechar() fecha o socket que escuta, o accept() levanta OSError.
                # E o jeito NORMAL de parar esta thread.
                if self.encerrando:
                    break
                # CUIDADO: se foi outro erro, esse raise mata so ESTA thread. O programa
                # continua de pe, mas ñ aceita mais ninguem.
                raise
            id = f"{addr[0]}:{addr[1]}"
            self.print(f"Cliente conectado: {id}")
            self.ativar_keepalive(conn)
            # Sem Lock aqui: o jogador so aparece pro resto do servidor (salas, users) depois do CONNECT.
            # Obs: 'addr' e 'ip' guardam a MESMA coisa (o ip).
            self.clientes[id] = {"socket": conn, "addr": addr[0], "port": addr[1], "ip": addr[0]}
            threading.Thread(target=self.handle_cliente, args=(conn, id), daemon=True).start()

    def ativar_keepalive(self, conn):
        """
        Liga o keepalive do TCP nessa conexao (ver as constantes KEEPALIVE_* la em cima).

        O ligar/desligar (SO_KEEPALIVE) existe em todo sistema. Mas ajustar os TEMPOS
        (ocioso, intervalo, tentativas) ñ, por isso os hasattr. Onde faltar, vale o padrao
        do sistema, que costuma ser de HORAS: a deteccao de cliente fantasma ficaria bem mais lenta.
        """
        conn.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        # Os ajustes de tempo nao existem em todos os sistemas operacionais
        if hasattr(socket, "TCP_KEEPIDLE"):
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, KEEPALIVE_OCIOSO)
        if hasattr(socket, "TCP_KEEPINTVL"):
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, KEEPALIVE_INTERVALO)
        if hasattr(socket, "TCP_KEEPCNT"):
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, KEEPALIVE_TENTATIVAS)

    def fechar(self):
        """
        Desliga tudo direitinho (chamado no Ctrl+C): cancela os timers e fecha todas as conexoes.

        Ele pega o Lock pra ñ competir com as threads dos clientes que estiverem no meio de
        uma jogada (desenvolvimento/arquitetura.md, secao 5).

        CUIDADO com a ORDEM: 'encerrando' vira True ANTES de fechar qualquer socket. Quando
        fechamos um socket, o recv() daquele jogador falha e a thread dele acordaria
        achando que o cliente caiu; olhando 'encerrando' ela sabe que e o servidor
        desligando e ñ faz a limpeza (nem avisa nada) por conta propria.
        """
        with self.lock:  # espera terminar o que as outras threads estao fazendo
            self.encerrando = True
            for sala in list(self.salas.values()):
                sala.cancelar_timer()
            for cliente in list(self.clientes.values()):
                try:
                    # shutdown corta a conversa dos dois lados; o recv() da thread do
                    # jogador acorda com erro e ela encerra.
                    cliente["socket"].shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass  # o cliente ja tinha caido: tudo bem
                cliente["socket"].close()
            self.clientes.clear()
            self.boxes.clear()
        # Fecha o socket que escuta, fora do 'with'. Isso faz o accept() levantar OSError e
        # a thread de aceite terminar.
        self.close()

    def handle_cliente(self, conn, id):
        """
        A thread de UM jogador: fica num laco lendo o que ele manda, mensagem por mensagem,
        ate a conexao acabar. Existe uma dessas pra cada jogador conectado.

        Cada volta do laco:
          1) le UMA mensagem inteira (bloqueia ate chegar; ver protocol.receive_message);
          2) se a leitura deu problema, trata de acordo com o tipo (tabela abaixo);
          3) se deu certo, pega o Lock e deixa o handle_mensagem aplicar as regras.

        O que fazer em cada falha (enunciado, secao 4: "tratar mensagens invalidas e desconexoes"):
          - ErroProtocolo: corpo malformado ou que ñ decifra. Ele foi lido INTEIRO, entao a
            proxima mensagem comeca no lugar certo: avisa o jogador e continua.
          - ErroTamanho: anunciou um tamanho absurdo. Ñ da pra saber onde a proxima
            mensagem comeca (o TCP e um fluxo de bytes), entao fecha a conexao.
          - qualquer outro erro: a conexao caiu (jogador fechou o terminal, rede, etc.).

        CUIDADO: o receive_message fica FORA do Lock de proposito. Ele pode ficar parado
        minutos esperando o jogador pensar; dentro do Lock, o servidor inteiro congelaria.
        """
        while True:
            try:
                # Com a Box da conexao, a mensagem e decifrada aqui dentro. Antes do
                # CONNECT ela ainda ñ existe (get devolve None) e a leitura e em texto puro.
                mensagem = protocol.receive_message(conn, self.boxes.get(conn))
                self.print(f"[{self.nome(id)}] {mensagem.first_line()}")

            except protocol.ErroProtocolo as e:
                # Corpo malformado: avisa o cliente e continua lendo
                self.print(f"[{self.nome(id)}] mensagem invalida: {e}")
                self.erro_seguro(conn, protocol.MENSAGEM_INVALIDA, "mensagem invalida: " + str(e))
                continue

            except protocol.ErroTamanho as e:
                # Nao da para achar o inicio da proxima mensagem: encerra
                self.print(f"[{self.nome(id)}] {e}. Encerrando a conexao.")
                self.erro_seguro(conn, protocol.MENSAGEM_INVALIDA, str(e))
                break

            except Exception as e:
                # Conexao caiu. Se foi o servidor desligando (encerrando), nem comenta.
                if not self.encerrando:
                    self.print(f"Conexão com {self.nome(id)} encerrada: {e}")
                break

            # Daqui pra baixo mexe no estado compartilhado: so UMA thread por vez.
            with self.lock:
                try:
                    self.handle_mensagem(conn, id, mensagem)
                except OSError:
                    pass  # falha ao enviar: o proximo recv percebe a desconexao
                except Exception as e:
                    # Erro inesperado no servidor: nao derruba a thread do cliente
                    self.print(f"Erro ao tratar {mensagem.first_line()} de {self.nome(id)}: {e}")
                    self.erro_seguro(conn, protocol.ERRO_INTERNO, "erro interno do servidor")

        # Saiu do laco = o jogador se foi. Faz a limpeza (sai da sala, libera o socket...).
        if not self.encerrando:
            self.desconectar(id)

    def handle_mensagem(self, conn, id, mensagem):
        """
        O "roteador": olha de que TIPO e a mensagem e chama quem sabe tratar.

        Cada tipo de mensagem do protocolo e uma classe em protocol.py, por isso o
        isinstance. Sempre chamado com o Lock em maos (o handle_cliente garante).
        """

        if isinstance(mensagem, protocol.ConnectRequest):
            # --- CONNECT: o jogador se apresenta e os dois lados trocam as chaves ---
            if id in self.users:
                self.erro(conn, protocol.JA_CONECTADO, "voce ja esta conectado")
                return
            erro = self.validar_conexao(mensagem)
            if erro is not None:
                # CONNECT ERROR vai em texto puro (ainda ñ tem chave) e a conexao continua aberta
                self.responder(conn, protocol.ConnectError(erro + "\r\n"))
                return
            try:
                # Cada lado combina a PROPRIA chave privada com a PUBLICA do outro e chega
                # na MESMA chave secreta, sem ela nunca passar pela rede (protocolo.md, 7.1).
                chave_cliente = PublicKey(mensagem.public_key, encoder=Base64Encoder)
                box = Box(self.private_key, chave_cliente)
            except (CryptoError, ValueError, TypeError):
                self.responder(conn, protocol.ConnectError("chave publica invalida\r\n"))
                return
            self.users[id] = {
                "name": mensagem.username,
                "public_key": chave_cliente
                }
            # O CONNECT OK vai em texto puro: o cliente ainda precisa da chave do servidor
            chave_texto = self.public_key.encode(encoder=Base64Encoder).decode()
            resposta = protocol.ConnectOk(chave_texto, self.categorias)
            protocol.send_message(conn, resposta)
            # A partir daqui, tudo nesta conexao vai cifrado.
            # CUIDADO com a ORDEM: a Box so entra DEPOIS do send_message acima. Se fosse
            # antes, o proprio CONNECT OK sairia cifrado e o cliente (sem a chave) ñ leria.
            self.boxes[conn] = box
            self.print(f"Conexão com {id} estabelecida. Usuário: {mensagem.username} (mensagens cifradas)")
            # Limitacao conhecida (pendencias.md, item 27): o cliente ñ confere que essa
            # chave e MESMO do servidor. Quem interceptar a conexao desde o comeco (man-in-the-middle) poderia trocar as chaves.
            return

        # Qualquer outra mensagem exige CONNECT antes
        if id not in self.users:
            self.erro(conn, protocol.NAO_CONECTADO, "envie CONNECT primeiro")
            return

        # --- roteamento dos pedidos do jogo ---
        if isinstance(mensagem, protocol.RoomCreateRequest):
            self.receber_criar_sala(conn, id, mensagem)

        elif isinstance(mensagem, protocol.RoomJoinRequest):
            self.receber_entrar_sala(conn, id, mensagem)

        elif isinstance(mensagem, protocol.RoomLeaveRequest):
            self.receber_sair_sala(conn, id, mensagem)

        elif isinstance(mensagem, protocol.RoomStartRequest):
            self.iniciar_partida(conn, id, mensagem.room_id)

        elif isinstance(mensagem, protocol.TurnResponseRequest):
            self.receber_jogada(conn, id, mensagem)

        else:
            # Mensagem valida no protocolo, mas que so o servidor envia
            # (ex.: um cliente alterado mandando ROOM CREATE OK). Nunca confiar no cliente.
            self.erro(conn, protocol.MENSAGEM_INVALIDA,
                      f"{mensagem.first_line()} nao e uma mensagem do cliente")

    def responder(self, conn, mensagem):
        """
        Manda uma mensagem pra UM jogador, cifrada com a Box dele (se ele ja passou do CONNECT).

        TODO envio do servidor passa por aqui. Assim ninguem esquece de cifrar.
        """
        # Cifra com a Box da conexao, se ela ja passou do CONNECT
        protocol.send_message(conn, mensagem, self.boxes.get(conn))

    def erro(self, conn, codigo, texto):
        """
        Manda um ERROR pro jogador: 'codigo' e fixo (o cliente decide o que fazer por ele,
        protocolo.md secao 6) e 'texto' e so a explicacao pra mostrar na tela.
        """
        self.responder(conn, protocol.ErrorMessage(codigo, texto))

    def erro_seguro(self, conn, codigo, texto):
        """
        Igual ao erro(), mas ignora falha de envio. Serve pra quando a conexao
        pode ja ter caido (ex.: dentro do tratamento de uma falha de leitura).
        """
        # Igual a erro(), mas ignora falha de envio (a conexao pode ja ter caido)
        try:
            self.erro(conn, codigo, texto)
        except OSError:
            pass

    def enviar_para_sala(self, sala, mensagem):
        """
        Manda a MESMA mensagem pra todo mundo da sala (e assim que os jogadores ficam sincronizados).

        CUIDADO (limitacao conhecida, pendencias.md item 25): isso roda com o Lock em maos. Se
        um jogador parar de ler sem fechar a conexao, o buffer de envio do TCP pode encher e o
        sendall() travar, e o servidor todo junto. Com mensagens de poucas centenas de
        bytes isso exigiria milhares de eventos acumulados, entao ñ rola em uso normal.
        """
        for jogador_id in sala.jogadores:
            if jogador_id in self.clientes:
                try:
                    self.responder(self.clientes[jogador_id]["socket"], mensagem)
                except OSError:
                    pass  # a thread do cliente trata a desconexao

    def nome(self, id):
        """Nome do jogador a partir do id "ip:porta". Se ainda ñ fez CONNECT, devolve o proprio id (pros logs)."""
        if id in self.users:
            return self.users[id]["name"]
        return id

    def nomes_conectados(self):
        nomes = []
        for user in self.users.values():
            nomes.append(user["name"])
        return nomes

    def nomes_da_sala(self, sala):
        """Nomes dos jogadores na ordem da sala. E o campo USERS das mensagens (o primeiro e o dono)."""
        nomes = []
        for jogador_id in sala.jogadores:
            nomes.append(self.nome(jogador_id))
        return nomes

    def placar_com_nomes(self, sala):
        # [(id, pontos)] -> [(nome, pontos)], para enviar no protocolo
        # (o protocolo so trabalha com NOMES; o id "ip:porta" nunca vai pros outros jogadores)
        placar = []
        for jogador_id, pontos in sala.placar_ordenado():
            placar.append((self.nome(jogador_id), pontos))
        return placar

    # -----------------------------------------------------------
    # Conexao
    # -----------------------------------------------------------
    def validar_conexao(self, mensagem):
        """
        Confere o CONNECT. Devolve None se esta tudo certo, ou o TEXTO do problema (vai no CONNECT ERROR).

        Mesma ordem de protocolo.md 3.1 e regras.md secao 1: a primeira checagem que
        falhar e a que o jogador ve.
        """
        # Devolve None se deu certo, ou o texto do erro
        if mensagem.version != protocol.VERSION:
            return "versao nao suportada, use " + protocol.VERSION
        nome = mensagem.username
        if nome.strip() == "" or len(nome) > TAMANHO_MAX_NOME_USUARIO:
            return f"nome de usuario deve ter de 1 a {TAMANHO_MAX_NOME_USUARIO} caracteres"
        for c in CARACTERES_PROIBIDOS_NOME:
            if c in nome:
                return "nome de usuario nao pode ter " + " ".join(CARACTERES_PROIBIDOS_NOME)
        if nome in self.nomes_conectados():
            return "nome de usuario ja em uso"
        return None

    # -----------------------------------------------------------
    # Salas
    # -----------------------------------------------------------
    def gerar_codigo(self):
        """
        Sorteia o codigo de 4 caracteres da sala (ex.: K7XP), repetindo ate achar um que NUNCA foi usado.

        Nunca reaproveitar (regras.md 2.3) tem um efeito bom: um codigo antigo ñ leva ninguem
        pra uma sala nova. Obs: a lista 'codigos_usados' so cresce enquanto o servidor ficar
        ligado (ñ e problema pro volume do trabalho).
        """
        # Sorteia ate achar um codigo que nunca foi usado
        while True:
            codigo = ""
            for i in range(TAMANHO_CODIGO):
                codigo += random.choice(CARACTERES_CODIGO)
            if codigo not in self.codigos_usados:
                self.codigos_usados.append(codigo)
                return codigo

    def codigo_valido(self, codigo):
        """So confere o FORMATO (4 caracteres permitidos), ñ se a sala existe. Aceita minuscula e espaco nas pontas."""
        codigo = codigo.strip().upper()
        if len(codigo) != TAMANHO_CODIGO:
            return False
        for c in codigo:
            if c not in CARACTERES_CODIGO:
                return False
        return True

    def receber_criar_sala(self, conn, id, mensagem):
        """
        Trata o ROOM CREATE: confere o pedido e, se estiver tudo certo, cria a sala.

        Cada checagem que falha manda um ERROR e SAI, sem mudar nada no servidor. As
        checagens seguem a ordem do protocolo.md 3.2, que e o que o cliente espera.
        CUIDADO: ñ troca a ordem sem mexer no protocolo.md tambem.

        A ultima (PALAVRAS_INSUFICIENTES) existe pq a palavra ñ repete dentro da partida e
        algumas combinacoes de categoria + dificuldade tem poucas palavras (regras.md 2.2).
        E ela que garante que o sortear_palavra() nunca fica sem opcao.
        """
        if self.sala_do_jogador(id) is not None:
            self.erro(conn, protocol.JA_EM_SALA, "voce ja esta em uma sala, saia dela primeiro")
            return
        if len(self.salas) >= MAX_SALAS:
            self.erro(conn, protocol.LIMITE_SALAS_SERVIDOR, "o servidor atingiu o limite de salas, tente mais tarde")
            return
        nome_sala = mensagem.room_name.strip()
        if nome_sala == "" or len(nome_sala) > TAMANHO_MAX_NOME_SALA:
            self.erro(conn, protocol.NOME_SALA_INVALIDO, f"nome da sala deve ter de 1 a {TAMANHO_MAX_NOME_SALA} caracteres")
            return
        if mensagem.numero_jogadores < MIN_JOGADORES or mensagem.numero_jogadores > MAX_JOGADORES:
            self.erro(conn, protocol.NUM_JOGADORES_INVALIDO, f"numero de jogadores deve ser de {MIN_JOGADORES} a {MAX_JOGADORES}")
            return
        if mensagem.dificuldade not in DIFICULDADES:
            self.erro(conn, protocol.DIFICULDADE_INVALIDA, "dificuldade deve ser " + ", ".join(DIFICULDADES))
            return
        if mensagem.rounds < MIN_RODADAS or mensagem.rounds > MAX_RODADAS:
            self.erro(conn, protocol.RODADAS_INVALIDAS, f"numero de rodadas deve ser de {MIN_RODADAS} a {MAX_RODADAS}")
            return
        if mensagem.categoria != banco_palavras.CATEGORIA_QUALQUER and mensagem.categoria not in self.categorias:
            self.erro(conn, protocol.CATEGORIA_INVALIDA, "categoria inexistente")
            return
        candidatas = banco_palavras.filtrar_palavras(self.palavras, mensagem.dificuldade, mensagem.categoria)
        if len(candidatas) < mensagem.rounds:
            self.erro(conn, protocol.PALAVRAS_INSUFICIENTES,
                      f"so ha {len(candidatas)} palavras nesta categoria e dificuldade, escolha outra combinacao")
            return

        # Passou em tudo: cria a sala (quem criou vira o dono) e devolve o codigo dela
        sala = self.criar_sala(id, nome_sala, mensagem.dificuldade, mensagem.numero_jogadores,
                               mensagem.rounds, mensagem.categoria)
        self.responder(conn, protocol.RoomCreateOk(sala.id))
        self.print(f"Sala {sala.id} '{sala.nome}' criada por {self.nome(id)} "
                   f"(ate {sala.max_jogadores} jogadores, {sala.rodadas} rodadas, {sala.dificuldade}, {sala.categoria_escolhida})")

    def receber_sair_sala(self, conn, id, mensagem):
        """Trata o ROOM LEAVE. Confirma pro jogador (ROOM LEAVE OK) e depois faz a saida de verdade no sair_sala()."""
        sala = self.get_sala(mensagem.room_id)
        if not sala or id not in sala.jogadores:
            self.erro(conn, protocol.SALA_NAO_PARTICIPA, "voce nao participa desta sala")
            return
        self.responder(conn, protocol.RoomLeaveOk())
        self.print(f"{self.nome(id)} saiu da sala {sala.id}")
        self.sair_sala(id, sala)

    def receber_entrar_sala(self, conn, id, mensagem):
        """
        Trata o ROOM JOIN. Quem entra recebe o ROOM JOIN OK (so ele) e depois TODOS da sala,
        ele incluido, recebem o ROOM UPDATE com a lista nova (protocolo.md 3.3).
        """
        codigo, erro = self.entrar_sala(mensagem.room_id, id)
        if codigo is not None:
            self.erro(conn, codigo, erro)
            return
        sala = self.get_sala(mensagem.room_id)
        self.responder(conn, protocol.RoomJoinOk(self.nomes_da_sala(sala), sala.dificuldade, sala.nome,
                                                 sala.rodadas, sala.categoria_escolhida))
        self.print(f"{self.nome(id)} entrou na sala {sala.id} ({sala.num_jogadores}/{sala.max_jogadores})")
        self.atualizar_sala(sala.id)

    def criar_sala(self, dono_id, nome_sala, dificuldade, numero_jogadores, rodadas, categoria):
        sala = Sala(self.gerar_codigo(), nome_sala, dono_id, dificuldade, numero_jogadores, rodadas, categoria)
        self.salas[sala.id] = sala
        return sala

    def get_sala(self, sala_id):
        """Acha a sala pelo codigo. Aceita minuscula e espaco nas pontas (mesma regra do codigo_valido)."""
        # aceita minusculas e espacos nas pontas
        return self.salas.get(sala_id.strip().upper())

    def sala_do_jogador(self, jogador_id):
        """
        Em que sala o jogador esta (ou None). Percorre todas, mas sao no maximo 50.

        Cada jogador fica em NO MAXIMO uma sala. A proposta original previa ate 5 salas por
        conexao, mas isso ficou em aberto (pendencias.md, item 5).
        """
        # No piloto cada jogador fica em no maximo uma sala
        for sala in self.salas.values():
            if jogador_id in sala.jogadores:
                return sala
        return None

    def entrar_sala(self, sala_id, jogador_id):
        """
        Tenta colocar o jogador na sala. Devolve (None, None) se deu certo, ou (codigo, texto) do erro.

        As checagens seguem a ordem do regras.md 2.4: a primeira que falhar define a
        recusa, e a recusa ñ pode alterar nada.

        CUIDADO: o adicionar_jogador() e a ULTIMA checagem de proposito. Ele confere se
        ha vaga E ja coloca o jogador na sala. Se estivesse antes de outra checagem, o
        jogador entraria e depois tomaria um erro, ficando dentro mesmo assim.
        """
        # Devolve (None, None) se deu certo, ou (codigo, texto) do erro
        if not self.codigo_valido(sala_id):
            return protocol.CODIGO_INVALIDO, f"codigo invalido, use {TAMANHO_CODIGO} caracteres (ex.: K7XP)"
        sala = self.get_sala(sala_id)
        if not sala:
            return protocol.SALA_INEXISTENTE, "sala inexistente"
        if self.sala_do_jogador(jogador_id) is not None:
            return protocol.JA_EM_SALA, "voce ja esta em uma sala, saia dela primeiro"
        if sala.estado == "em andamento":
            return protocol.PARTIDA_EM_ANDAMENTO, "partida em andamento, tente novamente quando terminar"
        if not sala.adicionar_jogador(jogador_id):
            return protocol.SALA_CHEIA, f"sala cheia ({sala.num_jogadores}/{sala.max_jogadores})"
        return None, None

    def atualizar_sala(self, sala_id):
        """
        Manda o ROOM UPDATE pra sala toda: lista de jogadores atual + 'ready' (o dono ja pode iniciar?).

        Chamado sempre que algo muda na sala (entrou, saiu, a partida acabou). E assim que
        os clientes ficam sempre com a mesma foto da sala.
        """
        sala = self.get_sala(sala_id)
        if sala:
            mensagem = protocol.RoomUpdate(sala.id, self.nomes_da_sala(sala), sala.dificuldade, sala.pode_iniciar())
            self.enviar_para_sala(sala, mensagem)

    # -----------------------------------------------------------
    # Partida e rodadas
    # -----------------------------------------------------------
    def iniciar_partida(self, conn, id, sala_id):
        """
        Trata o ROOM START (so o dono pode). Se passar nas checagens, zera a partida e
        manda a primeira rodada.

        Ordem das mensagens (protocolo.md 4.3): ROOM START OK so pro dono, depois ROOM
        STARTED pra todos, depois ja vem o ROUND START da rodada 1.
        """
        sala = self.get_sala(sala_id)
        if not sala or id not in sala.jogadores:
            self.erro(conn, protocol.SALA_NAO_PARTICIPA, "voce nao participa desta sala")
            return
        if sala.dono_addr != id:
            self.erro(conn, protocol.APENAS_DONO, "apenas o dono da sala pode iniciar")
            return
        if sala.estado == "em andamento":
            self.erro(conn, protocol.PARTIDA_EM_ANDAMENTO, "partida ja esta em andamento")
            return
        if sala.num_jogadores < MIN_JOGADORES:
            self.erro(conn, protocol.JOGADORES_INSUFICIENTES, f"sao necessarios pelo menos {MIN_JOGADORES} jogadores")
            return

        sala.iniciar_partida()
        self.print(f"Sala {sala.id}: partida iniciada com {sala.num_jogadores} jogadores e {sala.rodadas} rodadas")
        self.responder(conn, protocol.RoomStartOk())
        self.enviar_para_sala(sala, protocol.RoomStarted(sala.id, self.nomes_da_sala(sala), sala.rodadas))
        self.iniciar_rodada(sala)

    def iniciar_rodada(self, sala):
        """
        Sorteia a palavra, avisa a sala (ROUND START) e abre o primeiro turno.

        O ROUND START leva a MASCARA ("______"), nunca a palavra de verdade: ela so e
        revelada no ROUND END. Por isso um cliente alterado ñ consegue "espiar" a resposta.

        Chamado de DOIS lugares: do iniciar_partida() (rodada 1) e do timer da pausa (as
        outras). Nos dois casos ja esta com o Lock em maos.
        """
        candidatas = banco_palavras.filtrar_palavras(self.palavras, sala.dificuldade, sala.categoria_escolhida)
        palavra, categoria = banco_palavras.sortear_palavra(candidatas, sala.palavras_usadas)
        sala.iniciar_rodada(palavra, categoria)
        self.print(f"Sala {sala.id}: rodada {sala.rodada_atual}/{sala.rodadas}. Palavra: {palavra} ({categoria})")

        self.enviar_para_sala(sala, protocol.RoundStart(sala.id, sala.rodada_atual, sala.rodadas,
                                                        sala.categoria, sala.mascara()))
        self.enviar_turno(sala)

    def proxima_rodada(self, sala_id, rodada):
        """
        Chamado pelo timer quando acaba a pausa de 3 s entre as rodadas.

        O timer roda em OUTRA thread, entao ele mesmo pega o Lock (as outras funcoes
        recebem o Lock ja pego pelo handle_cliente). Durante a pausa muita coisa pode ter
        acontecido: a sala sumiu, a partida foi interrompida... Por isso confere antes
        e compara o numero da rodada, pra ñ iniciar uma rodada "velha".
        """
        # Chamado pelo timer da pausa entre rodadas
        with self.lock:
            sala = self.get_sala(sala_id)
            if not sala or sala.estado != "em andamento" or sala.rodada_atual != rodada:
                return  # a partida acabou ou a sala sumiu durante a pausa
            self.iniciar_rodada(sala)

    def encerrar_rodada(self, sala, motivo):
        """
        Fecha a rodada: revela a palavra, mostra o placar e decide o que vem depois.

        O 'motivo' e um de PALPITE, PALAVRA_COMPLETA, LIMITE_ERROS ou INTERROMPIDA (regras.md 3.7).
        Depois disso, tem tres caminhos:
          - INTERROMPIDA (sobrou 1 jogador) -> acaba a partida, sem vencedor;
          - era a ultima rodada -> acaba a partida, normal;
          - senao -> pausa de 3 s e o timer chama proxima_rodada().
        """
        sala.cancelar_timer()
        # Marca como inativa JA: durante a pausa, qualquer jogada leva SEM_RODADA_ATIVA
        sala.rodada_ativa = False
        self.print(f"Sala {sala.id}: fim da rodada {sala.rodada_atual} ({motivo})")
        # E AQUI que a palavra de verdade sai do servidor, so no fim da rodada
        self.enviar_para_sala(sala, protocol.RoundEnd(sala.id, sala.rodada_atual, sala.palavra.upper(),
                                                      motivo, self.placar_com_nomes(sala)))

        if motivo == protocol.MOTIVO_INTERROMPIDA:
            self.encerrar_partida(sala, protocol.MOTIVO_INTERROMPIDA)
        elif sala.rodada_atual >= sala.rodadas:
            self.encerrar_partida(sala, protocol.MOTIVO_NORMAL)
        else:
            # Pausa para os jogadores verem o resultado.
            # Timer = uma thread que dorme N segundos e depois roda a funcao; da pra cancelar.
            # daemon=True pelo mesmo motivo da thread de aceite (ñ segurar o encerramento).
            sala.timer = threading.Timer(PAUSA_ENTRE_RODADAS, self.proxima_rodada, args=(sala.id, sala.rodada_atual))
            sala.timer.daemon = True
            sala.timer.start()

    def encerrar_partida(self, sala, motivo):
        """
        Termina a partida: manda o GAME OVER com os vencedores e deixa a sala pronta pra jogar de novo.

        Os jogadores continuam na sala (estado 'finalizada') e o dono pode iniciar outra
        partida (regras.md 3.8). Se foi INTERROMPIDA, ninguem vence (lista vazia).
        """
        sala.cancelar_timer()
        sala.rodada_ativa = False
        sala.estado = "finalizada"

        vencedores = []
        if motivo == protocol.MOTIVO_NORMAL:
            for jogador_id in sala.vencedores():
                vencedores.append(self.nome(jogador_id))

        self.print(f"Sala {sala.id}: fim de jogo ({motivo}). Vencedores: {vencedores}")
        self.enviar_para_sala(sala, protocol.GameOver(sala.id, vencedores, self.placar_com_nomes(sala), motivo))
        self.atualizar_sala(sala.id)  # avisa se a sala ja pode iniciar de novo

    def enviar_turno(self, sala):
        """
        Abre um turno novo: avisa de quem e a vez (TURN) e liga o relogio de 30 s.

        Aqui mora o truque do 'numero_turno', que achei babado de simples. O problema:
        o jogador pode jogar quase no mesmo instante em que o relogio estoura. Os dois
        ficam esperando o Lock, e um deles passa primeiro. Se o relogio perder a
        corrida e acordar DEPOIS, ele ia dar timeout num turno que ja acabou. So que o
        cancel() ñ para um timer que ja disparou. Solucao: cada turno tem um NUMERO, o
        timer leva o numero do turno dele, e quando acorda confere se ainda e o turno atual.
        Ver tempo_esgotado() e README ("Concorrencia").
        """
        sala.cancelar_timer()
        sala.numero_turno += 1
        self.enviar_para_sala(sala, protocol.Turn(sala.id, self.nome(sala.jogador_da_vez()), TEMPO_TURNO))

        sala.timer = threading.Timer(TEMPO_TURNO, self.tempo_esgotado, args=(sala.id, sala.numero_turno))
        sala.timer.daemon = True
        sala.timer.start()

    def tempo_esgotado(self, sala_id, numero_turno):
        """
        Chamado pelo timer quando os 30 s do turno acabam. Avisa a sala (TURN TIMEOUT) e passa a vez.

        Estourar o tempo ñ tira ponto nem conta erro (regras.md 3.3). Roda em outra thread,
        por isso pega o Lock sozinho e confere se o turno ainda e o MESMO (ver enviar_turno).
        """
        with self.lock:
            sala = self.get_sala(sala_id)
            if not sala or not sala.rodada_ativa or sala.numero_turno != numero_turno:
                return  # turno ja acabou por outro motivo
            nome = self.nome(sala.jogador_da_vez())
            self.print(f"Sala {sala.id}: tempo esgotado para {nome}")
            self.enviar_para_sala(sala, protocol.TurnTimeout(sala.id, nome))
            sala.passar_vez()
            self.enviar_turno(sala)

    def receber_jogada(self, conn, id, mensagem):
        """
        Trata o TURN RESPONSE: a jogada (letra ou palpite) do jogador da vez. E o coracao do jogo.

        Em ordem:
          1) valida: sala, rodada ativa, e a vez dele, resposta nao vazia, e se a letra/palpite
             presta. A ordem e a do protocolo.md 3.9. Jogada invalida so gera ERROR: ñ passa a
             vez e ñ reinicia o prazo (regras.md 3.3);
          2) aplica na Sala (letra ou palpite) e pega os pontos;
          3) responde TURN RESPONSE OK so pra quem jogou, depois manda o resultado pra sala toda;
          4) decide o que vem: acabou a rodada? ou passa a vez?

        O servidor ñ confia em NADA que vem do cliente: ate o cliente "oficial" ja filtra,
        mas um cliente alterado poderia mandar qualquer coisa. Por isso tudo e conferido aqui.
        """
        sala = self.get_sala(mensagem.room_id)
        if not sala or id not in sala.jogadores:
            self.erro(conn, protocol.SALA_NAO_PARTICIPA, "voce nao participa desta sala")
            return
        if sala.estado != "em andamento" or not sala.rodada_ativa:
            self.erro(conn, protocol.SEM_RODADA_ATIVA, "nao ha rodada em andamento")
            return
        if sala.jogador_da_vez() != id:
            self.erro(conn, protocol.NAO_E_SUA_VEZ, "nao e sua vez")
            return

        resposta = mensagem.answer.strip()
        if resposta == "":
            self.erro(conn, protocol.RESPOSTA_VAZIA, "resposta vazia")
            return

        if mensagem.guess:
            # --- palpite: a palavra inteira ---
            # Qualquer tamanho vale: so recusa caracteres que nao formam palavra
            if not banco_palavras.so_caracteres_permitidos(resposta):
                self.erro(conn, protocol.PALPITE_INVALIDO, "use apenas letras, espaco e hifen")
                return
            # CUIDADO: o timer so e cancelado DEPOIS das validacoes. Se fosse antes, uma
            # jogada recusada reiniciaria o prazo, e o regras.md diz que NAO reinicia.
            sala.cancelar_timer()
            pontos = sala.tentar_palpite(id, resposta)
        else:
            # --- letra ---
            if not banco_palavras.letra_valida(resposta):
                self.erro(conn, protocol.LETRA_INVALIDA, "envie uma unica letra")
                return
            letra = banco_palavras.normalizar(resposta)  # "Ã" vira "a" (ver banco_palavras.py)
            if letra in sala.letras_usadas:
                self.erro(conn, protocol.LETRA_REPETIDA, "letra ja usada")
                return
            sala.cancelar_timer()
            pontos = sala.tentar_letra(id, letra)
        # Letra certa: pontos >= 1. Palpite certo: +5. Letra errada: 0. Palpite errado: negativo.
        acertou = pontos > 0

        nome = self.nome(id)
        self.print(f"Sala {sala.id}: {nome} tentou '{resposta}' -> {pontos} pontos ({sala.mascara()}, erros {sala.erros})")
        # Primeiro a confirmacao so pra quem jogou, depois o resultado pra todos (inclusive ele)
        self.responder(conn, protocol.TurnResponseOk())
        self.enviar_para_sala(sala, protocol.TurnResponseBroadcast(
            sala.id, nome, mensagem.guess, resposta, acertou, sala.mascara(),
            pontos, sala.erros, sala.letras_para_mostrar()))

        # O que vem depois (regras.md 3.7). A ordem importa: palpite certo vence qualquer outra condicao.
        if mensagem.guess and acertou:
            self.encerrar_rodada(sala, protocol.MOTIVO_PALPITE)
        elif sala.palavra_completa():
            self.encerrar_rodada(sala, protocol.MOTIVO_PALAVRA_COMPLETA)
        elif sala.erros >= MAX_ERROS:
            self.encerrar_rodada(sala, protocol.MOTIVO_LIMITE_ERROS)
        else:
            sala.passar_vez()
            self.enviar_turno(sala)

    # -----------------------------------------------------------
    # Saida e desconexao
    # -----------------------------------------------------------
    def sair_sala(self, id, sala):
        """
        Tira o jogador da sala e cuida de tudo que isso causa. Usado em DOIS casos: o jogador
        pediu pra sair (ROOM LEAVE) ou a conexao dele caiu. Pro resto do jogo da no mesmo (regras.md 2.6).

        Possibilidades, nesta ordem:
          - a sala ficou vazia -> some;
          - partida rodando e sobrou so 1 -> a partida e interrompida (sem vencedor);
          - senao -> avisa os que ficaram, e se era a vez de quem saiu, abre o turno do proximo.
        """
        # Usado ao sair da sala (ROOM LEAVE) e ao desconectar
        # CUIDADO: 'era_vez' tem que ser calculado ANTES do remover_jogador, pq depois que
        # ele sai a fila muda e ñ da mais pra saber de quem era a vez.
        era_vez = sala.rodada_ativa and sala.jogador_da_vez() == id
        sala.remover_jogador(id)

        if sala.num_jogadores == 0:
            sala.cancelar_timer()
            del self.salas[sala.id]
            self.print(f"Sala {sala.id} removida (vazia)")
            return

        if sala.estado == "em andamento" and sala.num_jogadores < MIN_JOGADORES:
            # Sobrou um jogador: a partida e interrompida
            if sala.rodada_ativa:
                self.encerrar_rodada(sala, protocol.MOTIVO_INTERROMPIDA)
            else:
                self.encerrar_partida(sala, protocol.MOTIVO_INTERROMPIDA)
            return  # encerrar_partida ja envia o ROOM UPDATE

        self.atualizar_sala(sala.id)
        if era_vez:
            # a vez ja aponta para o proximo jogador (o remover_jogador arrumou)
            self.enviar_turno(sala)

    def desconectar(self, id):
        """
        Limpeza quando a thread de um jogador termina (ele fechou o programa, a rede caiu
        ou mandou um tamanho absurdo). Tira ele da sala e libera tudo que era dele.

        Pega o Lock pq mexe no estado compartilhado. Se o servidor esta desligando
        ('encerrando'), ñ faz nada: o fechar() ja cuidou de todas as conexoes.
        """
        with self.lock:
            if self.encerrando:
                return  # fechar() ja cuidou de todas as conexoes
            self.print(f"{self.nome(id)} desconectou")
            # Primeiro sai da sala (isso avisa os outros jogadores)...
            sala = self.sala_do_jogador(id)
            if sala is not None:
                self.sair_sala(id, sala)

            # ...depois solta o resto: socket, chave de cifragem e cadastro do usuario
            if id in self.clientes:
                conn = self.clientes[id]["socket"]
                if conn in self.boxes:
                    del self.boxes[conn]
                conn.close()
                del self.clientes[id]
            if id in self.users:
                del self.users[id]


if __name__ == "__main__":
    # Uso: python3 -m servidor.server [porta]
    # O '-m' (rodar como modulo, a partir da pasta entrega/) e necessario pq os imports
    # acima ('from protocol import ...', 'from servidor import ...') partem dessa pasta.
    # Rodar "python server.py" direto quebra esses imports.
    porta = PORT
    if len(sys.argv) > 1:
        porta = int(sys.argv[1])
    server = Server(HOST, porta)
    server.iniciar()

    # A thread principal so fica dormindo. Ela PRECISA continuar viva: todas as outras
    # threads sao daemon, e threads daemon morrem junto com o programa. Se a principal
    # terminasse, o servidor acabava na hora.
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        # Ctrl+C
        server.print("Encerrando servidor...")
    except Exception as e:
        server.print(f"Erro inesperado: {e}")
    finally:
        server.fechar()
