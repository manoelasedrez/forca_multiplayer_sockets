"""
Testes do servidor de verdade, com clientes conectados por socket.
O servidor usa uma porta livre e um banco de palavras pequeno e conhecido.
"""

import socket
import struct
import threading
import time
import unittest

from nacl.encoding import Base64Encoder
from nacl.public import PrivateKey

import caminho_entrega  # noqa: F401 (precisa vir antes do codigo do jogo)
from protocol import protocol
from servidor import server as srv

PALAVRAS_TESTE = [
    ("uva", "Frutas"), ("kiwi", "Frutas"), ("caju", "Frutas"),
    ("gato", "Animais"),
]
# Nenhuma palavra acima tem as letras x, y, z, q, b, d


class ServidorTeste(srv.Server):
    def print(self, msg):
        pass  # sem log durante os testes


class ClienteTeste:
    def __init__(self, porta):
        self.sock = socket.create_connection(("127.0.0.1", porta))
        self.sock.settimeout(3)

    def conectar(self, nome, versao=protocol.VERSION):
        chave = PrivateKey.generate().public_key.encode(encoder=Base64Encoder).decode()
        self.enviar(protocol.ConnectRequest(chave, nome, versao))
        return self.receber()

    def enviar(self, mensagem):
        protocol.send_message(self.sock, mensagem)

    def receber(self):
        return protocol.receive_message(self.sock)

    def esperar(self, tipo):
        # Le mensagens ate chegar uma do tipo pedido
        while True:
            mensagem = self.receber()
            if isinstance(mensagem, tipo):
                return mensagem

    def esperar_resposta_de_jogada(self):
        # TURN RESPONSE OK ou ERROR, o que vier primeiro
        while True:
            mensagem = self.receber()
            if isinstance(mensagem, protocol.TurnResponseOk) or isinstance(mensagem, protocol.ErrorMessage):
                return mensagem

    def esperar_erro(self):
        return self.esperar(protocol.ErrorMessage).code

    def fechar(self):
        self.sock.close()


