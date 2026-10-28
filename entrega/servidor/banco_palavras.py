"""
Banco de palavras: tudo que o servidor precisa saber sobre AS PALAVRAS do jogo.

Resumao do que tem aq:
  - carregar o palavras.json e jogar fora o que for invalido ou repetido;
  - sortear a palavra de cada rodada;
  - tratar letra e acento (A, a, Ã... tudo vale igual na hora de comparar);
  - montar a palavra escondida, tipo "__A__A-____A".

O jogo tem um SERVIDOR (UM programa so, que roda o jogo de verdade) e varios
CLIENTES (o terminal de cada jogador). Os clientes ñ sabem a palavra e ñ decidem
nada: so mandam "tentei a letra A" pela rede e esperam a resposta. Quem guarda o
segredo e confere se acertou e o servidor. Por isso este arquivo mora na pasta do
servidor e o cliente nunca importa ele.

Nada aq mexe com socket (a "tomada" por onde os programas conversam pela rede) nem
com thread (um "atendente" que o servidor cria pra cada jogador). So le arquivo
(carregar_palavras) e sorteia (sortear_palavra). Isso deixa facil de testar sem
subir servidor (desenvolvimento/testes/test_banco_palavras.py).

Regras do jogo que dependem daqui: regras.md, secoes 2.2, 3.4 a 3.6, 4.1, 4.2 e 4.3.
"""

import json
import os
import random

# Caminho do palavras.json montado a partir DESTE arquivo, e ñ da pasta onde vc rodou
# o comando. Por isso funciona igualzinho de qualquer lugar.
CAMINHO_PALAVRAS = os.path.join(os.path.dirname(__file__), "..", "dados", "palavras.json")

# Alfabeto SEM acento. O acento e resolvido na normalizar() ANTES de comparar com isso.
LETRAS = "abcdefghijklmnopqrstuvwxyz"
# Espaco e hifen aparecem na palavra ("guarda-chuva"), mas ñ contam como letra e ñ
# precisam ser adivinhados: ja aparecem desde o comeco (regras.md 4.3).
SEPARADORES = " -"

# Limites de uma palavra do banco (regras.md 4.1).
# MIN e MAX contam so LETRAS: "guarda-chuva" tem 11 letras, ñ 12.
MIN_LETRAS = 3
MAX_LETRAS = 20
# Esse aq conta TUDO (letra + espaco + hifen).
MAX_CARACTERES = 30

# Categoria "curinga": quem cria a sala pode pedir "qualquer" e ai o sorteio usa todas.
# CUIDADO: o servidor compara esse texto com o que chega do cliente pela rede, e o
# regras.md tb cita "qualquer". Se mudar aq, tem que mudar la.
CATEGORIA_QUALQUER = "qualquer"

# Tabela de-para pra tirar acento. Usado so na comparacao: a grafia original e mantida na palavra
# (o jogador ve MAÇÃ, ñ MACA).
# CUIDADO: letra com acento que ñ estiver aqui (ï, è, ö...) NAO e convertida, e a
# so_caracteres_permitidos() recusa. Resultado: palavra do banco descartada ou palpite
# recusado. Se algum dia entrar palavra assim, e so acrescentar na tabela.
ACENTOS = {
    "á": "a", "à": "a", "â": "a", "ã": "a",
    "é": "e", "ê": "e",
    "í": "i",
    "ó": "o", "ô": "o", "õ": "o",
    "ú": "u", "ü": "u",
    "ç": "c",
}


