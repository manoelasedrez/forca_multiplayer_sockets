import json
import os
import tempfile
import unittest

import caminho_entrega  # noqa: F401 (precisa vir antes do codigo do jogo)
from servidor import banco_palavras


class TestNormalizacao(unittest.TestCase):
    def test_normalizar(self):
        self.assertEqual(banco_palavras.normalizar("MAÇÃ"), "maca")
        self.assertEqual(banco_palavras.normalizar("Pêssego"), "pessego")

    def test_letra_valida(self):
        self.assertTrue(banco_palavras.letra_valida("a"))
        self.assertTrue(banco_palavras.letra_valida(" Ã "))
        self.assertFalse(banco_palavras.letra_valida("ab"))
        self.assertFalse(banco_palavras.letra_valida("1"))
        self.assertFalse(banco_palavras.letra_valida("-"))
        self.assertFalse(banco_palavras.letra_valida(""))

    def test_mascarar(self):
        self.assertEqual(banco_palavras.mascarar("guarda-chuva", []), "______-_____")
        self.assertEqual(banco_palavras.mascarar("guarda-chuva", ["a"]), "__A__A-____A")
        self.assertEqual(banco_palavras.mascarar("maçã", ["m", "c", "a"]), "MAÇÃ")

    def test_contar_ocorrencias(self):
        self.assertEqual(banco_palavras.contar_ocorrencias("banana", "a"), 3)
        self.assertEqual(banco_palavras.contar_ocorrencias("maçã", "a"), 2)
        self.assertEqual(banco_palavras.contar_ocorrencias("banana", "z"), 0)


class TestValidacao(unittest.TestCase):
    def test_palavras_validas(self):
        self.assertIsNone(banco_palavras.validar_palavra("gato"))
        self.assertIsNone(banco_palavras.validar_palavra("guarda-chuva"))
        self.assertIsNone(banco_palavras.validar_palavra("mesa de jantar"))

    def test_palavras_invalidas(self):
        self.assertIsNotNone(banco_palavras.validar_palavra("pe"))  # menos de 3 letras
        self.assertIsNotNone(banco_palavras.validar_palavra("a" * 21))  # mais de 20 letras
        self.assertIsNotNone(banco_palavras.validar_palavra("gato2"))
        self.assertIsNotNone(banco_palavras.validar_palavra("-gato"))
        self.assertIsNotNone(banco_palavras.validar_palavra("gato--preto"))
        self.assertIsNotNone(banco_palavras.validar_palavra("gato  preto"))

    def test_carregar_ignora_invalidas_e_repetidas(self):
        dados = {"categorias": {"Frutas": ["maçã", "maca", "uv", "banana"], "Outra": ["banana", "kiwi"]}}
        arquivo = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(dados, arquivo)
        arquivo.close()
        try:
            palavras = banco_palavras.carregar_palavras(arquivo.name)
        finally:
            os.remove(arquivo.name)
        self.assertEqual(palavras, [("maçã", "Frutas"), ("banana", "Frutas"), ("kiwi", "Outra")])

    def test_banco_real_carrega(self):
        palavras = banco_palavras.carregar_palavras()
        self.assertGreater(len(palavras), 0)
        self.assertEqual(len(banco_palavras.listar_categorias(palavras)), 10)


class TestSorteio(unittest.TestCase):
    def setUp(self):
        self.palavras = [("gato", "Animais"), ("girafa", "Animais"), ("uva", "Frutas"), ("abacaxi", "Frutas")]

    def test_dificuldade(self):
        self.assertEqual(banco_palavras.dificuldade_da_palavra("uva"), "easy")
        self.assertEqual(banco_palavras.dificuldade_da_palavra("girafa"), "medium")
        self.assertEqual(banco_palavras.dificuldade_da_palavra("guarda-chuva"), "hard")

    def test_filtrar(self):
        self.assertEqual(banco_palavras.filtrar_palavras(self.palavras, "easy", "qualquer"),
                         [("gato", "Animais"), ("uva", "Frutas")])
        self.assertEqual(banco_palavras.filtrar_palavras(self.palavras, "easy", "Frutas"), [("uva", "Frutas")])
        self.assertEqual(banco_palavras.filtrar_palavras(self.palavras, "hard", "qualquer"), [])

    def test_sortear_sem_repetir(self):
        candidatas = banco_palavras.filtrar_palavras(self.palavras, "easy", "qualquer")
        for i in range(20):
            palavra, categoria = banco_palavras.sortear_palavra(candidatas, ["gato"])
            self.assertEqual(palavra, "uva")


if __name__ == "__main__":
    unittest.main()
