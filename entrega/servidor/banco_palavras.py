"""
Banco de palavras: carga do arquivo, sorteio e tratamento de letras.
"""

import json
import os
import random

CAMINHO_PALAVRAS = os.path.join(os.path.dirname(__file__), "..", "dados", "palavras.json")

LETRAS = "abcdefghijklmnopqrstuvwxyz"
SEPARADORES = " -"

MIN_LETRAS = 3
MAX_LETRAS = 20
MAX_CARACTERES = 30

CATEGORIA_QUALQUER = "qualquer"

# Usado so na comparacao: a grafia original e mantida na palavra
ACENTOS = {
    "á": "a", "à": "a", "â": "a", "ã": "a",
    "é": "e", "ê": "e",
    "í": "i",
    "ó": "o", "ô": "o", "õ": "o",
    "ú": "u", "ü": "u",
    "ç": "c",
}


def normalizar(texto):
    """Minusculas e sem acentos/cedilha."""
    resultado = ""
    for c in texto.lower():
        if c in ACENTOS:
            resultado += ACENTOS[c]
        else:
            resultado += c
    return resultado


def contar_letras(palavra):
    """Conta as letras, sem espacos e hifens."""
    total = 0
    for c in palavra:
        if c not in SEPARADORES:
            total += 1
    return total


def so_caracteres_permitidos(texto):
    """Apenas letras (com ou sem acento), espaco e hifen."""
    for c in normalizar(texto):
        if c not in LETRAS and c not in SEPARADORES:
            return False
    return True


def validar_palavra(palavra):
    """Devolve None se a palavra pode entrar no banco, ou o motivo da recusa."""
    if not so_caracteres_permitidos(palavra):
        return "caracteres nao permitidos"
    n = contar_letras(palavra)
    if n < MIN_LETRAS or n > MAX_LETRAS:
        return f"deve ter de {MIN_LETRAS} a {MAX_LETRAS} letras"
    if len(palavra) > MAX_CARACTERES:
        return f"deve ter no maximo {MAX_CARACTERES} caracteres"
    if palavra[0] in SEPARADORES or palavra[-1] in SEPARADORES:
        return "comeca ou termina com espaco ou hifen"
    for i in range(len(palavra) - 1):
        if palavra[i] in SEPARADORES and palavra[i + 1] in SEPARADORES:
            return "tem espacos ou hifens seguidos"
    return None


def carregar_palavras(caminho=CAMINHO_PALAVRAS):
    """Devolve uma lista de (palavra, categoria), ja sem palavras invalidas ou repetidas."""
    arquivo = open(caminho, encoding="utf-8")
    dados = json.load(arquivo)
    arquivo.close()

    palavras = []
    vistas = []  # palavras normalizadas, para achar repetidas
    for categoria in dados["categorias"]:
        for palavra in dados["categorias"][categoria]:
            palavra = palavra.strip()
            motivo = validar_palavra(palavra)
            if motivo is not None:
                print(f"Palavra ignorada '{palavra}' ({categoria}): {motivo}")
                continue
            if normalizar(palavra) in vistas:
                print(f"Palavra ignorada '{palavra}' ({categoria}): repetida")
                continue
            vistas.append(normalizar(palavra))
            palavras.append((palavra, categoria))
    return palavras


def listar_categorias(palavras):
    """Categorias na ordem do arquivo, sem repetir."""
    categorias = []
    for palavra, categoria in palavras:
        if categoria not in categorias:
            categorias.append(categoria)
    return categorias


def dificuldade_da_palavra(palavra):
    """easy: ate 5 letras / medium: 6 a 8 / hard: 9 ou mais."""
    n = contar_letras(palavra)
    if n <= 5:
        return "easy"
    if n <= 8:
        return "medium"
    return "hard"


def filtrar_palavras(palavras, dificuldade, categoria):
    """Palavras da dificuldade e da categoria pedidas ("qualquer" aceita todas)."""
    candidatas = []
    for palavra, cat in palavras:
        if dificuldade_da_palavra(palavra) != dificuldade:
            continue
        if categoria != CATEGORIA_QUALQUER and cat != categoria:
            continue
        candidatas.append((palavra, cat))
    return candidatas


def sortear_palavra(candidatas, usadas):
    """Sorteia uma palavra que ainda nao esta em 'usadas' (normalizadas)."""
    livres = []
    for palavra, categoria in candidatas:
        if normalizar(palavra) not in usadas:
            livres.append((palavra, categoria))
    return random.choice(livres)


def contar_ocorrencias(palavra, letra):
    """Quantas vezes a letra (normalizada) aparece na palavra."""
    total = 0
    for c in normalizar(palavra):
        if c == letra:
            total += 1
    return total


def mascarar(palavra, letras_usadas):
    """Mostra as letras ja usadas, espacos e hifens; o resto vira '_'."""
    resultado = ""
    for c in palavra:
        if c in SEPARADORES:
            resultado += c
        elif normalizar(c) in letras_usadas:
            resultado += c.upper()
        else:
            resultado += "_"
    return resultado


def letra_valida(texto):
    """Uma unica letra de a a z (aceita acentuadas)."""
    texto = normalizar(texto.strip())
    return len(texto) == 1 and texto in LETRAS
