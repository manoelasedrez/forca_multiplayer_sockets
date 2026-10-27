"""
Mensagens do protocolo forca1.0 (versao simples).

No fio, cada mensagem e:  <size: 4 bytes (struct "!I")> + <corpo em UTF-8>
O size e o tamanho do corpo (nao conta os 4 bytes do size).
O corpo e texto: 1a linha = comando, demais = "chave: valor", cada linha termina com \r\n.

Enviar:   sock.sendall(RoomJoinRequest("abc").encode())
Receber:  msg = receive_message(sock)
"""

import struct

CRLF = "\r\n"
VERSION = "forca1.0"

# Maior corpo aceito, em bytes. As mensagens do jogo tem poucas centenas de bytes;
# o limite evita que alguem anuncie um tamanho enorme e prenda o servidor lendo.
MAX_TAMANHO_MENSAGEM = 16384


class ErroProtocolo(Exception):
    """Corpo malformado (comando desconhecido, header faltando, valor invalido).
    O corpo ja foi lido inteiro, entao a conexao pode continuar."""


class ErroTamanho(Exception):
    """Tamanho anunciado acima do limite. Nao da para saber onde comeca a
    proxima mensagem, entao a conexao precisa ser encerrada."""

# Motivos de fim de rodada (ROUND END)
MOTIVO_PALPITE = "PALPITE"
MOTIVO_PALAVRA_COMPLETA = "PALAVRA_COMPLETA"
MOTIVO_LIMITE_ERROS = "LIMITE_ERROS"
MOTIVO_INTERROMPIDA = "INTERROMPIDA"

# Motivos de fim de partida (GAME OVER)
MOTIVO_NORMAL = "NORMAL"
# MOTIVO_INTERROMPIDA tambem vale para GAME OVER

# Codigos de erro (ERROR)
MENSAGEM_INVALIDA = "MENSAGEM_INVALIDA"
ERRO_INTERNO = "ERRO_INTERNO"
NAO_CONECTADO = "NAO_CONECTADO"
JA_CONECTADO = "JA_CONECTADO"
JA_EM_SALA = "JA_EM_SALA"
LIMITE_SALAS_SERVIDOR = "LIMITE_SALAS_SERVIDOR"
NOME_SALA_INVALIDO = "NOME_SALA_INVALIDO"
NUM_JOGADORES_INVALIDO = "NUM_JOGADORES_INVALIDO"
DIFICULDADE_INVALIDA = "DIFICULDADE_INVALIDA"
RODADAS_INVALIDAS = "RODADAS_INVALIDAS"
CATEGORIA_INVALIDA = "CATEGORIA_INVALIDA"
PALAVRAS_INSUFICIENTES = "PALAVRAS_INSUFICIENTES"
CODIGO_INVALIDO = "CODIGO_INVALIDO"
SALA_INEXISTENTE = "SALA_INEXISTENTE"
PARTIDA_EM_ANDAMENTO = "PARTIDA_EM_ANDAMENTO"
SALA_CHEIA = "SALA_CHEIA"
SALA_NAO_PARTICIPA = "SALA_NAO_PARTICIPA"
APENAS_DONO = "APENAS_DONO"
JOGADORES_INSUFICIENTES = "JOGADORES_INSUFICIENTES"
SEM_RODADA_ATIVA = "SEM_RODADA_ATIVA"
NAO_E_SUA_VEZ = "NAO_E_SUA_VEZ"
RESPOSTA_VAZIA = "RESPOSTA_VAZIA"
LETRA_INVALIDA = "LETRA_INVALIDA"
LETRA_REPETIDA = "LETRA_REPETIDA"
PALPITE_INVALIDO = "PALPITE_INVALIDO"


# ---------------------------------------------------------------
# Funcoes auxiliares
# ---------------------------------------------------------------
def bool_to_text(valor):
    if valor:
        return "true"
    return "false"


def text_to_bool(texto):
    return texto == "true"


def list_to_text(lista):
    return ", ".join(lista)


def text_to_list(texto):
    itens = []
    for item in texto.split(","):
        item = item.strip()
        if item != "":
            itens.append(item)
    return itens


def users_to_text(lista):
    return list_to_text(lista)


def text_to_users(texto):
    return text_to_list(texto)


def placar_to_text(placar):
    # [("ana", 8), ("bob", -2)] -> "ana=8, bob=-2"
    partes = []
    for nome, pontos in placar:
        partes.append(nome + "=" + str(pontos))
    return ", ".join(partes)


def text_to_placar(texto):
    placar = []
    for item in text_to_list(texto):
        nome, pontos = item.split("=", 1)
        placar.append((nome.strip(), int(pontos)))
    return placar


