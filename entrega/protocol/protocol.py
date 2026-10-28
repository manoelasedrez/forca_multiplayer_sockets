"""
Mensagens do protocolo forca1.1.

Resumao do que e isso: o TCP so leva bytes de um lado pro outro, ele ñ sabe o que eles
significam. Entao a gente precisou combinar uma "lingua" pra conversa: quais mensagens
existem, como cada uma e escrita e quem manda o que e quando. Isso e o PROTOCOLO DE
APLICACAO. Este arquivo e a implementacao dele, e e usado pelos DOIS lados (cliente e
servidor), igualzinho, pra os dois sempre falarem a mesma lingua.

O documento que explica tudo pra alguem implementar sem ler codigo e o protocolo.md (o
enunciado pede isso na secao 5). Aqui e a "implementacao de referencia".

No fio, cada mensagem e:  <size: 4 bytes (struct "!I")> + <corpo>
O size e o tamanho do corpo (nao conta os 4 bytes do size).
O corpo e texto UTF-8: 1a linha = comando, demais = "chave: valor", cada linha termina com \r\n.

Por que o size na frente? Lembra que o TCP entrega um FLUXO de bytes, sem marcar onde uma
mensagem acaba e a outra comeca? Se vc manda duas mensagens seguidas, elas podem chegar
coladas, ou uma cortada no meio. Com o tamanho na frente, quem recebe sabe exatamente
quantos bytes ler pra pegar UMA mensagem inteira (ver receive_exact e receive_message).

O formato do corpo (comando na 1a linha + "chave: valor") e inspirado no HTTP, que a
gente estudou pra ter uma referencia (README, "Uso de Inteligencia Artificial").

Cifragem: CONNECT, CONNECT OK e CONNECT ERROR vao em texto puro (e nelas que as chaves
publicas sao trocadas). Depois do CONNECT OK, o corpo de todas as mensagens vai cifrado
com um nacl.public.Box (chave privada propria + chave publica do outro lado).

Enviar:   send_message(sock, RoomJoinRequest("abc"), box)
Receber:  msg = receive_message(sock, box)
(box = None enquanto a conexao ainda nao foi aceita)

Ordem do arquivo: constantes e erros -> funcoes de conversao texto<->valor -> as classes das
mensagens -> decodificar (texto -> objeto) -> ler/enviar pelo socket.
"""

import struct

from nacl.exceptions import CryptoError

CRLF = "\r\n"  # fim de linha do protocolo (os dois caracteres juntos, como no HTTP)
# A versao vai na 1a linha do CONNECT, e o servidor recusa qualquer outra.
# CUIDADO (parece incoerente com o protocolo.md 7.5): um CONNECT SEM public-key, como o da
# antiga forca1.0 (que ñ tinha cifragem), nem chega a ser comparado com esta versao. O
# decode() ja recusa por "atributo obrigatorio ausente", e a resposta vira um ERROR
# MENSAGEM_INVALIDA, ñ o CONNECT ERROR "versao nao suportada" que o documento promete.
VERSION = "forca1.1"

# Maior corpo aceito, em bytes. As mensagens do jogo tem poucas centenas de bytes;
# o limite evita que alguem anuncie um tamanho enorme e prenda o servidor lendo.
MAX_TAMANHO_MENSAGEM = 16384


class ErroProtocolo(Exception):
    """Corpo malformado (comando desconhecido, header faltando, valor invalido).
    O corpo ja foi lido inteiro, entao a conexao pode continuar.

    Tambem e o erro de uma mensagem que ñ pode ser decifrada (ver decifrar). A diferenca
    pro ErroTamanho: aqui a gente SABE onde a proxima mensagem comeca, entao ñ precisa
    derrubar ninguem; so avisa e segue a vida."""


class ErroTamanho(Exception):
    """Tamanho anunciado acima do limite. Nao da para saber onde comeca a
    proxima mensagem, entao a conexao precisa ser encerrada.

    Pensa assim: pra pular a mensagem gigante a gente teria que ler todos aqueles bytes
    (justo o que o limite quer evitar). Sem ler, o fluxo do TCP fica "perdido", e a unica
    saida segura e fechar a conexao."""

# Motivos de fim de rodada (ROUND END)
MOTIVO_PALPITE = "PALPITE"
MOTIVO_PALAVRA_COMPLETA = "PALAVRA_COMPLETA"
MOTIVO_LIMITE_ERROS = "LIMITE_ERROS"
MOTIVO_INTERROMPIDA = "INTERROMPIDA"