def normalizar(texto):
    """
    Deixa o texto minusculo e sem acento/cedilha: "MAÇÃ" vira "maca".

    Serve SO pra comparar. A palavra que o jogador ve continua com a grafia original
    (ver mascarar()).

    Por que existe: o jogador digita "a" e espera que o "Ã" da MAÇÃ apareca junto
    (regras.md 4.2). Se a gente comparasse direto, "a" e "ã" seriam letras diferentes
    e o jogo ia parecer quebrado. Achei babado de simples, e e a base do arquivo todo.

    CUIDADO: o servidor usa isso pra comparar letra, palpite e palavras ja usadas.
    Normalizou so UM lado da comparacao? O bug aparece SO com palavra acentuada, e e
    esquisitinho de achar, pq os testes com "gato" passam certinho.
    """
    resultado = ""
    for c in texto.lower():  # lower() ANTES: "Ã" e "ã" caem na mesma entrada da tabela
        if c in ACENTOS:
            resultado += ACENTOS[c]
        else:
            resultado += c  # ñ esta na tabela (letra normal, numero, espaco...): fica igual
    return resultado


def contar_letras(palavra):
    """
    Conta so as LETRAS da palavra, sem espaco e sem hifen.

    "guarda-chuva" tem 12 caracteres mas 11 letras. E a conta de LETRAS (ñ de
    caracteres) que decide a dificuldade (easy/medium/hard) e se a palavra cabe
    nos limites de MIN_LETRAS a MAX_LETRAS.
    """
    total = 0
    for c in palavra:
        if c not in SEPARADORES:
            total += 1
    return total


def so_caracteres_permitidos(texto):
    """
    True se o texto so tem letras (com ou sem acento), espaco e hifen.

    Usada em DOIS lugares: pra aprovar palavra do banco (validar_palavra) e pra
    aprovar o PALPITE que o jogador manda pela rede (server.py). O segundo uso e o
    importante: tudo que chega pela rede ñ e confiavel (um cliente mexido pode
    mandar qualquer coisa), entao o servidor confere ANTES de usar. Isso e o
    "tratar mensagens/requisicoes invalidas" que o enunciado pede.

    CUIDADO: texto vazio devolve True (o loop nem roda). Quem chamar tem que checar
    vazio por fora; o server ja faz isso antes (RESPOSTA_VAZIA).
    """
    # normaliza primeiro: "Ã" vira "a", que esta em LETRAS
    for c in normalizar(texto):
        if c not in LETRAS and c not in SEPARADORES:
            return False
    return True


def validar_palavra(palavra):
    """
    Devolve None se a palavra pode entrar no banco, ou o MOTIVO (texto) da recusa.

    O jeito "None = deu certo, texto = deu ruim" e pra quem chamar poder imprimir o
    motivo no aviso do terminal do servidor ("Palavra ignorada ... motivo").

    A ORDEM das checagens importa: se a palavra tem 2 problemas, so o primeiro
    motivo aparece.
    """
    # 1) so letra, espaco e hifen (numero e simbolo ficam de fora)
    if not so_caracteres_permitidos(palavra):
        return "caracteres nao permitidos"
    # 2) tamanho em LETRAS (regras.md 4.1)
    n = contar_letras(palavra)
    if n < MIN_LETRAS or n > MAX_LETRAS:
        return f"deve ter de {MIN_LETRAS} a {MAX_LETRAS} letras"
    # 3) tamanho total, contando espaco e hifen
    if len(palavra) > MAX_CARACTERES:
        return f"deve ter no maximo {MAX_CARACTERES} caracteres"
    # 4) ñ pode comecar nem terminar com separador.
    # Obs: o carregar_palavras ja tira espaco das pontas (strip), entao por la na pratica
    # so o hifen cai aq. Quem chamar direto (os testes, por ex.) pode cair nos dois.
    if palavra[0] in SEPARADORES or palavra[-1] in SEPARADORES:
        return "comeca ou termina com espaco ou hifen"
    # 5) separador duplo ("gato--preto", "gato  preto"). Olha cada par de vizinhos.
    for i in range(len(palavra) - 1):
        if palavra[i] in SEPARADORES and palavra[i + 1] in SEPARADORES:
            return "tem espacos ou hifens seguidos"
    return None