# ---------------------------------------------------------------
# Classe base
# ---------------------------------------------------------------
class Message:
    def first_line(self):
        return ""

    def headers(self):
        # lista de (chave, valor)
        return []

    def to_text(self):
        texto = self.first_line() + CRLF
        for chave, valor in self.headers():
            texto += chave + ": " + str(valor) + CRLF
        return texto

    def encode(self):
        corpo = self.to_text().encode("utf-8")
        tamanho = struct.pack("!I", len(corpo))
        return tamanho + corpo


# ---------------------------------------------------------------
# Conexao
# ---------------------------------------------------------------
class ConnectRequest(Message):
    def __init__(self, public_key, username, version=VERSION):
        self.public_key = public_key
        self.username = username
        self.version = version

    def first_line(self):
        return "CONNECT " + self.version

    def headers(self):
        return [("public-key", self.public_key), ("username", self.username)]


class ConnectOk(Message):
    def __init__(self, public_key, categorias, version=VERSION):
        self.public_key = public_key
        self.categorias = categorias  # lista de categorias do banco de palavras
        self.version = version

    def first_line(self):
        return "CONNECT OK " + self.version

    def headers(self):
        return [("public-key", self.public_key), ("categorias", list_to_text(self.categorias))]


class ConnectError(Message):
    def __init__(self, data="", version=VERSION):
        self.data = data
        self.version = version

    def first_line(self):
        return "CONNECT ERROR " + self.version

    def to_text(self):
        # depois da 1a linha vai o <DATA> do jeito que veio
        return self.first_line() + CRLF + self.data


# ---------------------------------------------------------------
# Salas
# ---------------------------------------------------------------
class RoomCreateRequest(Message):
    def __init__(self, numero_jogadores, dificuldade, room_name, rounds, categoria):
        self.numero_jogadores = numero_jogadores  # maximo de jogadores
        self.dificuldade = dificuldade
        self.room_name = room_name  # apelido da sala
        self.rounds = rounds
        self.categoria = categoria  # nome da categoria ou "qualquer"

    def first_line(self):
        return "ROOM CREATE"

    def headers(self):
        return [
            ("num-players", self.numero_jogadores),
            ("dificuldade", self.dificuldade),
            ("room-name", self.room_name),
            ("rounds", self.rounds),
            ("categoria", self.categoria),
        ]


class RoomCreateOk(Message):
    def __init__(self, room_id):
        self.room_id = room_id

    def first_line(self):
        return "ROOM CREATE OK"

    def headers(self):
        return [("room-id", self.room_id)]


class RoomJoinRequest(Message):
    def __init__(self, room_id):
        self.room_id = room_id

    def first_line(self):
        return "ROOM JOIN"

    def headers(self):
        return [("room-id", self.room_id)]


class RoomJoinOk(Message):
    def __init__(self, users, dificuldade, room_name, rounds, categoria):
        self.users = users  # lista de nomes
        self.dificuldade = dificuldade
        self.room_name = room_name
        self.rounds = rounds
        self.categoria = categoria

    def first_line(self):
        return "ROOM JOIN OK"

    def headers(self):
        return [
            ("USERS", users_to_text(self.users)),
            ("dificuldade", self.dificuldade),
            ("room-name", self.room_name),
            ("rounds", self.rounds),
            ("categoria", self.categoria),
        ]


class RoomLeaveRequest(Message):
    def __init__(self, room_id):
        self.room_id = room_id

    def first_line(self):
        return "ROOM LEAVE"

    def headers(self):
        return [("room-id", self.room_id)]


class RoomLeaveOk(Message):
    def first_line(self):
        return "ROOM LEAVE OK"


class RoomUpdate(Message):
    def __init__(self, room_id, users, dificuldade, ready):
        self.room_id = room_id
        self.users = users
        self.dificuldade = dificuldade
        self.ready = ready  # True ou False

    def first_line(self):
        return "ROOM UPDATE"

    def headers(self):
        return [
            ("room-id", self.room_id),
            ("USERS", users_to_text(self.users)),
            ("dificuldade", self.dificuldade),
            ("ready", bool_to_text(self.ready)),
        ]


class RoomStartRequest(Message):
    def __init__(self, room_id):
        self.room_id = room_id

    def first_line(self):
        return "ROOM START"

    def headers(self):
        return [("room-id", self.room_id)]


class RoomStartOk(Message):
    def first_line(self):
        return "ROOM START OK"


class RoomStarted(Message):
    def __init__(self, room_id, users, rounds):
        self.room_id = room_id
        self.users = users
        self.rounds = rounds

    def first_line(self):
        return "ROOM STARTED"

    def headers(self):
        return [
            ("room-id", self.room_id),
            ("USERS", users_to_text(self.users)),
            ("rounds", self.rounds),
        ]