# Motivos de fim de partida (GAME OVER)
MOTIVO_NORMAL = "NORMAL"
# MOTIVO_INTERROMPIDA tambem vale para GAME OVER

# Codigos de erro (ERROR). O cliente decide o que fazer pelo CODIGO (que e fixo); o texto
# do erro e so pra mostrar ao jogador e pode mudar. Tabela completa: protocolo.md, secao 6.
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
# Na rede TUDO viaja como texto (o corpo e texto UTF-8). Entao numero, booleano, lista e
# placar precisam ser convertidos pra texto na hora de enviar e de volta na hora de ler.
# E pra isso que servem as funcoes abaixo. Formatos: protocolo.md, secao 2.3.
def bool_to_text(valor):
    if valor:
        return "true"
    return "false"


def text_to_bool(texto):
    """
    CUIDADO, pegadinha: so o texto EXATO "true" vira True. Qualquer outra coisa ("True",
    "TRUE", "1", lixo) vira False, sem dar erro. Ou seja, um booleano mal escrito ñ e
    detectado como mensagem malformada.
    """
    return texto == "true"


def list_to_text(lista):
    return ", ".join(lista)


def text_to_list(texto):
    """
    Desfaz o list_to_text: "ana, bob" -> ["ana", "bob"]. Ignora espacos e itens vazios,
    entao lista vazia ("") vira [].

    CUIDADO: a virgula e o separador, por isso nome de jogador ñ pode ter ',' (o servidor
    barra isso no CONNECT). Um item com virgula viraria dois.
    """
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
    """
    Desfaz o placar_to_text: "ana=8, bob=-2" -> [("ana", 8), ("bob", -2)].

    O split("=", 1) corta so no PRIMEIRO '=', e e por isso que nome de jogador ñ pode ter
    '=' tambem. Se os pontos ñ forem um numero, o int() levanta ValueError e o decode()
    transforma isso em ErroProtocolo.
    """
    placar = []
    for item in text_to_list(texto):
        nome, pontos = item.split("=", 1)
        placar.append((nome.strip(), int(pontos)))
    return placar


# ---------------------------------------------------------------
# Classe base
# ---------------------------------------------------------------
class Message:
    """
    Molde de TODA mensagem. Cada tipo de mensagem (as classes abaixo) so precisa dizer duas
    coisas: qual a 1a linha (first_line) e quais atributos leva (headers). O resto, que e
    montar o texto, ja vem pronto daqui.
    """

    def first_line(self):
        return ""

    def headers(self):
        # lista de (chave, valor). Lista (e ñ dicionario) pra manter a ORDEM de escrita.
        return []

    def to_text(self):
        """Monta o corpo em texto: 1a linha + uma linha 'chave: valor' por atributo, todas terminadas em \\r\\n."""
        texto = self.first_line() + CRLF
        for chave, valor in self.headers():
            texto += chave + ": " + str(valor) + CRLF
        return texto

    def encode(self):
        """
        Corpo SEM cifra, ja com o tamanho na frente. So os testes usam este metodo.
        CUIDADO: o envio de verdade passa pelo encode_message(), que cifra. Mexeu aqui?
        Mexe la tb, senao os dois jeitos de montar a mensagem ficam diferentes.
        """
        corpo = self.to_text().encode("utf-8")
        tamanho = struct.pack("!I", len(corpo))
        return tamanho + corpo


# ---------------------------------------------------------------
# Conexao
# ---------------------------------------------------------------
class ConnectRequest(Message):
    """
    CONNECT (cliente -> servidor, em TEXTO PURO). A primeira mensagem de todas: o jogador
    diz o nome e entrega a chave publica dele. Ver protocolo.md 3.1.
    """

    def __init__(self, public_key, username, version=VERSION):
        self.public_key = public_key
        self.username = username
        self.version = version

    def first_line(self):
        return "CONNECT " + self.version

    def headers(self):
        return [("public-key", self.public_key), ("username", self.username)]


class ConnectOk(Message):
    """
    CONNECT OK (servidor -> cliente, em TEXTO PURO). Aceitou! Devolve a chave publica do
    servidor e as categorias de palavras. Vai sem cifra pq o cliente ainda ñ tem a chave do
    servidor pra decifrar. Depois dela, tudo vai cifrado. Ver protocolo.md 3.1.
    """

    def __init__(self, public_key, categorias, version=VERSION):
        self.public_key = public_key
        self.categorias = categorias  # lista de categorias do banco de palavras
        self.version = version

    def first_line(self):
        return "CONNECT OK " + self.version

    def headers(self):
        return [("public-key", self.public_key), ("categorias", list_to_text(self.categorias))]