def carregar_palavras(caminho=CAMINHO_PALAVRAS):
    """
    Le o palavras.json e devolve uma lista de (palavra, categoria) JA LIMPA.

    Roda UMA vez, quando o servidor liga. Depois disso o servidor so LE a lista
    (nunca altera), entao as threads atendendo os jogadores ao mesmo tempo ñ brigam
    por ela.

    Palavra invalida ou repetida e DESCARTADA com aviso no terminal (regras.md 4.1),
    e isso acontece ao LIGAR o servidor, ñ no meio da partida. Faz diferenca: uma
    palavra com numero, por ex., seria IMPOSSIVEL de acertar, pq a letra_valida() so
    aceita a-z. Melhor ver o aviso ao ligar do que descobrir isso com jogador na sala.

    O arquivo tem um bloco "categorias" e, dentro dele, cada categoria com a lista
    de palavras dela.
    """
    # abre, le tudo e fecha. Se o json estiver quebrado o close ñ roda, mas ñ importa:
    # o servidor nem chega a subir.
    arquivo = open(caminho, encoding="utf-8")
    dados = json.load(arquivo)
    arquivo.close()

    palavras = []
    # palavras NORMALIZADAS ja aceitas, pra achar repetida. E lista mesmo; sao ~320
    # palavras, entao a busca lenta ñ pesa.
    vistas = []
    for categoria in dados["categorias"]:
        for palavra in dados["categorias"][categoria]:
            palavra = palavra.strip()  # tira espaco sobrando nas pontas do json
            motivo = validar_palavra(palavra)
            if motivo is not None:
                print(f"Palavra ignorada '{palavra}' ({categoria}): {motivo}")
                continue
            # Repetida = igual SEM olhar acento nem maiuscula ("Maca" e "maçã" sao a mesma).
            # Tem que ser assim pq o sortear_palavra compara normalizado: se as duas
            # ficassem, ele trataria as duas como UMA so.
            if normalizar(palavra) in vistas:
                print(f"Palavra ignorada '{palavra}' ({categoria}): repetida")
                continue
            vistas.append(normalizar(palavra))
            palavras.append((palavra, categoria))
    return palavras


def listar_categorias(palavras):
    """
    Lista as categorias (Frutas, Animais...) na ORDEM em que aparecem no arquivo, sem repetir.

    Duas serventias: o jogador recebe essa lista ao conectar (regras.md 1) pra escolher
    na hora de criar a sala, e o servidor usa ela pra recusar categoria inexistente
    (CATEGORIA_INVALIDA). Lista (e ñ conjunto) mantem a ordem do arquivo, assim o
    menu sai sempre igual.
    """
    categorias = []
    for palavra, categoria in palavras:
        if categoria not in categorias:
            categorias.append(categoria)
    return categorias


def dificuldade_da_palavra(palavra):
    """
    Diz se a palavra e "easy", "medium" ou "hard" pelo numero de LETRAS.

        easy: ate 5 letras / medium: 6 a 8 / hard: 9 ou mais   (regras.md 4.1)

    A dificuldade ñ vem escrita no json, ela e CALCULADA aq. Entao mexer nesses
    numeros muda quantas palavras cada nivel tem, e pode deixar uma combinacao de
    categoria + dificuldade sem palavra suficiente. Hoje, por ex., Profissoes e
    Comidas e bebidas ñ tem NENHUMA easy (regras.md 2.2).
    """
    n = contar_letras(palavra)
    if n <= 5:
        return "easy"
    if n <= 8:
        return "medium"
    return "hard"


def filtrar_palavras(palavras, dificuldade, categoria):
    """
    Separa as palavras que servem pra sala: da dificuldade E da categoria pedidas.

    "qualquer" na categoria e curinga e aceita todas. Devolve lista de
    (palavra, categoria) e ela PODE vir vazia.

    Roda em DOIS momentos: ao CRIAR a sala (pra ver se tem palavra pra todas as
    rodadas; se ñ tiver, erro PALAVRAS_INSUFICIENTES) e ao comecar cada RODADA (pra
    sortear). O resultado ñ fica guardado, a conta e refeita toda vez.
    """
    candidatas = []
    for palavra, cat in palavras:  # cat = categoria DA palavra; categoria = a que o jogador pediu
        # pula se a dificuldade ñ bate
        if dificuldade_da_palavra(palavra) != dificuldade:
            continue
        # pula se a categoria ñ bate (a menos que seja o curinga)
        if categoria != CATEGORIA_QUALQUER and cat != categoria:
            continue
        candidatas.append((palavra, cat))
    return candidatas


