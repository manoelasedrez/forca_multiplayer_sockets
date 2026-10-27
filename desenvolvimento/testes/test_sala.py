import unittest

import caminho_entrega  # noqa: F401 (precisa vir antes do codigo do jogo)
from servidor.server import Sala


def nova_sala(jogadores, rodadas=3):
    # Sala com os jogadores na ordem dada; o primeiro e o dono
    sala = Sala("K7XP", "Teste", jogadores[0], "easy", 6, rodadas, "qualquer")
    for jogador in jogadores[1:]:
        sala.adicionar_jogador(jogador)
    return sala


class TestPontuacao(unittest.TestCase):
    def setUp(self):
        self.sala = nova_sala(["ana", "bob"])
        self.sala.iniciar_partida()
        self.sala.iniciar_rodada("banana", "Frutas")

    def test_letra_certa_vale_ocorrencias(self):
        self.assertEqual(self.sala.tentar_letra("ana", "a"), 3)
        self.assertEqual(self.sala.placar["ana"], 3)
        self.assertEqual(self.sala.erros, 0)

    def test_letra_errada(self):
        self.assertEqual(self.sala.tentar_letra("ana", "z"), 0)
        self.assertEqual(self.sala.placar["ana"], 0)
        self.assertEqual(self.sala.erros, 1)

    def test_palpite_certo(self):
        self.sala.tentar_letra("ana", "a")
        self.assertEqual(self.sala.tentar_palpite("bob", " BANANA "), 5)
        self.assertEqual(self.sala.placar["bob"], 5)
        self.assertTrue(self.sala.palavra_completa())

    def test_palpite_errado_de_qualquer_tamanho(self):
        self.assertEqual(self.sala.tentar_palpite("ana", "ba"), -2)
        self.assertEqual(self.sala.tentar_palpite("ana", "bananadamadura"), -2)
        self.assertEqual(self.sala.placar["ana"], -4)
        self.assertEqual(self.sala.erros, 2)

    def test_palpite_ignora_acentos(self):
        self.sala.iniciar_rodada("maçã", "Frutas")
        self.assertEqual(self.sala.tentar_palpite("ana", "maca"), 5)

    def test_palpite_exige_hifen(self):
        self.sala.iniciar_rodada("guarda-chuva", "Objetos")
        self.assertEqual(self.sala.tentar_palpite("ana", "guarda chuva"), -2)
        self.assertEqual(self.sala.tentar_palpite("ana", "guarda-chuva"), 5)

    def test_ultima_letra_completa_a_palavra(self):
        self.sala.tentar_letra("ana", "a")
        self.sala.tentar_letra("bob", "n")
        self.assertFalse(self.sala.palavra_completa())
        self.assertEqual(self.sala.tentar_letra("ana", "b"), 1)
        self.assertTrue(self.sala.palavra_completa())


class TestPlacar(unittest.TestCase):
    def test_ordem_e_empate(self):
        sala = nova_sala(["ana", "bob", "caio"])
        sala.iniciar_partida()
        sala.placar = {"ana": 8, "bob": 12, "caio": 12}
        self.assertEqual(sala.placar_ordenado(), [("bob", 12), ("caio", 12), ("ana", 8)])
        self.assertEqual(sala.vencedores(), ["bob", "caio"])

    def test_quem_sai_perde_os_pontos(self):
        sala = nova_sala(["ana", "bob", "caio"])
        sala.iniciar_partida()
        sala.placar = {"ana": 8, "bob": 12, "caio": 3}
        sala.remover_jogador("bob")
        self.assertEqual(sala.vencedores(), ["ana"])

    def test_quem_entra_depois_nao_aparece(self):
        sala = nova_sala(["ana", "bob"])
        sala.iniciar_partida()
        sala.estado = "finalizada"
        sala.adicionar_jogador("caio")
        self.assertEqual(len(sala.placar_ordenado()), 2)


class TestTurnos(unittest.TestCase):
    def test_vez_circular(self):
        sala = nova_sala(["ana", "bob", "caio"])
        sala.iniciar_partida()
        sala.iniciar_rodada("gato", "Animais")
        ordem = []
        for i in range(4):
            ordem.append(sala.jogador_da_vez())
            sala.passar_vez()
        self.assertEqual(ordem, ["ana", "bob", "caio", "ana"])

    def test_primeiro_jogador_alterna(self):
        sala = nova_sala(["ana", "bob", "caio"], rodadas=4)
        sala.iniciar_partida()
        primeiros = []
        for i in range(4):
            sala.iniciar_rodada("gato", "Animais")
            primeiros.append(sala.jogador_da_vez())
        self.assertEqual(primeiros, ["ana", "bob", "caio", "ana"])

    def test_quem_comecou_saiu(self):
        # bob comecou a rodada 2 e saiu: a rodada 3 comeca com caio
        sala = nova_sala(["ana", "bob", "caio", "dani"])
        sala.iniciar_partida()
        sala.iniciar_rodada("gato", "Animais")
        sala.iniciar_rodada("gato", "Animais")
        self.assertEqual(sala.jogador_da_vez(), "bob")
        sala.remover_jogador("bob")
        sala.iniciar_rodada("gato", "Animais")
        self.assertEqual(sala.jogador_da_vez(), "caio")

    def test_ultimo_comecou_e_saiu(self):
        # dani (ultima) comecou e saiu: volta para o primeiro da lista
        sala = nova_sala(["ana", "bob", "caio", "dani"])
        sala.iniciar_partida()
        for i in range(4):
            sala.iniciar_rodada("gato", "Animais")
        self.assertEqual(sala.jogador_da_vez(), "dani")
        sala.remover_jogador("dani")
        sala.iniciar_rodada("gato", "Animais")
        self.assertEqual(sala.jogador_da_vez(), "ana")

    def test_saida_de_quem_tem_a_vez(self):
        sala = nova_sala(["ana", "bob", "caio"])
        sala.iniciar_partida()
        sala.iniciar_rodada("gato", "Animais")
        sala.passar_vez()  # vez de bob
        sala.remover_jogador("bob")
        self.assertEqual(sala.jogador_da_vez(), "caio")

    def test_dono_passa_para_o_proximo(self):
        sala = nova_sala(["ana", "bob", "caio"])
        sala.remover_jogador("ana")
        self.assertEqual(sala.dono_addr, "bob")


if __name__ == "__main__":
    unittest.main()