# ---------------------------------------------------------------
# Rodadas
# ---------------------------------------------------------------
class RoundStart(Message):
    def __init__(self, room_id, round, rounds, categoria, word):
        self.room_id = room_id
        self.round = round  # numero da rodada (1, 2, ...)
        self.rounds = rounds
        self.categoria = categoria
        self.word = word  # ex: "_____"

    def first_line(self):
        return "ROUND START"

    def headers(self):
        return [
            ("room-id", self.room_id),
            ("round", self.round),
            ("rounds", self.rounds),
            ("categoria", self.categoria),
            ("word", self.word),
        ]


class RoundEnd(Message):
    def __init__(self, room_id, round, word, motivo, placar):
        self.room_id = room_id
        self.round = round
        self.word = word  # palavra revelada
        self.motivo = motivo
        self.placar = placar  # lista de (nome, pontos)

    def first_line(self):
        return "ROUND END"

    def headers(self):
        return [
            ("room-id", self.room_id),
            ("round", self.round),
            ("word", self.word),
            ("motivo", self.motivo),
            ("placar", placar_to_text(self.placar)),
        ]


# ---------------------------------------------------------------
# Turnos
# ---------------------------------------------------------------
class Turn(Message):
    def __init__(self, room_id, user_turn, tempo):
        self.room_id = room_id
        self.user_turn = user_turn
        self.tempo = tempo  # segundos do turno

    def first_line(self):
        return "TURN"

    def headers(self):
        return [("room-id", self.room_id), ("user-turn", self.user_turn), ("tempo", self.tempo)]


class TurnTimeout(Message):
    def __init__(self, room_id, user_turn):
        self.room_id = room_id
        self.user_turn = user_turn  # quem perdeu a vez

    def first_line(self):
        return "TURN TIMEOUT"

    def headers(self):
        return [("room-id", self.room_id), ("user-turn", self.user_turn)]


class TurnResponseRequest(Message):
    # guess=True: chute da palavra inteira / False: uma letra
    def __init__(self, room_id, guess, answer):
        self.room_id = room_id
        self.guess = guess
        self.answer = answer

    def first_line(self):
        return "TURN RESPONSE"

    def headers(self):
        return [
            ("room-id", self.room_id),
            ("guess", bool_to_text(self.guess)),
            ("answer", self.answer),
        ]


class TurnResponseOk(Message):
    def first_line(self):
        return "TURN RESPONSE OK"


class TurnResponseBroadcast(Message):
    def __init__(self, room_id, user_turn, guess, answer, accepted, word, pontos, erros, letras):
        self.room_id = room_id
        self.user_turn = user_turn
        self.guess = guess
        self.answer = answer
        self.accepted = accepted
        self.word = word
        self.pontos = pontos  # pontos ganhos (ou perdidos) nesta jogada
        self.erros = erros  # erros da rodada ate agora
        self.letras = letras  # lista de letras ja usadas na rodada

    def first_line(self):
        return "TURN RESPONSE"

    def headers(self):
        return [
            ("room-id", self.room_id),
            ("user-turn", self.user_turn),
            ("guess", bool_to_text(self.guess)),
            ("answer", self.answer),
            ("accepted", bool_to_text(self.accepted)),
            ("word", self.word),
            ("pontos", self.pontos),
            ("erros", self.erros),
            ("letras", list_to_text(self.letras)),
        ]


class GameOver(Message):
    def __init__(self, room_id, winners, placar, motivo):
        self.room_id = room_id
        self.winners = winners  # lista de nomes (vazia = ninguem venceu)
        self.placar = placar  # lista de (nome, pontos)
        self.motivo = motivo

    def first_line(self):
        return "GAME OVER"

    def headers(self):
        return [
            ("room-id", self.room_id),
            ("winners", users_to_text(self.winners)),
            ("placar", placar_to_text(self.placar)),
            ("motivo", self.motivo),
        ]


class ErrorMessage(Message):
    def __init__(self, code, error):
        self.code = code  # um dos codigos de erro acima
        self.error = error  # texto para mostrar ao jogador

    def first_line(self):
        return "ERROR"

    def headers(self):
        return [("code", self.code), ("error", self.error)]


# ---------------------------------------------------------------
# Decodificar: corpo (bytes, sem o size) -> objeto
# ---------------------------------------------------------------
def read_headers(texto):
    """Transforma 'chave: valor\\r\\n...' em um dicionario."""
    h = {}
    for linha in texto.split(CRLF):
        if linha == "":
            continue
        if ":" not in linha:
            raise ValueError("header sem ':' -> " + linha)
        chave, valor = linha.split(":", 1)
        h[chave.strip().lower()] = valor.strip()
    return h


