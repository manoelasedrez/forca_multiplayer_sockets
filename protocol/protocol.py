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


# ---------------------------------------------------------------
# Funcoes auxiliares
# ---------------------------------------------------------------
def bool_to_text(valor):
    if valor:
        return "true"
    return "false"


def text_to_bool(texto):
    return texto == "true"


def users_to_text(lista):
    return ", ".join(lista)


def text_to_users(texto):
    usuarios = []
    for nome in texto.split(","):
        nome = nome.strip()
        if nome != "":
            usuarios.append(nome)
    return usuarios


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
    def __init__(self, public_key, version=VERSION):
        self.public_key = public_key
        self.version = version

    def first_line(self):
        return "CONNECT OK " + self.version

    def headers(self):
        return [("public-key", self.public_key)]


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
    def __init__(self, numero_jogadores, dificuldade):
        self.numero_jogadores = numero_jogadores
        self.dificuldade = dificuldade

    def first_line(self):
        return "ROOM CREATE"

    def headers(self):
        return [("num-players", self.numero_jogadores), ("dificuldade", self.dificuldade)]


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
    def __init__(self, users, dificuldade):
        self.users = users  # lista de nomes
        self.dificuldade = dificuldade

    def first_line(self):
        return "ROOM JOIN OK"

    def headers(self):
        return [("USERS", users_to_text(self.users)), ("dificuldade", self.dificuldade)]


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
    def first_line(self):
        return "ROOM START"


class RoomStartOk(Message):
    def first_line(self):
        return "ROOM START OK"


class RoomStarted(Message):
    def __init__(self, room_id, users, word):
        self.room_id = room_id
        self.users = users
        self.word = word  # ex: "_____"

    def first_line(self):
        return "ROOM STARTED"

    def headers(self):
        return [
            ("room-id", self.room_id),
            ("USERS", users_to_text(self.users)),
            ("word", self.word),
        ]


# ---------------------------------------------------------------
# Turnos
# ---------------------------------------------------------------
class Turn(Message):
    def __init__(self, room_id, user_turn):
        self.room_id = room_id
        self.user_turn = user_turn

    def first_line(self):
        return "TURN"

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
    def __init__(self, room_id, user_turn, guess, answer, accepted, word):
        self.room_id = room_id
        self.user_turn = user_turn
        self.guess = guess
        self.answer = answer
        self.accepted = accepted
        self.word = word

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
        ]


class GameOver(Message):
    def __init__(self, room_id, winner):
        self.room_id = room_id
        self.winner = winner

    def first_line(self):
        return "GAME OVER"

    def headers(self):
        return [("room-id", self.room_id), ("winner", self.winner)]


class ErrorMessage(Message):
    def __init__(self, error):
        self.error = error

    def first_line(self):
        return "ERROR"

    def headers(self):
        return [("error", self.error)]


# ---------------------------------------------------------------
# Decodificar: corpo (bytes, sem o size) -> objeto
# ---------------------------------------------------------------
def read_headers(texto):
    """Transforma 'chave: valor\\r\\n...' em um dicionario."""
    h = {}
    for linha in texto.split(CRLF):
        if linha == "":
            continue
        chave, valor = linha.split(":", 1)
        h[chave.strip().lower()] = valor.strip()
    return h


def decode(corpo):
    texto = corpo.decode("utf-8")
    first, rest = texto.split(CRLF, 1)

    # CONNECT: a versao vem na primeira linha
    if first.startswith("CONNECT ERROR "):
        return ConnectError(rest, first.split(" ")[2])

    h = read_headers(rest)

    if first.startswith("CONNECT OK "):
        return ConnectOk(h["public-key"], first.split(" ")[2])
    if first.startswith("CONNECT "):
        return ConnectRequest(h["public-key"], h["username"], first.split(" ")[1])

    if first == "ROOM CREATE":
        return RoomCreateRequest(int(h["num-players"]), h["dificuldade"])
    if first == "ROOM CREATE OK":
        return RoomCreateOk(h["room-id"])
    if first == "ROOM JOIN":
        return RoomJoinRequest(h["room-id"])
    if first == "ROOM JOIN OK":
        return RoomJoinOk(text_to_users(h["users"]), h["dificuldade"])
    if first == "ROOM UPDATE":
        return RoomUpdate(h["room-id"], text_to_users(h["users"]), h["dificuldade"], text_to_bool(h["ready"]))
    if first == "ROOM START":
        return RoomStartRequest()
    if first == "ROOM START OK":
        return RoomStartOk()
    if first == "ROOM STARTED":
        return RoomStarted(h["room-id"], text_to_users(h["users"]), h["word"])

    if first == "TURN":
        return Turn(h["room-id"], h["user-turn"])
    if first == "TURN RESPONSE OK":
        return TurnResponseOk()
    if first == "TURN RESPONSE":
        # o request e o broadcast tem a mesma 1a linha;
        # o broadcast e o que tem "user-turn"
        if "user-turn" in h:
            return TurnResponseBroadcast(
                h["room-id"], h["user-turn"], text_to_bool(h["guess"]),
                h["answer"], text_to_bool(h["accepted"]), h["word"],
            )
        return TurnResponseRequest(h["room-id"], text_to_bool(h["guess"]), h["answer"])

    if first == "GAME OVER":
        return GameOver(h["room-id"], h["winner"])
    if first == "ERROR":
        return ErrorMessage(h["error"])

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
    tamanho = struct.unpack("!I", receive_exact(sock, 4))[0]
    corpo = receive_exact(sock, tamanho)
    return decode(corpo)


def send_message(sock, msg: Message):
    """Envia uma mensagem (objeto Message) pelo socket."""
    if not isinstance(msg, Message):
        raise ValueError("msg deve ser uma instancia de Message")
    sock.sendall(msg.encode())


# ---------------------------------------------------------------
# Teste rapido: python forca_protocol.py
# ---------------------------------------------------------------
if __name__ == "__main__":
    exemplos = [
        ConnectRequest("PUBKEY", "ana"),
        ConnectOk("SERVERKEY"),
        ConnectError("versao nao suportada\r\n", "forca2.0"),
        RoomCreateRequest(3, "easy"),
        RoomCreateOk("abc123"),
        RoomJoinRequest("abc123"),
        RoomJoinOk(["ana", "bob"], "easy"),
        RoomUpdate("abc123", ["ana", "bob"], "easy", True),
        RoomStartRequest(),
        RoomStartOk(),
        RoomStarted("abc123", ["ana", "bob"], "_____"),
        Turn("abc123", "ana"),
        TurnResponseRequest("abc123", False, "a"),
        TurnResponseOk(),
        TurnResponseBroadcast("abc123", "ana", False, "a", True, "_a_a_"),
        GameOver("abc123", "ana"),
        ErrorMessage("sala inexistente"),
    ]
    for m in exemplos:
        bytes_msg = m.encode()
        tamanho = struct.unpack("!I", bytes_msg[:4])[0]
        assert tamanho == len(bytes_msg) - 4
        volta = decode(bytes_msg[4:])
        assert type(volta) is type(m)
        assert volta.encode() == bytes_msg
        print("OK", type(m).__name__)
    print("todos os testes passaram")