class ConnectError(Message):
    """
    CONNECT ERROR (servidor -> cliente, em TEXTO PURO). Recusou o CONNECT. E a unica
    mensagem SEM atributos: depois da 1a linha vem so um texto livre com o motivo.
    A conexao continua aberta e o cliente pode tentar de novo. Ver protocolo.md 3.1.
    """

    def __init__(self, data="", version=VERSION):
        self.data = data
        self.version = version

    def first_line(self):
        return "CONNECT ERROR " + self.version

    def to_text(self):
        # depois da 1a linha vai o <DATA> do jeito que veio
        # (quem cria ja manda o texto terminado em \r\n; o servidor faz isso)
        return self.first_line() + CRLF + self.data


# ---------------------------------------------------------------
# Salas
# ---------------------------------------------------------------
class RoomCreateRequest(Message):
    """ROOM CREATE (cliente -> servidor). Pede pra criar uma sala; quem cria vira o dono. Protocolo.md 3.2."""

    def __init__(self, numero_jogadores, dificuldade, room_name, rounds, categoria):
        # Obs: no fio o atributo se chama "num-players", mas aqui dentro e numero_jogadores
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
    """ROOM CREATE OK (servidor -> cliente). Sala criada; devolve so o CODIGO dela, que o dono passa pros amigos."""

    def __init__(self, room_id):
        self.room_id = room_id

    def first_line(self):
        return "ROOM CREATE OK"

    def headers(self):
        return [("room-id", self.room_id)]


class RoomJoinRequest(Message):
    """ROOM JOIN (cliente -> servidor). Pede pra entrar numa sala pelo codigo. Protocolo.md 3.3."""

    def __init__(self, room_id):
        self.room_id = room_id

    def first_line(self):
        return "ROOM JOIN"

    def headers(self):
        return [("room-id", self.room_id)]


class RoomJoinOk(Message):
    """
    ROOM JOIN OK (servidor -> cliente). Entrou! Traz os dados da sala. Repara que ele NAO
    traz o codigo da sala: o cliente lembra o que ele mesmo pediu (ver Client.sala_pedida).
    """

    def __init__(self, users, dificuldade, room_name, rounds, categoria):
        self.users = users  # lista de nomes
        self.dificuldade = dificuldade
        self.room_name = room_name
        self.rounds = rounds
        self.categoria = categoria

    def first_line(self):
        return "ROOM JOIN OK"

    def headers(self):
        # "USERS" em maiusculas, mas as chaves nao diferenciam maiuscula de minuscula
        # (o read_headers passa tudo pra minusculo), entao tanto faz.
        return [
            ("USERS", users_to_text(self.users)),
            ("dificuldade", self.dificuldade),
            ("room-name", self.room_name),
            ("rounds", self.rounds),
            ("categoria", self.categoria),
        ]


class RoomLeaveRequest(Message):
    """ROOM LEAVE (cliente -> servidor). Pede pra sair da sala. Protocolo.md 3.5."""

    def __init__(self, room_id):
        self.room_id = room_id

    def first_line(self):
        return "ROOM LEAVE"

    def headers(self):
        return [("room-id", self.room_id)]


class RoomLeaveOk(Message):
    """ROOM LEAVE OK (servidor -> cliente). Saida confirmada. Sem atributos: so a 1a linha."""

    def first_line(self):
        return "ROOM LEAVE OK"


class RoomUpdate(Message):
    """
    ROOM UPDATE (servidor -> TODA a sala). Um aviso que o servidor manda por conta propria
    (ninguem pediu) sempre que a lista de jogadores muda ou uma partida termina. E assim que
    todo mundo fica com a mesma "foto" da sala. O primeiro de USERS e o dono. Protocolo.md 3.4.
    """

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
    """ROOM START (cliente -> servidor). O DONO pede pra iniciar a partida. Protocolo.md 3.6."""

    def __init__(self, room_id):
        self.room_id = room_id

    def first_line(self):
        return "ROOM START"

    def headers(self):
        return [("room-id", self.room_id)]


class RoomStartOk(Message):
    """ROOM START OK (servidor -> so o dono). Pedido aceito; vem antes do ROOM STARTED. Sem atributos."""

    def first_line(self):
        return "ROOM START OK"