def decode(corpo):
    """Corpo (bytes) -> objeto Message. Lanca ErroProtocolo se estiver malformado."""
    try:
        return decode_corpo(corpo)
    except KeyError as e:
        raise ErroProtocolo("atributo obrigatorio ausente: " + str(e).strip("'"))
    except (ValueError, IndexError, UnicodeDecodeError) as e:
        raise ErroProtocolo(str(e))


def decode_corpo(corpo):
    texto = corpo.decode("utf-8")
    first, rest = texto.split(CRLF, 1)

    # CONNECT: a versao vem na primeira linha
    if first.startswith("CONNECT ERROR "):
        return ConnectError(rest, first.split(" ")[2])

    h = read_headers(rest)

    if first.startswith("CONNECT OK "):
        return ConnectOk(h["public-key"], text_to_list(h["categorias"]), first.split(" ")[2])
    if first.startswith("CONNECT "):
        return ConnectRequest(h["public-key"], h["username"], first.split(" ")[1])

    if first == "ROOM CREATE":
        return RoomCreateRequest(int(h["num-players"]), h["dificuldade"], h["room-name"],
                                 int(h["rounds"]), h["categoria"])
    if first == "ROOM CREATE OK":
        return RoomCreateOk(h["room-id"])
    if first == "ROOM JOIN":
        return RoomJoinRequest(h["room-id"])
    if first == "ROOM JOIN OK":
        return RoomJoinOk(text_to_users(h["users"]), h["dificuldade"], h["room-name"],
                          int(h["rounds"]), h["categoria"])
    if first == "ROOM LEAVE":
        return RoomLeaveRequest(h["room-id"])
    if first == "ROOM LEAVE OK":
        return RoomLeaveOk()
    if first == "ROOM UPDATE":
        return RoomUpdate(h["room-id"], text_to_users(h["users"]), h["dificuldade"], text_to_bool(h["ready"]))
    if first == "ROOM START":
        return RoomStartRequest(h["room-id"])
    if first == "ROOM START OK":
        return RoomStartOk()
    if first == "ROOM STARTED":
        return RoomStarted(h["room-id"], text_to_users(h["users"]), int(h["rounds"]))

    if first == "ROUND START":
        return RoundStart(h["room-id"], int(h["round"]), int(h["rounds"]), h["categoria"], h["word"])
    if first == "ROUND END":
        return RoundEnd(h["room-id"], int(h["round"]), h["word"], h["motivo"], text_to_placar(h["placar"]))

    if first == "TURN":
        return Turn(h["room-id"], h["user-turn"], int(h["tempo"]))
    if first == "TURN TIMEOUT":
        return TurnTimeout(h["room-id"], h["user-turn"])
    if first == "TURN RESPONSE OK":
        return TurnResponseOk()
    if first == "TURN RESPONSE":
        # o request e o broadcast tem a mesma 1a linha;
        # o broadcast e o que tem "user-turn"
        if "user-turn" in h:
            return TurnResponseBroadcast(
                h["room-id"], h["user-turn"], text_to_bool(h["guess"]),
                h["answer"], text_to_bool(h["accepted"]), h["word"],
                int(h["pontos"]), int(h["erros"]), text_to_list(h["letras"]),
            )
        return TurnResponseRequest(h["room-id"], text_to_bool(h["guess"]), h["answer"])

    if first == "GAME OVER":
        return GameOver(h["room-id"], text_to_users(h["winners"]), text_to_placar(h["placar"]), h["motivo"])
    if first == "ERROR":
        return ErrorMessage(h["code"], h["error"])

    raise ValueError("comando desconhecido: " + first)


# ---------------------------------------------------------------
# Socket
# ---------------------------------------------------------------
def receive_exact(sock, quantidade):
    """Le exatamente 'quantidade' bytes (um recv pode devolver menos)."""
    dados = b""
    while len(dados) < quantidade:
        pedaco = sock.recv(quantidade - len(dados))
        if pedaco == b"":
            raise ConnectionError("conexao fechada")
        dados += pedaco
    return dados


def receive_message(sock):
    """Le uma mensagem inteira do socket.
    Lanca ErroTamanho (encerrar a conexao) ou ErroProtocolo (pode continuar)."""
    tamanho = struct.unpack("!I", receive_exact(sock, 4))[0]
    if tamanho > MAX_TAMANHO_MENSAGEM:
        raise ErroTamanho(f"mensagem de {tamanho} bytes (limite {MAX_TAMANHO_MENSAGEM})")
    corpo = receive_exact(sock, tamanho)
    return decode(corpo)


def send_message(sock, msg: Message):
    """Envia uma mensagem (objeto Message) pelo socket."""
    if not isinstance(msg, Message):
        raise ValueError("msg deve ser uma instancia de Message")
    sock.sendall(msg.encode())