def sortear_palavra(candidatas, usadas):
    """
    Sorteia UMA palavra entre as candidatas que ainda ñ sairam nessa partida.

    'usadas' tem as palavras ja sorteadas, NORMALIZADAS (o server guarda assim em
    palavras_usadas), por isso a comparacao aq e com normalizar(palavra).

    Regra: palavra ñ repete DENTRO da partida (regras.md 4.1). Entre partidas pode.

    CUIDADO: se TODAS ja foram usadas, 'livres' fica vazia e random.choice(lista
    vazia) da IndexError. Hoje isso ñ acontece pq o server confere ANTES, ao criar
    a sala: exige candidatas >= numero de rodadas (PALAVRAS_INSUFICIENTES,
    regras.md 2.2). Mexeu naquela checagem? Pensa aq tb.
    """
    livres = []
    for palavra, categoria in candidatas:
        if normalizar(palavra) not in usadas:
            livres.append((palavra, categoria))
    return random.choice(livres)


def contar_ocorrencias(palavra, letra):
    """
    Quantas vezes a letra aparece na palavra, ignorando acento.

        "banana" + "a" -> 3        "maçã" + "a" -> 2

    Esse numero e a PONTUACAO da jogada: +1 ponto por ocorrencia (regras.md 3.5).

    CUIDADO: a 'letra' tem que chegar JA normalizada (minuscula, sem acento). So a
    palavra e normalizada aq dentro. Passou "Ã" em vez de "a"? Da 0, e o jogador
    "erra" de mentirinha um acerto. O server normaliza antes de chamar.
    """
    total = 0
    for c in normalizar(palavra):
        if c == letra:
            total += 1
    return total


def mascarar(palavra, letras_usadas):
    """
    Monta a palavra escondida que o jogador ve: letra descoberta aparece, o resto vira "_".

        mascarar("guarda-chuva", ["a"]) -> "__A__A-____A"        (regras.md 4.3)

    Espaco e hifen aparecem desde o comeco, e tudo sai em MAIUSCULAS.

    'letras_usadas' sao as letras ja tentadas, NORMALIZADAS (guarda "a", ñ "Ã").
    O truque: compara a versao normalizada de cada letra, mas MOSTRA a original
    (c.upper()). Por isso digitar "a" revela o "A" e o "Ã" juntos em MAÇÃ.

    O cliente NUNCA recebe a palavra de verdade durante
    a rodada, so essa versao mascarada (a palavra so sai do servidor no fim da rodada;
    README, secao Arquitetura). Se o cliente soubesse a palavra, um cliente alterado
    podia trapacear.
    """
    resultado = ""
    for c in palavra:
        if c in SEPARADORES:
            resultado += c  # espaco/hifen: sempre visivel
        elif normalizar(c) in letras_usadas:
            resultado += c.upper()  # descoberta: mostra a grafia ORIGINAL, em maiuscula
        else:
            resultado += "_"
    return resultado


def letra_valida(texto):
    """
    True se o texto e UMA letra de a a z (acentuada vale: "Ã" conta como "a").

    Recusa "ab", "1", "-" e vazio. E o filtro da jogada "letra": o que chega do
    cliente pela rede ñ e confiavel (mesma ideia da so_caracteres_permitidos), entao
    o servidor confere antes de usar. Se falhar, o erro e LETRA_INVALIDA e a vez ñ
    passa (regras.md 3.3 e 3.4).

    CUIDADO, pegadinha: ñ tira o 'len(texto) == 1'. O 'in' numa string testa PEDACO,
    e "ab" e um pedaco do alfabeto (a string vazia tb!), entao sem essa checagem de
    tamanho "ab" passava como letra valida.
    """
    texto = normalizar(texto.strip())
    return len(texto) == 1 and texto in LETRAS
