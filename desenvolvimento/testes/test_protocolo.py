import struct
import unittest

import caminho_entrega  # noqa: F401 (precisa vir antes do codigo do jogo)
from protocol import protocol


class TestProtocolo(unittest.TestCase):
    def exemplos(self):
        return [
            protocol.ConnectRequest("PUBKEY", "ana"),
            protocol.ConnectOk("SERVERKEY", ["Frutas", "Objetos da casa"]),
            protocol.ConnectError("versao nao suportada\r\n", "forca2.0"),
            protocol.RoomCreateRequest(3, "easy", "Sala da Ana", 2, "qualquer"),
            protocol.RoomCreateOk("K7XP"),
            protocol.RoomJoinRequest("K7XP"),
            protocol.RoomJoinOk(["ana", "bob"], "easy", "Sala da Ana", 2, "Frutas"),
            protocol.RoomLeaveRequest("K7XP"),
            protocol.RoomLeaveOk(),
            protocol.RoomUpdate("K7XP", ["ana", "bob"], "easy", True),
            protocol.RoomStartRequest("K7XP"),
            protocol.RoomStartOk(),
            protocol.RoomStarted("K7XP", ["ana", "bob"], 3),
            protocol.RoundStart("K7XP", 1, 3, "Frutas", "_____"),
            protocol.RoundEnd("K7XP", 1, "BANANA", protocol.MOTIVO_PALPITE, [("ana", 8), ("bob", -2)]),
            protocol.Turn("K7XP", "ana", 30),
            protocol.TurnTimeout("K7XP", "ana"),
            protocol.TurnResponseRequest("K7XP", False, "a"),
            protocol.TurnResponseOk(),
            protocol.TurnResponseBroadcast("K7XP", "ana", False, "a", True, "_A_A_", 2, 1, ["A", "E"]),
            protocol.GameOver("K7XP", ["ana", "bob"], [("ana", 8), ("bob", 8)], protocol.MOTIVO_NORMAL),
            protocol.GameOver("K7XP", [], [("ana", 3)], protocol.MOTIVO_INTERROMPIDA),
            protocol.ErrorMessage(protocol.SALA_INEXISTENTE, "sala inexistente"),
        ]

    def test_ida_e_volta(self):
        # Codificar e decodificar devolve a mesma mensagem
        for m in self.exemplos():
            bytes_msg = m.encode()
            tamanho = struct.unpack("!I", bytes_msg[:4])[0]
            self.assertEqual(tamanho, len(bytes_msg) - 4)
            volta = protocol.decode(bytes_msg[4:])
            self.assertIs(type(volta), type(m))
            self.assertEqual(volta.encode(), bytes_msg)

    def test_placar(self):
        texto = protocol.placar_to_text([("ana", 8), ("bob", -2)])
        self.assertEqual(texto, "ana=8, bob=-2")
        self.assertEqual(protocol.text_to_placar(texto), [("ana", 8), ("bob", -2)])

    def test_listas_vazias(self):
        m = protocol.decode(protocol.GameOver("K7XP", [], [], protocol.MOTIVO_INTERROMPIDA).encode()[4:])
        self.assertEqual(m.winners, [])
        self.assertEqual(m.placar, [])

    def test_turn_response_request_e_broadcast(self):
        # Mesma 1a linha: o broadcast e o que tem user-turn
        pedido = protocol.decode(protocol.TurnResponseRequest("K7XP", True, "maca").encode()[4:])
        self.assertIsInstance(pedido, protocol.TurnResponseRequest)
        self.assertTrue(pedido.guess)

    def test_mensagens_malformadas(self):
        corpos = [
            "PULAR VEZ\r\n".encode("utf-8"),  # comando desconhecido
            "ROOM JOIN\r\n".encode("utf-8"),  # header faltando
            "ROOM JOIN\r\nsem dois pontos\r\n".encode("utf-8"),
            "ROOM CREATE\r\nnum-players: dois\r\n".encode("utf-8"),  # numero invalido
            b"\xff\xfe",  # nao e UTF-8
            b"",  # vazio
        ]
        for corpo in corpos:
            with self.assertRaises(protocol.ErroProtocolo):
                protocol.decode(corpo)


class SocketFalso:
    # Imita um socket: devolve os bytes recebidos no construtor
    def __init__(self, dados):
        self.dados = dados

    def recv(self, quantidade):
        pedaco = self.dados[:quantidade]
        self.dados = self.dados[quantidade:]
        return pedaco


class TestRecebimento(unittest.TestCase):
    def test_mensagem_em_pedacos(self):
        dados = protocol.RoomJoinRequest("K7XP").encode()
        sock = SocketFalso(dados)
        self.assertEqual(protocol.receive_message(sock).room_id, "K7XP")

    def test_tamanho_acima_do_limite(self):
        sock = SocketFalso(struct.pack("!I", protocol.MAX_TAMANHO_MENSAGEM + 1) + b"abc")
        with self.assertRaises(protocol.ErroTamanho):
            protocol.receive_message(sock)

    def test_conexao_fechada_no_meio(self):
        sock = SocketFalso(struct.pack("!I", 50) + b"ROOM")
        with self.assertRaises(ConnectionError):
            protocol.receive_message(sock)


if __name__ == "__main__":
    unittest.main()