class TestServidor(unittest.TestCase):
    def setUp(self):
        self.tempo_turno = srv.TEMPO_TURNO
        self.pausa = srv.PAUSA_ENTRE_RODADAS
        srv.TEMPO_TURNO = 5
        srv.PAUSA_ENTRE_RODADAS = 0.1

        self.servidor = ServidorTeste("127.0.0.1", 0)
        self.servidor.palavras = PALAVRAS_TESTE
        self.servidor.categorias = ["Frutas", "Animais"]
        self.servidor.iniciar()
        self.clientes = []

    def tearDown(self):
        for cliente in self.clientes:
            cliente.fechar()
        self.servidor.fechar()
        srv.TEMPO_TURNO = self.tempo_turno
        srv.PAUSA_ENTRE_RODADAS = self.pausa

    def novo_cliente(self, nome):
        cliente = ClienteTeste(self.servidor.port)
        self.clientes.append(cliente)
        resposta = cliente.conectar(nome)
        self.assertIsInstance(resposta, protocol.ConnectOk)
        return cliente

    def criar_sala(self, dono, max_jogadores=2, rodadas=1, categoria="Frutas"):
        dono.enviar(protocol.RoomCreateRequest(max_jogadores, "easy", "Sala Teste", rodadas, categoria))
        return dono.esperar(protocol.RoomCreateOk).room_id

    def sala_com_dois(self, rodadas=1):
        # ana (dono) e bob na mesma sala, partida ainda nao iniciada
        ana = self.novo_cliente("ana")
        bob = self.novo_cliente("bob")
        codigo = self.criar_sala(ana, rodadas=rodadas)
        bob.enviar(protocol.RoomJoinRequest(codigo))
        bob.esperar(protocol.RoomJoinOk)
        return ana, bob, codigo

    def iniciar(self, ana, bob, codigo):
        ana.enviar(protocol.RoomStartRequest(codigo))
        ana.esperar(protocol.RoomStartOk)
        for cliente in [ana, bob]:
            cliente.esperar(protocol.RoundStart)
            cliente.esperar(protocol.Turn)

    def palavra(self, codigo):
        return self.servidor.get_sala(codigo).palavra

    # -----------------------------------------------------------
    def test_conexao(self):
        self.novo_cliente("ana")
        for nome in ["ana", "a,b", "a=b", "x" * 16, " "]:
            cliente = ClienteTeste(self.servidor.port)
            self.clientes.append(cliente)
            self.assertIsInstance(cliente.conectar(nome), protocol.ConnectError, nome)

        cliente = ClienteTeste(self.servidor.port)
        self.clientes.append(cliente)
        self.assertIsInstance(cliente.conectar("bob", "forca2.0"), protocol.ConnectError)

    def test_mensagem_antes_do_connect(self):
        cliente = ClienteTeste(self.servidor.port)
        self.clientes.append(cliente)
        cliente.enviar(protocol.RoomJoinRequest("K7XP"))
        self.assertEqual(cliente.esperar_erro(), protocol.NAO_CONECTADO)

    def test_validacoes_criar_sala(self):
        ana = self.novo_cliente("ana")
        casos = [
            (protocol.RoomCreateRequest(2, "easy", " ", 1, "qualquer"), protocol.NOME_SALA_INVALIDO),
            (protocol.RoomCreateRequest(7, "easy", "Sala", 1, "qualquer"), protocol.NUM_JOGADORES_INVALIDO),
            (protocol.RoomCreateRequest(2, "facil", "Sala", 1, "qualquer"), protocol.DIFICULDADE_INVALIDA),
            (protocol.RoomCreateRequest(2, "easy", "Sala", 6, "qualquer"), protocol.RODADAS_INVALIDAS),
            (protocol.RoomCreateRequest(2, "easy", "Sala", 1, "Planetas"), protocol.CATEGORIA_INVALIDA),
            (protocol.RoomCreateRequest(2, "easy", "Sala", 2, "Animais"), protocol.PALAVRAS_INSUFICIENTES),
        ]
        for mensagem, codigo in casos:
            ana.enviar(mensagem)
            self.assertEqual(ana.esperar_erro(), codigo)
        self.assertEqual(len(self.servidor.salas), 0)

        self.criar_sala(ana)
        ana.enviar(protocol.RoomCreateRequest(2, "easy", "Outra", 1, "qualquer"))
        self.assertEqual(ana.esperar_erro(), protocol.JA_EM_SALA)

    def test_validacoes_entrar(self):
        ana = self.novo_cliente("ana")
        bob = self.novo_cliente("bob")
        caio = self.novo_cliente("caio")
        codigo = self.criar_sala(ana)

        bob.enviar(protocol.RoomJoinRequest("XYZ"))
        self.assertEqual(bob.esperar_erro(), protocol.CODIGO_INVALIDO)
        bob.enviar(protocol.RoomJoinRequest("ZZZZ"))
        self.assertEqual(bob.esperar_erro(), protocol.SALA_INEXISTENTE)
        ana.enviar(protocol.RoomJoinRequest(codigo))
        self.assertEqual(ana.esperar_erro(), protocol.JA_EM_SALA)

        bob.enviar(protocol.RoomJoinRequest(" " + codigo.lower()))
        self.assertEqual(bob.esperar(protocol.RoomJoinOk).users, ["ana", "bob"])
        caio.enviar(protocol.RoomJoinRequest(codigo))
        self.assertEqual(caio.esperar_erro(), protocol.SALA_CHEIA)

    def test_inicio(self):
        ana = self.novo_cliente("ana")
        bob = self.novo_cliente("bob")
        codigo = self.criar_sala(ana, max_jogadores=4)

        ana.enviar(protocol.RoomStartRequest(codigo))
        self.assertEqual(ana.esperar_erro(), protocol.JOGADORES_INSUFICIENTES)

        bob.enviar(protocol.RoomJoinRequest(codigo))
        update = bob.esperar(protocol.RoomUpdate)
        self.assertTrue(update.ready)  # 2 de 4 ja pode iniciar

        bob.enviar(protocol.RoomStartRequest(codigo))
        self.assertEqual(bob.esperar_erro(), protocol.APENAS_DONO)

        ana.enviar(protocol.RoomStartRequest(codigo))
        ana.esperar(protocol.RoomStartOk)
        inicio = bob.esperar(protocol.RoundStart)
        self.assertEqual(inicio.categoria, "Frutas")
        self.assertEqual(bob.esperar(protocol.Turn).user_turn, "ana")

        caio = self.novo_cliente("caio")
        caio.enviar(protocol.RoomJoinRequest(codigo))
        self.assertEqual(caio.esperar_erro(), protocol.PARTIDA_EM_ANDAMENTO)

    def test_jogadas_invalidas(self):
        ana, bob, codigo = self.sala_com_dois()

        ana.enviar(protocol.TurnResponseRequest(codigo, False, "a"))
        self.assertEqual(ana.esperar_erro(), protocol.SEM_RODADA_ATIVA)

        self.iniciar(ana, bob, codigo)
        bob.enviar(protocol.TurnResponseRequest(codigo, False, "a"))
        self.assertEqual(bob.esperar_erro(), protocol.NAO_E_SUA_VEZ)
        casos = [
            (False, " ", protocol.RESPOSTA_VAZIA),
            (False, "ab", protocol.LETRA_INVALIDA),
            (False, "1", protocol.LETRA_INVALIDA),
            (True, "uva!", protocol.PALPITE_INVALIDO),
        ]
        for guess, resposta, codigo_erro in casos:
            ana.enviar(protocol.TurnResponseRequest(codigo, guess, resposta))
            self.assertEqual(ana.esperar_erro(), codigo_erro)

        # Jogada valida de ana, depois letra repetida de bob
        letra = self.palavra(codigo)[0]
        ana.enviar(protocol.TurnResponseRequest(codigo, False, letra))
        ana.esperar(protocol.TurnResponseOk)
        self.assertEqual(bob.esperar(protocol.Turn).user_turn, "bob")
        bob.enviar(protocol.TurnResponseRequest(codigo, False, letra.upper()))
        self.assertEqual(bob.esperar_erro(), protocol.LETRA_REPETIDA)

    def test_partida_com_duas_rodadas(self):
        ana, bob, codigo = self.sala_com_dois(rodadas=2)
        self.iniciar(ana, bob, codigo)

        # Rodada 1: ana erra uma letra, bob acerta a palavra
        ana.enviar(protocol.TurnResponseRequest(codigo, False, "z"))
        ana.esperar(protocol.TurnResponseBroadcast)
        resultado = bob.esperar(protocol.TurnResponseBroadcast)
        self.assertFalse(resultado.accepted)
        self.assertEqual(resultado.erros, 1)
        self.assertEqual(resultado.letras, ["Z"])
        self.assertEqual(bob.esperar(protocol.Turn).user_turn, "bob")

        bob.enviar(protocol.TurnResponseRequest(codigo, True, self.palavra(codigo).upper()))
        resultado = ana.esperar(protocol.TurnResponseBroadcast)
        self.assertEqual(resultado.pontos, 5)
        fim = ana.esperar(protocol.RoundEnd)
        self.assertEqual(fim.motivo, protocol.MOTIVO_PALPITE)
        self.assertEqual(fim.placar, [("bob", 5), ("ana", 0)])

        # Rodada 2: comeca com bob; palavra diferente da primeira
        inicio = ana.esperar(protocol.RoundStart)
        self.assertEqual(inicio.round, 2)
        self.assertEqual(ana.esperar(protocol.Turn).user_turn, "bob")
        bob.enviar(protocol.TurnResponseRequest(codigo, True, "abacate"))
        self.assertEqual(ana.esperar(protocol.TurnResponseBroadcast).pontos, -2)
        ana.enviar(protocol.TurnResponseRequest(codigo, True, self.palavra(codigo)))

        fim = bob.esperar(protocol.GameOver)
        self.assertEqual(fim.motivo, protocol.MOTIVO_NORMAL)
        # ana: 0 + 5 = 5 / bob: 5 - 2 = 3
        self.assertEqual(fim.placar, [("ana", 5), ("bob", 3)])
        self.assertEqual(fim.winners, ["ana"])

    def test_limite_de_erros(self):
        ana, bob, codigo = self.sala_com_dois()
        self.iniciar(ana, bob, codigo)
        jogadores = [ana, bob]
        for i in range(6):
            jogadores[i % 2].enviar(protocol.TurnResponseRequest(codigo, False, "xyzqbd"[i]))
            jogadores[i % 2].esperar(protocol.TurnResponseOk)
        fim = ana.esperar(protocol.RoundEnd)
        self.assertEqual(fim.motivo, protocol.MOTIVO_LIMITE_ERROS)
        self.assertEqual(fim.word, self.palavra(codigo).upper())
        self.assertEqual(ana.esperar(protocol.GameOver).winners, ["ana", "bob"])  # 0 x 0

    def test_tempo_esgotado(self):
        srv.TEMPO_TURNO = 1
        ana, bob, codigo = self.sala_com_dois()
        self.iniciar(ana, bob, codigo)
        self.assertEqual(bob.esperar(protocol.TurnTimeout).user_turn, "ana")
        self.assertEqual(bob.esperar(protocol.Turn).user_turn, "bob")

    def test_saida_interrompe_partida(self):
        ana, bob, codigo = self.sala_com_dois(rodadas=2)
        self.iniciar(ana, bob, codigo)
        bob.enviar(protocol.RoomLeaveRequest(codigo))
        bob.esperar(protocol.RoomLeaveOk)

        self.assertEqual(ana.esperar(protocol.RoundEnd).motivo, protocol.MOTIVO_INTERROMPIDA)
        fim = ana.esperar(protocol.GameOver)
        self.assertEqual(fim.motivo, protocol.MOTIVO_INTERROMPIDA)
        self.assertEqual(fim.winners, [])
        self.assertEqual(fim.placar, [("ana", 0)])

        # Depois de sair, bob pode criar outra sala
        self.criar_sala(bob)

    def test_desconexao_passa_a_vez(self):
        ana = self.novo_cliente("ana")
        bob = self.novo_cliente("bob")
        caio = self.novo_cliente("caio")
        codigo = self.criar_sala(ana, max_jogadores=3)
        for cliente in [bob, caio]:
            cliente.enviar(protocol.RoomJoinRequest(codigo))
            cliente.esperar(protocol.RoomJoinOk)
        ana.enviar(protocol.RoomStartRequest(codigo))
        caio.esperar(protocol.Turn)

        ana.fechar()  # era a vez de ana
        self.clientes.remove(ana)
        self.assertEqual(caio.esperar(protocol.Turn).user_turn, "bob")
        sala = self.servidor.get_sala(codigo)
        self.assertEqual(sala.dono_addr, sala.jogadores[0])
        self.assertEqual(len(sala.jogadores), 2)


    # -----------------------------------------------------------
    # Mensagens invalidas
    # -----------------------------------------------------------
    def test_chave_publica_invalida(self):
        cliente = ClienteTeste(self.servidor.port)
        self.clientes.append(cliente)
        cliente.enviar(protocol.ConnectRequest("isso nao e uma chave", "ana"))
        self.assertIsInstance(cliente.receber(), protocol.ConnectError)
        # A conexao continua: da para tentar de novo
        self.assertIsInstance(cliente.conectar("ana"), protocol.ConnectOk)

    def test_connect_repetido(self):
        ana = self.novo_cliente("ana")
        resposta = ana.conectar("ana2")
        self.assertIsInstance(resposta, protocol.ErrorMessage)
        self.assertEqual(resposta.code, protocol.JA_CONECTADO)

    def test_mensagem_que_so_o_servidor_envia(self):
        ana = self.novo_cliente("ana")
        ana.enviar(protocol.RoomCreateOk("K7XP"))
        self.assertEqual(ana.esperar_erro(), protocol.MENSAGEM_INVALIDA)
        self.criar_sala(ana)  # a conexao continua funcionando

    def test_corpo_malformado_nao_derruba_a_conexao(self):
        ana = self.novo_cliente("ana")
        for corpo in [b"PULAR VEZ\r\n", b"ROOM JOIN\r\n", b"\xff\xfe", b""]:
            ana.sock.sendall(struct.pack("!I", len(corpo)) + corpo)
            self.assertEqual(ana.esperar_erro(), protocol.MENSAGEM_INVALIDA)
        self.criar_sala(ana)

    def test_tamanho_acima_do_limite_encerra(self):
        ana = self.novo_cliente("ana")
        codigo = self.criar_sala(ana)
        ana.sock.sendall(struct.pack("!I", 2 ** 31) + b"abc")
        self.assertEqual(ana.esperar_erro(), protocol.MENSAGEM_INVALIDA)
        with self.assertRaises(ConnectionError):
            ana.receber()  # o servidor fechou a conexao
        time.sleep(0.2)
        self.assertIsNone(self.servidor.get_sala(codigo))  # e tratou como desconexao

    # -----------------------------------------------------------
    # Operacoes simultaneas
    # -----------------------------------------------------------
    def test_jogadas_simultaneas(self):
        # ana (da vez) e bob jogam ao mesmo tempo. O servidor trata uma de cada vez:
        # a jogada de bob so vale se chegar depois da de ana (quando ja e a vez dele).
        ana, bob, codigo = self.sala_com_dois()
        self.iniciar(ana, bob, codigo)
        t1 = threading.Thread(target=ana.enviar, args=(protocol.TurnResponseRequest(codigo, False, "x"),))
        t2 = threading.Thread(target=bob.enviar, args=(protocol.TurnResponseRequest(codigo, False, "y"),))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        primeira = ana.esperar(protocol.TurnResponseBroadcast)
        self.assertEqual(primeira.user_turn, "ana")
        self.assertEqual(primeira.letras, ["X"])

        resposta_bob = bob.esperar_resposta_de_jogada()
        if isinstance(resposta_bob, protocol.ErrorMessage):
            self.assertEqual(resposta_bob.code, protocol.NAO_E_SUA_VEZ)  # chegou antes da de ana
        else:
            segunda = ana.esperar(protocol.TurnResponseBroadcast)  # chegou depois: jogada valida
            self.assertEqual(segunda.user_turn, "bob")
            self.assertEqual(segunda.letras, ["X", "Y"])

    def test_varias_salas_ao_mesmo_tempo(self):
        # 5 salas com 2 jogadores cada, jogando em paralelo, cada uma em sua thread
        resultados = []

        def jogar_partida(numero):
            dono = self.novo_cliente(f"dono{numero}")
            outro = self.novo_cliente(f"outro{numero}")
            codigo = self.criar_sala(dono)
            outro.enviar(protocol.RoomJoinRequest(codigo))
            outro.esperar(protocol.RoomJoinOk)
            self.iniciar(dono, outro, codigo)
            dono.enviar(protocol.TurnResponseRequest(codigo, True, self.palavra(codigo)))
            resultados.append(outro.esperar(protocol.GameOver).winners)

        threads = []
        for i in range(5):
            t = threading.Thread(target=jogar_partida, args=(i,))
            threads.append(t)
            t.start()
        for t in threads:
            t.join(10)

        self.assertEqual(len(resultados), 5)
        for vencedores in resultados:
            self.assertEqual(len(vencedores), 1)
            self.assertTrue(vencedores[0].startswith("dono"))
        self.assertEqual(len(self.servidor.salas), 5)


if __name__ == "__main__":
    unittest.main()
