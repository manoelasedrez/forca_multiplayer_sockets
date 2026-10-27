import socket
import sys
import time
import threading

from nacl.encoding import Base64Encoder
from nacl.exceptions import CryptoError
from protocol import protocol
from servidor import banco_palavras
import random
from nacl.public import PrivateKey, PublicKey

HOST = "0.0.0.0"  # aceita conexoes de qualquer interface (rede local)
PORT = 38905

# Keepalive do TCP: percebe um cliente que sumiu sem fechar a conexao
# (cabo desligado, maquina travada). Valores em segundos.
KEEPALIVE_OCIOSO = 10
KEEPALIVE_INTERVALO = 5
KEEPALIVE_TENTATIVAS = 3

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
CARACTERES_CODIGO = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
TAMANHO_CODIGO = 4
TAMANHO_MAX_NOME_SALA = 20

# Nome de usuario: estes caracteres quebrariam as listas do protocolo
TAMANHO_MAX_NOME_USUARIO = 15
CARACTERES_PROIBIDOS_NOME = ",:="


def pegar_pontos(item):
    # usado para ordenar o placar: item = (id, pontos)
    return item[1]


class Sala:
    def __init__(self, sala_id, nome, dono_addr, dificuldade, numero_jogadores, rodadas, categoria):
        self.nome = nome  # apelido da sala
        self.dono_addr = dono_addr
        self.dificuldade = dificuldade
        self.max_jogadores = numero_jogadores
        self.rodadas = rodadas
        self.categoria_escolhida = categoria  # categoria da sala ou "qualquer"
        self.jogadores = [dono_addr]
        self.num_jogadores = 1
        self.estado = "aguardando"  # ou "em andamento", "finalizada"
        self.id = sala_id

        # Estado da partida
        self.placar = {}  # id do jogador -> pontos
        self.rodada_atual = 0
        self.rodada_ativa = False  # False tambem na pausa entre rodadas
        self.palavras_usadas = []  # normalizadas, para nao repetir na partida
        self.inicio_rodada = -1  # indice de quem comecou a rodada

        # Estado da rodada
        self.palavra = ""
        self.categoria = ""  # categoria da palavra sorteada
        self.letras_usadas = []  # letras ja normalizadas
        self.erros = 0
        self.vez = 0  # indice em self.jogadores
        self.timer = None
        self.numero_turno = 0  # usado para ignorar timers antigos

    def adicionar_jogador(self, jogador_addr):
        if self.num_jogadores < self.max_jogadores:
            self.jogadores.append(jogador_addr)
            self.num_jogadores += 1
            return True
        return False

    def remover_jogador(self, jogador_addr):
        indice = self.jogadores.index(jogador_addr)
        self.jogadores.remove(jogador_addr)
        self.num_jogadores -= 1

        # Os pontos de quem sai deixam de contar
        if jogador_addr in self.placar:
            del self.placar[jogador_addr]

        # Mantem a vez no mesmo jogador (ou no proximo, se era a vez de quem saiu)
        if indice < self.vez:
            self.vez -= 1
        if self.num_jogadores > 0 and self.vez >= self.num_jogadores:
            self.vez = 0

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
        return self.num_jogadores >= MIN_JOGADORES and self.estado != "em andamento"

    def iniciar_partida(self):
        self.placar = {}
        for jogador in self.jogadores:
            self.placar[jogador] = 0
        self.rodada_atual = 0
        self.palavras_usadas = []
        self.inicio_rodada = -1  # a primeira rodada comeca com o primeiro da lista
        self.estado = "em andamento"

    def iniciar_rodada(self, palavra, categoria):
        self.rodada_atual += 1
        self.palavra = palavra
        self.categoria = categoria
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
        self.vez = (self.vez + 1) % self.num_jogadores

    def mascara(self):
        return banco_palavras.mascarar(self.palavra, self.letras_usadas)

    def tentar_letra(self, jogador, letra):
        # letra ja normalizada; devolve os pontos ganhos (0 se errou)
        self.letras_usadas.append(letra)
        pontos = banco_palavras.contar_ocorrencias(self.palavra, letra)
        if pontos == 0:
            self.erros += 1
        self.placar[jogador] += pontos
        return pontos

    def tentar_palpite(self, jogador, texto):
        # devolve os pontos ganhos (positivo) ou perdidos (negativo)
        texto = " ".join(texto.split())  # junta espacos repetidos
        if banco_palavras.normalizar(texto) == banco_palavras.normalizar(self.palavra):
            # revela a palavra inteira
            for c in banco_palavras.normalizar(self.palavra):
                if c not in self.letras_usadas and c not in banco_palavras.SEPARADORES:
                    self.letras_usadas.append(c)
            self.placar[jogador] += PONTOS_PALAVRA
            return PONTOS_PALAVRA
        self.erros += 1
        self.placar[jogador] -= PENALIDADE_PALPITE
        return -PENALIDADE_PALPITE

    def palavra_completa(self):
        return "_" not in self.mascara()

    def placar_ordenado(self):
        # Lista de (id, pontos), do maior para o menor.
        # Empatados ficam na ordem de entrada na sala.
        lista = []
        for jogador in self.jogadores:
            if jogador in self.placar:
                lista.append((jogador, self.placar[jogador]))
        return sorted(lista, key=pegar_pontos, reverse=True)

    def vencedores(self):
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
        letras = []
        for letra in self.letras_usadas:
            letras.append(letra.upper())
        return letras

    def cancelar_timer(self):
        if self.timer is not None:
            self.timer.cancel()
            self.timer = None