class RoomStarted(Message):
    """ROOM STARTED (servidor -> TODA a sala). A partida comecou. Logo em seguida vem o ROUND START da rodada 1."""

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
    """
    ROUND START (servidor -> TODA a sala). Comecou uma rodada. O campo 'word' e a palavra
    ESCONDIDA ("_____"), nunca a palavra de verdade: ela so aparece no ROUND END. Por isso
    nem um cliente alterado consegue espiar a resposta. Protocolo.md 3.7.
    """

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
    """ROUND END (servidor -> TODA a sala). A rodada acabou: revela a palavra, diz o motivo e manda o placar. Protocolo.md 3.10."""

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
    """TURN (servidor -> TODA a sala). Comecou um turno: so o jogador 'user-turn' pode jogar, e tem 'tempo' segundos. Protocolo.md 3.8."""

    def __init__(self, room_id, user_turn, tempo):
        self.room_id = room_id
        self.user_turn = user_turn
        self.tempo = tempo  # segundos do turno

    def first_line(self):
        return "TURN"

    def headers(self):
        return [("room-id", self.room_id), ("user-turn", self.user_turn), ("tempo", self.tempo)]


class TurnTimeout(Message):
    """TURN TIMEOUT (servidor -> TODA a sala). O tempo do jogador da vez acabou; ele ñ perde pontos. O proximo TURN vem em seguida."""

    def __init__(self, room_id, user_turn):
        self.room_id = room_id
        self.user_turn = user_turn  # quem perdeu a vez

    def first_line(self):
        return "TURN TIMEOUT"

    def headers(self):
        return [("room-id", self.room_id), ("user-turn", self.user_turn)]


class TurnResponseRequest(Message):
    """
    TURN RESPONSE, versao PEDIDO (cliente -> servidor): a jogada. Protocolo.md 3.9.

    CUIDADO: esta mensagem e a TurnResponseBroadcast (mais abaixo) tem a MESMA 1a linha.
    Quem diferencia as duas ao ler e a presenca do atributo 'user-turn' (ver decode_corpo).
    """

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
    """TURN RESPONSE OK (servidor -> so quem jogou). Jogada aceita. Chega antes do resultado, que vai pra sala toda."""

    def first_line(self):
        return "TURN RESPONSE OK"


class TurnResponseBroadcast(Message):
    """
    TURN RESPONSE, versao RESULTADO (servidor -> TODA a sala): o que aconteceu na jogada.
    Broadcast = mandar a mesma coisa pra todo mundo. Tem os mesmos atributos do pedido mais
    'user-turn' (quem jogou), o resultado e o estado novo da rodada. Protocolo.md 3.9.
    """

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
    """GAME OVER (servidor -> TODA a sala). A partida acabou: vencedores (lista vazia = ninguem venceu), placar final e motivo."""

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
    """
    ERROR (servidor -> cliente). Qualquer pedido recusado (menos o CONNECT, que tem o proprio
    CONNECT ERROR) ou mensagem invalida recebe isso. Nada muda no servidor. Protocolo.md 3.11.
    """

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
    """
    Transforma 'chave: valor\\r\\n...' em um dicionario.

    As chaves viram minusculas (assim 'USERS' e 'users' sao a mesma, protocolo.md 2.2).
    O split(":", 1) corta so no PRIMEIRO ':', por isso o valor pode ter ':' dentro.
    """
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
    """
    Corpo (bytes) -> objeto Message. Lanca ErroProtocolo se estiver malformado.

    Aqui so TRADUZ os erros: o decode_corpo levanta KeyError (atributo faltando),
    ValueError (numero invalido, comando desconhecido, etc.) ou IndexError, e este
    metodo troca tudo por um unico tipo, o ErroProtocolo. Assim quem chama so precisa
    tratar UM erro (e o servidor responde ERROR MENSAGEM_INVALIDA).
    """
    try:
        return decode_corpo(corpo)
    except KeyError as e:
        raise ErroProtocolo("atributo obrigatorio ausente: " + str(e).strip("'"))
    except (ValueError, IndexError, UnicodeDecodeError) as e:
        raise ErroProtocolo(str(e))