class Server(socket.socket):
    def __init__(self, host, port):
        super().__init__(socket.AF_INET, socket.SOCK_STREAM)
        self.host = host
        self.port = port
        self.public_key = None
        self.private_key = None

        self.clientes = {}

        self.users = {}  # Dicionário para armazenar informações dos usuários conectados

        self.salas = {}
        self.codigos_usados = []  # codigos nunca sao reaproveitados
        self.encerrando = False

        self.palavras = banco_palavras.carregar_palavras()
        self.categorias = banco_palavras.listar_categorias(self.palavras)
        self.lock = threading.Lock()  # protege salas e users entre as threads

    def print(self, msg):
        print(msg)

    def iniciar(self):
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

        self.private_key = PrivateKey.generate()
        self.public_key = self.private_key.public_key

        threading.Thread(target=self.aceitar_conexao_thread, daemon=True).start()

    def aceitar_conexao_thread(self):
        while True:
            try:
                conn, addr = self.accept()
            except OSError:
                if self.encerrando:
                    break
                raise
            id = f"{addr[0]}:{addr[1]}"
            self.print(f"Cliente conectado: {id}")
            self.ativar_keepalive(conn)
            self.clientes[id] = {"socket": conn, "addr": addr[0], "port": addr[1], "ip": addr[0]}
            threading.Thread(target=self.handle_cliente, args=(conn, id), daemon=True).start()

    def ativar_keepalive(self, conn):
        conn.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        # Os ajustes de tempo nao existem em todos os sistemas operacionais
        if hasattr(socket, "TCP_KEEPIDLE"):
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, KEEPALIVE_OCIOSO)
        if hasattr(socket, "TCP_KEEPINTVL"):
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, KEEPALIVE_INTERVALO)
        if hasattr(socket, "TCP_KEEPCNT"):
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, KEEPALIVE_TENTATIVAS)

    def fechar(self):
        with self.lock:  # espera terminar o que as outras threads estao fazendo
            self.encerrando = True
            for sala in list(self.salas.values()):
                sala.cancelar_timer()
            for cliente in list(self.clientes.values()):
                try:
                    cliente["socket"].shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                cliente["socket"].close()
            self.clientes.clear()
        self.close()

    def handle_cliente(self, conn, id):
        while True:
            try:
                mensagem = protocol.receive_message(conn)
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
                if not self.encerrando:
                    self.print(f"Conexão com {self.nome(id)} encerrada: {e}")
                break

            with self.lock:
                try:
                    self.handle_mensagem(conn, id, mensagem)
                except OSError:
                    pass  # falha ao enviar: o proximo recv percebe a desconexao
                except Exception as e:
                    # Erro inesperado no servidor: nao derruba a thread do cliente
                    self.print(f"Erro ao tratar {mensagem.first_line()} de {self.nome(id)}: {e}")
                    self.erro_seguro(conn, protocol.ERRO_INTERNO, "erro interno do servidor")

        if not self.encerrando:
            self.desconectar(id)

    def handle_mensagem(self, conn, id, mensagem):

        if isinstance(mensagem, protocol.ConnectRequest):
            if id in self.users:
                self.erro(conn, protocol.JA_CONECTADO, "voce ja esta conectado")
                return
            erro = self.validar_conexao(mensagem)
            if erro is not None:
                self.responder(conn, protocol.ConnectError(erro + "\r\n"))
                return
            try:
                # Guardada para a futura cifragem das mensagens
                chave_cliente = PublicKey(mensagem.public_key, encoder=Base64Encoder)
            except (CryptoError, ValueError, TypeError):
                self.responder(conn, protocol.ConnectError("chave publica invalida\r\n"))
                return
            self.users[id] = {
                "name": mensagem.username,
                "public_key": chave_cliente
                }
            chave_texto = self.public_key.encode(encoder=Base64Encoder).decode()
            resposta = protocol.ConnectOk(chave_texto, self.categorias)
            protocol.send_message(conn, resposta)
            self.print(f"Conexão com {id} estabelecida. Usuário: {mensagem.username}")
            return

        # Qualquer outra mensagem exige CONNECT antes
        if id not in self.users:
            self.erro(conn, protocol.NAO_CONECTADO, "envie CONNECT primeiro")
            return

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
            self.erro(conn, protocol.MENSAGEM_INVALIDA,
                      f"{mensagem.first_line()} nao e uma mensagem do cliente")

    def responder(self, conn, mensagem):
        protocol.send_message(conn, mensagem)

    def erro(self, conn, codigo, texto):
        self.responder(conn, protocol.ErrorMessage(codigo, texto))

    def erro_seguro(self, conn, codigo, texto):
        # Igual a erro(), mas ignora falha de envio (a conexao pode ja ter caido)
        try:
            self.erro(conn, codigo, texto)
        except OSError:
            pass

    def enviar_para_sala(self, sala, mensagem):
        for jogador_id in sala.jogadores:
            if jogador_id in self.clientes:
                try:
                    self.responder(self.clientes[jogador_id]["socket"], mensagem)
                except OSError:
                    pass  # a thread do cliente trata a desconexao

    def nome(self, id):
        if id in self.users:
            return self.users[id]["name"]
        return id

    def nomes_conectados(self):
        nomes = []
        for user in self.users.values():
            nomes.append(user["name"])
        return nomes

    def nomes_da_sala(self, sala):
        nomes = []
        for jogador_id in sala.jogadores:
            nomes.append(self.nome(jogador_id))
        return nomes

    def placar_com_nomes(self, sala):
        # [(id, pontos)] -> [(nome, pontos)], para enviar no protocolo
        placar = []
        for jogador_id, pontos in sala.placar_ordenado():
            placar.append((self.nome(jogador_id), pontos))
        return placar

    # -----------------------------------------------------------
    # Conexao
    # -----------------------------------------------------------
    def validar_conexao(self, mensagem):
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
        # Sorteia ate achar um codigo que nunca foi usado
        while True:
            codigo = ""
            for i in range(TAMANHO_CODIGO):
                codigo += random.choice(CARACTERES_CODIGO)
            if codigo not in self.codigos_usados:
                self.codigos_usados.append(codigo)
                return codigo

    def codigo_valido(self, codigo):
        codigo = codigo.strip().upper()
        if len(codigo) != TAMANHO_CODIGO:
            return False
        for c in codigo:
            if c not in CARACTERES_CODIGO:
                return False
        return True

    def receber_criar_sala(self, conn, id, mensagem):
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

        sala = self.criar_sala(id, nome_sala, mensagem.dificuldade, mensagem.numero_jogadores,
                               mensagem.rounds, mensagem.categoria)
        self.responder(conn, protocol.RoomCreateOk(sala.id))
        self.print(f"Sala {sala.id} '{sala.nome}' criada por {self.nome(id)} "
                   f"(ate {sala.max_jogadores} jogadores, {sala.rodadas} rodadas, {sala.dificuldade}, {sala.categoria_escolhida})")

    def receber_sair_sala(self, conn, id, mensagem):
        sala = self.get_sala(mensagem.room_id)
        if not sala or id not in sala.jogadores:
            self.erro(conn, protocol.SALA_NAO_PARTICIPA, "voce nao participa desta sala")
            return
        self.responder(conn, protocol.RoomLeaveOk())
        self.print(f"{self.nome(id)} saiu da sala {sala.id}")
        self.sair_sala(id, sala)

    def receber_entrar_sala(self, conn, id, mensagem):
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
        # aceita minusculas e espacos nas pontas
        return self.salas.get(sala_id.strip().upper())

    def sala_do_jogador(self, jogador_id):
        # No piloto cada jogador fica em no maximo uma sala
        for sala in self.salas.values():
            if jogador_id in sala.jogadores:
                return sala
        return None

    def entrar_sala(self, sala_id, jogador_id):
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
        sala = self.get_sala(sala_id)
        if sala:
            mensagem = protocol.RoomUpdate(sala.id, self.nomes_da_sala(sala), sala.dificuldade, sala.pode_iniciar())
            self.enviar_para_sala(sala, mensagem)

    # -----------------------------------------------------------
    # Partida e rodadas
    # -----------------------------------------------------------
    def iniciar_partida(self, conn, id, sala_id):
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
        candidatas = banco_palavras.filtrar_palavras(self.palavras, sala.dificuldade, sala.categoria_escolhida)
        palavra, categoria = banco_palavras.sortear_palavra(candidatas, sala.palavras_usadas)
        sala.iniciar_rodada(palavra, categoria)
        self.print(f"Sala {sala.id}: rodada {sala.rodada_atual}/{sala.rodadas}. Palavra: {palavra} ({categoria})")

        self.enviar_para_sala(sala, protocol.RoundStart(sala.id, sala.rodada_atual, sala.rodadas,
                                                        sala.categoria, sala.mascara()))
        self.enviar_turno(sala)

    def proxima_rodada(self, sala_id, rodada):
        # Chamado pelo timer da pausa entre rodadas
        with self.lock:
            sala = self.get_sala(sala_id)
            if not sala or sala.estado != "em andamento" or sala.rodada_atual != rodada:
                return  # a partida acabou ou a sala sumiu durante a pausa
            self.iniciar_rodada(sala)

    def encerrar_rodada(self, sala, motivo):
        sala.cancelar_timer()
        sala.rodada_ativa = False
        self.print(f"Sala {sala.id}: fim da rodada {sala.rodada_atual} ({motivo})")
        self.enviar_para_sala(sala, protocol.RoundEnd(sala.id, sala.rodada_atual, sala.palavra.upper(),
                                                      motivo, self.placar_com_nomes(sala)))

        if motivo == protocol.MOTIVO_INTERROMPIDA:
            self.encerrar_partida(sala, protocol.MOTIVO_INTERROMPIDA)
        elif sala.rodada_atual >= sala.rodadas:
            self.encerrar_partida(sala, protocol.MOTIVO_NORMAL)
        else:
            # Pausa para os jogadores verem o resultado
            sala.timer = threading.Timer(PAUSA_ENTRE_RODADAS, self.proxima_rodada, args=(sala.id, sala.rodada_atual))
            sala.timer.daemon = True
            sala.timer.start()

    def encerrar_partida(self, sala, motivo):
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
        sala.cancelar_timer()
        sala.numero_turno += 1
        self.enviar_para_sala(sala, protocol.Turn(sala.id, self.nome(sala.jogador_da_vez()), TEMPO_TURNO))

        sala.timer = threading.Timer(TEMPO_TURNO, self.tempo_esgotado, args=(sala.id, sala.numero_turno))
        sala.timer.daemon = True
        sala.timer.start()

    def tempo_esgotado(self, sala_id, numero_turno):
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
            # Qualquer tamanho vale: so recusa caracteres que nao formam palavra
            if not banco_palavras.so_caracteres_permitidos(resposta):
                self.erro(conn, protocol.PALPITE_INVALIDO, "use apenas letras, espaco e hifen")
                return
            sala.cancelar_timer()
            pontos = sala.tentar_palpite(id, resposta)
        else:
            if not banco_palavras.letra_valida(resposta):
                self.erro(conn, protocol.LETRA_INVALIDA, "envie uma unica letra")
                return
            letra = banco_palavras.normalizar(resposta)
            if letra in sala.letras_usadas:
                self.erro(conn, protocol.LETRA_REPETIDA, "letra ja usada")
                return
            sala.cancelar_timer()
            pontos = sala.tentar_letra(id, letra)
        acertou = pontos > 0

        nome = self.nome(id)
        self.print(f"Sala {sala.id}: {nome} tentou '{resposta}' -> {pontos} pontos ({sala.mascara()}, erros {sala.erros})")
        self.responder(conn, protocol.TurnResponseOk())
        self.enviar_para_sala(sala, protocol.TurnResponseBroadcast(
            sala.id, nome, mensagem.guess, resposta, acertou, sala.mascara(),
            pontos, sala.erros, sala.letras_para_mostrar()))

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
        # Usado ao sair da sala (ROOM LEAVE) e ao desconectar
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
            # a vez ja aponta para o proximo jogador
            self.enviar_turno(sala)

    def desconectar(self, id):
        with self.lock:
            if self.encerrando:
                return  # fechar() ja cuidou de todas as conexoes
            self.print(f"{self.nome(id)} desconectou")
            sala = self.sala_do_jogador(id)
            if sala is not None:
                self.sair_sala(id, sala)

            if id in self.clientes:
                self.clientes[id]["socket"].close()
                del self.clientes[id]
            if id in self.users:
                del self.users[id]


if __name__ == "__main__":
    # Uso: python3 -m servidor.server [porta]
    porta = PORT
    if len(sys.argv) > 1:
        porta = int(sys.argv[1])
    server = Server(HOST, porta)
    server.iniciar()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.print("Encerrando servidor...")
    except Exception as e:
        server.print(f"Erro inesperado: {e}")
    finally:
        server.fechar()