def decode_corpo(corpo):
    """
    Descobre qual mensagem e pela 1a linha e monta o objeto certo com os atributos.

    Cada 'h["chave"]' que falta levanta KeyError; cada int() ruim levanta ValueError.
    """
    texto = corpo.decode("utf-8")
    first, rest = texto.split(CRLF, 1)

    # CONNECT: a versao vem na primeira linha
    if first.startswith("CONNECT ERROR "):
        # O ERROR tem texto livre (sem 'chave: valor'), entao NAO passa pelo read_headers
        return ConnectError(rest, first.split(" ")[2])

    h = read_headers(rest)

    # CUIDADO com a ORDEM: "CONNECT OK ..." tambem comeca com "CONNECT ", entao o OK
    # tem que ser testado ANTES. Se invertesse, todo CONNECT OK viraria um pedido de CONNECT.
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
    """
    Le exatamente 'quantidade' bytes (um recv pode devolver menos).

    Fiquei gag qd descobri: o recv(N) NAO garante N bytes, ele devolve o que tiver chegado
    ate ali (pode ser 1 byte so). Entao a gente repete ate completar. Sem isso, uma mensagem
    cortada no meio pela rede quebraria tudo, e isso so aconteceria de vez em quando, o
    pior tipo de bug.

    Quando o recv devolve b"" (zero bytes), nao e "nao chegou nada": significa que o outro
    lado FECHOU a conexao. Aqui isso vira ConnectionError, e e assim que o servidor e o
    cliente percebem uma desconexao (enunciado: "tratar desconexoes e falhas de comunicacao").
    """
    dados = b""
    while len(dados) < quantidade:
        pedaco = sock.recv(quantidade - len(dados))
        if pedaco == b"":
            raise ConnectionError("conexao fechada")
        dados += pedaco
    return dados


def receive_message(sock, box=None):
    """
    Le uma mensagem inteira do socket. Com box, decifra o corpo antes de interpretar.
    Lanca ErroTamanho (encerrar a conexao) ou ErroProtocolo (pode continuar).

    Passo a passo:
      1) le 4 bytes = o tamanho. O "!I" do struct quer dizer "numero inteiro sem sinal de 4
         bytes, na ordem da REDE (big-endian)": o byte mais significativo vai primeiro, e e o
         padrao de rede, assim PCs de tipos diferentes concordam sobre o numero;
      2) se o tamanho passa do limite, recusa SEM ler o corpo (prender o servidor lendo
         lixo gigante e justamente o que o limite evita);
      3) le exatamente 'tamanho' bytes;
      4) decifra (se tiver box) e interpreta o texto.
    """
    tamanho = struct.unpack("!I", receive_exact(sock, 4))[0]
    if tamanho > MAX_TAMANHO_MENSAGEM:
        raise ErroTamanho(f"mensagem de {tamanho} bytes (limite {MAX_TAMANHO_MENSAGEM})")
    corpo = receive_exact(sock, tamanho)
    if box is not None:
        corpo = decifrar(corpo, box)
    return decode(corpo)


def cifrar(corpo, box):
    """
    Corpo em claro -> nonce (24 bytes) + corpo cifrado + autenticacao (16 bytes).

    O nonce e um numero aleatorio sorteado a CADA mensagem e mandado junto. Por isso a mesma
    mensagem enviada duas vezes gera bytes diferentes. A autenticacao (Poly1305) e o que
    permite detectar se alguem mexeu na mensagem no caminho. Total: +40 bytes por mensagem.
    Detalhes: protocolo.md, secao 7.
    """
    return bytes(box.encrypt(corpo))


def decifrar(corpo, box):
    """
    Desfaz o cifrar(). Corpo alterado, cifrado com outra chave ou em claro -> ErroProtocolo.

    Os tres casos dao no mesmo erro de proposito: pro servidor tanto faz por que falhou, a
    mensagem e descartada e a conexao continua (protocolo.md 5.3).
    """
    try:
        return box.decrypt(corpo)
    except (CryptoError, ValueError):
        raise ErroProtocolo("mensagem nao pode ser decifrada")


def encode_message(msg, box=None):
    """
    Mensagem -> bytes prontos para o socket (tamanho + corpo, cifrado se houver box).

    CUIDADO: o tamanho e calculado DEPOIS de cifrar, pq o que vai pro fio (e o que o outro
    lado vai ler) e o corpo ja cifrado, com os 40 bytes a mais. O tamanho em si ñ e cifrado,
    senao quem recebe ñ saberia quantos bytes ler.
    """
    corpo = msg.to_text().encode("utf-8")
    if box is not None:
        corpo = cifrar(corpo, box)
    return struct.pack("!I", len(corpo)) + corpo


def send_message(sock, msg: Message, box=None):
    """
    Envia uma mensagem (objeto Message) pelo socket. Com box, o corpo vai cifrado.

    Usa sendall() e ñ send(): o send() pode mandar so uma parte dos bytes e te avisar
    quanto foi (o mesmo problema do recv, so que no envio). O sendall() repete sozinho ate
    mandar tudo, ou da erro.
    """
    if not isinstance(msg, Message):
        raise ValueError("msg deve ser uma instancia de Message")
    sock.sendall(encode_message(msg, box))
