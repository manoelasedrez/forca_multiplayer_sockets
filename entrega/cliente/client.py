import socket
import sys
import threading
import time
from protocol import protocol
from nacl.public import PrivateKey, PublicKey
from nacl.encoding import Base64Encoder

HOST = "127.0.0.1"  # padrao: servidor na mesma maquina
PORT = 38905

MAX_ERROS = 6
PENALIDADE_PALPITE = 2  # so para avisar o jogador; quem decide e o servidor
CATEGORIA_QUALQUER = "qualquer"

# Codigos ANSI (mude para False se o terminal nao suportar)
USAR_CORES = True
LIMPAR_TELA = True  # redesenha a tela a cada turno, em vez de empilhar mensagens
VERDE = "\033[32m"
VERMELHO = "\033[31m"
AMARELO = "\033[33m"
CIANO = "\033[36m"
CINZA = "\033[90m"
NEGRITO = "\033[1m"
RESET = "\033[0m"
CODIGO_LIMPAR_TELA = "\033[2J\033[H"

LARGURA = 60  # largura das linhas e quadros da tela
MAX_HISTORICO = 4  # jogadas recentes mostradas no painel

MOTIVOS_RODADA = {
    protocol.MOTIVO_PALPITE: "acertou a palavra",
    protocol.MOTIVO_PALAVRA_COMPLETA: "revelou a última letra",
    protocol.MOTIVO_LIMITE_ERROS: "limite de erros atingido",
    protocol.MOTIVO_INTERROMPIDA: "partida interrompida por falta de jogadores",
}


def colorir(texto, cor):
    if USAR_CORES:
        return cor + texto + RESET
    return texto


def desenhar_forca(erros):
    # Devolve as 5 linhas da forca de acordo com o numero de erros (0 a 6)
    cabeca = " "
    corpo = " "
    braco_esq = " "
    braco_dir = " "
    perna_esq = " "
    perna_dir = " "
    if erros >= 1:
        cabeca = "O"
    if erros >= 2:
        corpo = "|"
    if erros >= 3:
        braco_esq = "/"
    if erros >= 4:
        braco_dir = "\\"
    if erros >= 5:
        perna_esq = "/"
    if erros >= 6:
        perna_dir = "\\"
    return [
        "  +---+",
        "  |   " + cabeca,
        "  |  " + braco_esq + corpo + braco_dir,
        "  |  " + perna_esq + " " + perna_dir,
        " ===",
    ]


class Client(socket.socket):
    def __init__(self, host, port, username):
        super().__init__(socket.AF_INET, socket.SOCK_STREAM)
        self.host = host
        self.port = port
        self.username = username
        self.public_key = None
        self.private_key = None

        self.server_public_key = None  # Chave publica recebida do servidor
        self.categorias = []  # Categorias do banco, recebidas no CONNECT OK

        self.sala_id = None  # Id da sala atual
        self.sala_nome = None  # Apelido da sala atual
        self.sala_pedida = None  # Id enviado no ROOM JOIN, esperando resposta
        self.criacao_pedida = None  # Dados enviados no ROOM CREATE, esperando resposta
        self.sou_dono = False
        self.jogadores = []
        self.rodadas = 0
        self.categoria_sala = ""

        # Partida
        self.em_partida = False
        self.pontos = {}  # nome -> pontos

        # Rodada
        self.rodada = 0
        self.categoria = ""
        self.palavra = ""
        self.letras = []
        self.erros = 0
        self.vez_de = ""
        self.tempo = 0
        self.minha_vez = False
        self.historico = []  # jogadas recentes da rodada, ja formatadas
        self.ultimo_jogador = ""  # quem fez a ultima jogada (para o fim da rodada)
        self.resultado_anterior = ""  # resumo da rodada anterior, mostrado no painel

        self.prompt = ""  # texto do input() atual, reimpresso apos cada aviso
        self.encerrando = False
        self.conectado = False  # vira False quando a conexao com o servidor cai

    def print(self, msg):
        print(msg)

    def iniciar(self):
        try:
            self.connect((self.host, self.port))
        except OSError as e:
            self.print(f"Erro ao conectar no servidor: {e}")
            try:
                self.port += 1  # Tenta conectar na próxima porta
                self.connect((self.host, self.port))
            except OSError as e:
                self.print(f"Erro ao conectar no servidor: {e}")
                return
        self.print(f"Conectado ao servidor em {self.host}:{self.port}")

        self.private_key = PrivateKey.generate()
        self.public_key = self.private_key.public_key

        if not self.conectar():
            self.close()
            return
        self.conectado = True

        threading.Thread(target=self.receber_mensagens_thread, daemon=True).start()
        self.menu()

    def conectar(self):
        # Envia o CONNECT e espera a resposta do servidor
        chave_texto = self.public_key.encode(encoder=Base64Encoder).decode()
        if not self.enviar(protocol.ConnectRequest(chave_texto, self.username)):
            return False

        try:
            resposta = protocol.receive_message(self)
        except Exception as e:
            self.print(f"Erro de conexão com o servidor: {e}")
            return False

        if isinstance(resposta, protocol.ConnectOk):
            self.server_public_key = PublicKey(resposta.public_key, encoder=Base64Encoder)
            self.categorias = resposta.categorias
            self.print("Conexão com o servidor estabelecida")
            return True

        if isinstance(resposta, protocol.ConnectError):
            self.print(f"Servidor recusou a conexão: {resposta.data.strip()}")
            return False

        self.print(f"Resposta inesperada do servidor: {resposta}")
        return False

    def receber_mensagens_thread(self):
        while True:
            try:
                mensagem = protocol.receive_message(self)

            except protocol.ErroProtocolo as e:
                # Mensagem malformada do servidor: ignora e continua
                self.print(colorir(f"\nMensagem inválida recebida do servidor (ignorada): {e}", VERMELHO))
                continue

            except Exception as e:
                # Conexao caiu (ou mensagem grande demais, sem como continuar)
                self.perder_conexao(e)
                break

            self.handle_mensagem(mensagem)
            if self.vem_outra_em_seguida(mensagem):
                continue  # o prompt so e repetido depois da ultima mensagem da sequencia
            self.mostrar_prompt()

    def vem_outra_em_seguida(self, mensagem):
        # Mensagens que o servidor sempre manda junto com outra logo depois
        if isinstance(mensagem, protocol.TurnResponseOk):
            return True  # vem o resultado da jogada
        if isinstance(mensagem, protocol.TurnResponseBroadcast):
            return True  # vem o proximo TURN ou o ROUND END
        if isinstance(mensagem, protocol.TurnTimeout):
            return True  # vem o proximo TURN
        if isinstance(mensagem, protocol.RoomStartOk) or isinstance(mensagem, protocol.RoomStarted):
            return True  # vem o ROUND START
        if isinstance(mensagem, protocol.RoundStart):
            return True  # vem o primeiro TURN
        if isinstance(mensagem, protocol.GameOver):
            return True  # vem o ROOM UPDATE
        if isinstance(mensagem, protocol.RoundEnd):
            # Na ultima rodada (ou se foi interrompida) vem o GAME OVER
            return mensagem.round >= self.rodadas or mensagem.motivo == protocol.MOTIVO_INTERROMPIDA
        return False

    def perder_conexao(self, motivo):
        if self.encerrando or not self.conectado:
            return
        self.conectado = False
        self.print(colorir(f"\nConexão com o servidor perdida: {motivo}", VERMELHO))
        self.print("Pressione Enter para encerrar.")

    def handle_mensagem(self, mensagem):
        # --- Salas ---
        if isinstance(mensagem, protocol.RoomCreateOk):
            nome_sala, rodadas, categoria = self.criacao_pedida
            self.sala_id = mensagem.room_id
            self.sala_nome = nome_sala
            self.rodadas = rodadas
            self.categoria_sala = categoria
            self.sou_dono = True
            self.jogadores = [self.username]
            self.aviso(f"Sala '{self.sala_nome}' criada!   Código: {colorir(self.sala_id, NEGRITO)}")
            self.print("  Passe o código aos outros jogadores. Aguardando jogadores...")

        if isinstance(mensagem, protocol.RoomJoinOk):
            self.sala_id = self.sala_pedida
            self.sala_nome = mensagem.room_name
            self.rodadas = mensagem.rounds
            self.categoria_sala = mensagem.categoria
            self.jogadores = mensagem.users
            self.sou_dono = False
            self.aviso(f"Você entrou na sala '{self.sala_nome}' ({self.sala_id})")
            self.print(f"  Rodadas: {self.rodadas}   Dificuldade: {mensagem.dificuldade}   Categoria: {self.categoria_sala}")
            self.print(f"  Jogadores: {', '.join(mensagem.users)}")

        if isinstance(mensagem, protocol.RoomLeaveOk):
            self.aviso(f"Você saiu da sala '{self.sala_nome}'")
            self.limpar_sala()

        if isinstance(mensagem, protocol.RoomUpdate):
            # Compara com a lista anterior para dizer quem entrou e quem saiu
            mudancas = []
            for nome in mensagem.users:
                if nome not in self.jogadores:
                    mudancas.append(f"{nome} entrou na sala")
            for nome in self.jogadores:
                if nome not in mensagem.users:
                    mudancas.append(f"{nome} saiu da sala")
            self.jogadores = mensagem.users
            self.sou_dono = len(mensagem.users) > 0 and mensagem.users[0] == self.username

            if self.em_partida:
                # Durante a partida, a saida aparece no painel, no proximo turno
                for texto in mudancas:
                    self.adicionar_historico(colorir(texto, AMARELO))
            else:
                if len(mudancas) > 0:
                    self.aviso(". ".join(mudancas) + ".")
                else:
                    self.print("")
                self.print(f"  Jogadores ({len(mensagem.users)}): {', '.join(mensagem.users)}")
                if mensagem.ready:
                    if self.sou_dono:
                        self.print(colorir("  Já é possível iniciar a partida (opção 3).", AMARELO))
                    else:
                        self.print("  Aguardando o dono iniciar a partida.")

        # --- Partida e rodadas ---
        if isinstance(mensagem, protocol.RoomStarted):
            self.em_partida = True
            self.rodadas = mensagem.rounds
            self.jogadores = mensagem.users
            self.pontos = {}
            for nome in mensagem.users:
                self.pontos[nome] = 0
            self.resultado_anterior = ""
            self.aviso(colorir(f"A partida vai começar! {self.rodadas} rodada(s).", NEGRITO))

        if isinstance(mensagem, protocol.RoundStart):
            self.rodada = mensagem.round
            self.categoria = mensagem.categoria
            self.palavra = mensagem.word
            self.letras = []
            self.erros = 0
            self.historico = []

        if isinstance(mensagem, protocol.Turn):
            self.vez_de = mensagem.user_turn
            self.tempo = mensagem.tempo
            self.minha_vez = mensagem.user_turn == self.username
            self.mostrar_painel()

        if isinstance(mensagem, protocol.TurnTimeout):
            self.adicionar_historico(colorir(f"{self.nome_ou_voce(mensagem.user_turn)}: tempo esgotado", AMARELO))
            self.minha_vez = False

        if isinstance(mensagem, protocol.TurnResponseBroadcast):
            self.palavra = mensagem.word
            self.erros = mensagem.erros
            self.letras = mensagem.letras
            self.ultimo_jogador = mensagem.user_turn
            if mensagem.user_turn in self.pontos:
                self.pontos[mensagem.user_turn] += mensagem.pontos
            if mensagem.guess:
                tipo = f"chutou {mensagem.answer.upper()}"
            else:
                tipo = f"tentou a letra {mensagem.answer.upper()}"
            if mensagem.accepted:
                resultado = colorir(f"acertou ({self.com_sinal(mensagem.pontos)})", VERDE)
            else:
                resultado = colorir(f"errou ({self.com_sinal(mensagem.pontos)})", VERMELHO)
            self.adicionar_historico(f"{self.nome_ou_voce(mensagem.user_turn)} {tipo}: {resultado}")
            self.minha_vez = False

        if isinstance(mensagem, protocol.RoundEnd):
            self.minha_vez = False
            self.palavra = mensagem.word
            for nome, pontos in mensagem.placar:
                self.pontos[nome] = pontos
            self.mostrar_fim_rodada(mensagem)

        if isinstance(mensagem, protocol.GameOver):
            self.minha_vez = False
            self.em_partida = False
            self.mostrar_fim_jogo(mensagem)

        if isinstance(mensagem, protocol.ErrorMessage):
            self.aviso(colorir(f"Erro: {mensagem.error}", VERMELHO))
            if mensagem.code == protocol.NAO_E_SUA_VEZ or mensagem.code == protocol.SEM_RODADA_ATIVA:
                self.minha_vez = False

    # -----------------------------------------------------------
    # Exibicao
    # -----------------------------------------------------------
    def aviso(self, texto):
        # Mensagem avulsa (fora do painel), separada por uma linha em branco
        self.print("")
        self.print("  " + texto)

    def linha(self, caractere="="):
        self.print(caractere * LARGURA)

    def limpar_tela(self):
        if LIMPAR_TELA:
            print(CODIGO_LIMPAR_TELA, end="")
        else:
            self.print("\n\n")

    def nome_ou_voce(self, nome):
        if nome == self.username:
            return "Você"
        return nome

    def com_sinal(self, pontos):
        if pontos > 0:
            return "+" + str(pontos)
        return str(pontos)

    def mostrar_palavra(self):
        # "BAN_N_" -> "B A N _ N _"
        return " ".join(self.palavra)

    def texto_placar(self, placar):
        # [("ana", 8), ("bob", 3)] -> "ana 8    bob 3", com o proprio nome em destaque
        partes = []
        for nome, pontos in placar:
            texto = f"{nome} {pontos}"
            if nome == self.username:
                texto = colorir(texto, NEGRITO)
            partes.append(texto)
        return "    ".join(partes)

    def placar_atual(self):
        placar = []
        for nome in self.jogadores:
            if nome in self.pontos:
                placar.append((nome, self.pontos[nome]))
        return placar

    def adicionar_historico(self, texto):
        self.historico.append(texto)
        if len(self.historico) > MAX_HISTORICO:
            self.historico.pop(0)

    def mostrar_cabecalho(self):
        esquerda = f"  {self.sala_nome}  ({self.sala_id})"
        direita = f"Rodada {self.rodada} de {self.rodadas}  "
        espacos = LARGURA - len(esquerda) - len(direita)
        if espacos < 2:
            espacos = 2
        self.linha("=")
        self.print(colorir(esquerda + " " * espacos + direita, CIANO))
        self.linha("=")

    def mostrar_forca_e_palavra(self):
        # Forca a esquerda; palavra, letras e erros a direita
        forca = desenhar_forca(self.erros)
        marcas = colorir("X " * self.erros, VERMELHO) + ". " * (MAX_ERROS - self.erros)
        letras = "  ".join(self.letras)
        if letras == "":
            letras = "-"
        info = [
            "",
            colorir(self.mostrar_palavra(), NEGRITO),
            "",
            f"Letras usadas:  {letras}",
            f"Erros:  {marcas} ({self.erros} de {MAX_ERROS})",
        ]
        for i in range(len(forca)):
            self.print("    " + forca[i].ljust(16) + info[i])

    def mostrar_painel(self):
        self.limpar_tela()
        self.mostrar_cabecalho()
        if self.resultado_anterior != "":
            self.print(colorir(f"  Rodada anterior: {self.resultado_anterior}", CINZA))
        self.print("")
        self.print(f"  Categoria:  {colorir(self.categoria, NEGRITO)}")
        self.print("")
        self.mostrar_forca_e_palavra()
        self.print("")
        self.print(f"  Placar:   {self.texto_placar(self.placar_atual())}")
        self.print("")
        self.print("  Últimas jogadas:")
        if len(self.historico) == 0:
            self.print(colorir("    (nenhuma ainda)", CINZA))
        for texto in self.historico:
            self.print("    - " + texto)
        self.print("")
        self.linha("-")
        if self.minha_vez:
            self.print(colorir(f"  >>> SUA VEZ!  Você tem {self.tempo} segundos.", AMARELO))
            self.print("      4 - Letra     5 - Palpite     6 - Sair da sala")
        else:
            self.print(f"  Vez de {colorir(self.vez_de, NEGRITO)} ({self.tempo} s). Aguarde...")
            self.print("      6 - Sair da sala     0 - Sair do jogo")
        self.linha("-")

    def mostrar_fim_rodada(self, mensagem):
        motivo = MOTIVOS_RODADA.get(mensagem.motivo, mensagem.motivo)
        if mensagem.motivo == protocol.MOTIVO_PALPITE or mensagem.motivo == protocol.MOTIVO_PALAVRA_COMPLETA:
            motivo = f"{self.nome_ou_voce(self.ultimo_jogador)} {motivo}"
        self.resultado_anterior = f"{mensagem.word} ({motivo})"

        self.limpar_tela()
        self.mostrar_cabecalho()
        self.print("")
        self.print(f"  Categoria:  {colorir(self.categoria, NEGRITO)}")
        self.print("")
        self.mostrar_forca_e_palavra()
        self.print("")
        self.print("  Últimas jogadas:")
        if len(self.historico) == 0:
            self.print(colorir("    (nenhuma)", CINZA))
        for texto in self.historico:
            self.print("    - " + texto)
        self.print("")
        self.linha("-")
        self.print(colorir(f"  FIM DA RODADA {mensagem.round}: {motivo}", NEGRITO))
        self.print(f"  A palavra era: {colorir(mensagem.word, NEGRITO)}")
        self.print("")
        self.print(f"  Placar:   {self.texto_placar(mensagem.placar)}")
        if mensagem.round < self.rodadas and mensagem.motivo != protocol.MOTIVO_INTERROMPIDA:
            self.print("")
            self.print(colorir("  Próxima rodada em instantes...", CINZA))
        self.linha("-")

    def mostrar_fim_jogo(self, mensagem):
        self.print("")
        self.linha("=")
        self.print(colorir("FIM DE JOGO".center(LARGURA), NEGRITO))
        self.linha("=")
        self.print("")
        if mensagem.motivo == protocol.MOTIVO_INTERROMPIDA:
            self.print(colorir("  Partida interrompida por falta de jogadores.", AMARELO))
            self.print("")
        self.mostrar_placar_final(mensagem.placar)
        self.print("")
        if len(mensagem.winners) == 0:
            self.print("  Ninguém venceu.")
        elif len(mensagem.winners) > 1:
            self.print(colorir(f"  Empate! Vencedores: {', '.join(mensagem.winners)}", VERDE))
        elif mensagem.winners[0] == self.username:
            self.print(colorir("  Você venceu!", VERDE))
        else:
            self.print(f"  Vencedor: {colorir(mensagem.winners[0], NEGRITO)}")
        self.print("")
        self.linha("=")
        self.print(colorir("  Pressione Enter para voltar ao menu da sala.", CINZA))

    def mostrar_placar_final(self, placar):
        # Empatados ficam na mesma posicao
        posicao = 0
        anterior = None
        for i in range(len(placar)):
            nome, pontos = placar[i]
            if pontos != anterior:
                posicao = i + 1
                anterior = pontos
            linha = f"    {posicao}º   {nome.ljust(16)} {str(pontos).rjust(4)} pontos"
            if nome == self.username:
                linha = colorir(linha, NEGRITO)
            self.print(linha)

    def mostrar_prompt(self):
        # Reimprime o que o jogador estava digitando, depois de um aviso
        if self.prompt != "":
            print(self.prompt, end="", flush=True)

    def ler(self, texto):
        self.prompt = texto
        valor = input(texto)
        self.prompt = ""
        return valor

    def limpar_sala(self):
        self.sala_id = None
        self.sala_nome = None
        self.sou_dono = False
        self.jogadores = []
        self.em_partida = False
        self.pontos = {}
        self.palavra = ""
        self.letras = []
        self.erros = 0
        self.minha_vez = False
        self.historico = []
        self.resultado_anterior = ""

    # -----------------------------------------------------------
    # Menu
    # -----------------------------------------------------------
    def menu(self):
        while True:
            # Fora de sala: so cria ou entra. Dentro: so joga ou sai.
            if self.sala_id is None:
                self.print("")
                self.linha("-")
                self.print("  1 - Criar sala")
                self.print("  2 - Entrar em sala")
                self.print("  0 - Sair")
                self.linha("-")
            elif not self.em_partida:
                # Em partida as opcoes ja aparecem no painel
                self.print("")
                self.linha("-")
                self.print(f"  Sala: {self.sala_nome}  ({self.sala_id})")
                self.print("")
                if self.sou_dono:
                    self.print("  3 - Iniciar partida")
                self.print("  6 - Sair da sala")
                self.print("  0 - Sair")
                self.linha("-")
            opcao = self.ler("Escolha uma opção: ").strip()

            if not self.conectado:
                self.print("Encerrando o cliente.")
                self.close()
                break

            if (opcao == "1" or opcao == "2") and self.sala_id is not None:
                self.aviso("Você já está em uma sala. Saia dela primeiro.")

            elif (opcao == "3" or opcao == "4" or opcao == "5" or opcao == "6") and self.sala_id is None:
                self.aviso("Você não está em uma sala.")

            elif (opcao == "4" or opcao == "5") and not self.em_partida:
                self.aviso("Nenhuma partida em andamento.")

            elif opcao == "1":
                self.criar_sala()

            elif opcao == "2":
                self.entrar_sala()

            elif opcao == "3":
                self.iniciar_partida()

            elif opcao == "4":
                self.jogar(False)

            elif opcao == "5":
                self.jogar(True)

            elif opcao == "6":
                self.sair_sala()

            elif opcao == "0":
                self.print("Encerrando o cliente.")
                self.encerrando = True
                self.close()
                break

            else:
                self.aviso("Opção inválida.")

            time.sleep(0.2)  # da tempo da resposta aparecer antes do menu

    def ler_numero(self, texto):
        # Devolve o numero digitado, ou None se nao for numero
        try:
            return int(self.ler(texto))
        except ValueError:
            self.print("Número inválido")
            return None

    def escolher_categoria(self):
        self.print("Categorias:")
        self.print(f"  0 - {CATEGORIA_QUALQUER}")
        for i in range(len(self.categorias)):
            self.print(f"  {i + 1} - {self.categorias[i]}")
        numero = self.ler_numero("Categoria: ")
        if numero is None:
            return None
        if numero == 0:
            return CATEGORIA_QUALQUER
        if numero < 1 or numero > len(self.categorias):
            self.print("Categoria inválida")
            return None
        return self.categorias[numero - 1]

    def criar_sala(self):
        nome_sala = self.ler("Nome da sala: ").strip()
        numero_jogadores = self.ler_numero("Máximo de jogadores (2 a 6): ")
        if numero_jogadores is None:
            return
        rodadas = self.ler_numero("Número de rodadas (1 a 5): ")
        if rodadas is None:
            return
        dificuldade = self.ler("Dificuldade (easy, medium, hard): ").strip().lower()
        categoria = self.escolher_categoria()
        if categoria is None:
            return
        self.criacao_pedida = (nome_sala, rodadas, categoria)
        self.enviar(protocol.RoomCreateRequest(numero_jogadores, dificuldade, nome_sala, rodadas, categoria))

    def entrar_sala(self):
        room_id = self.ler("Digite o código da sala: ").strip().upper()
        self.sala_pedida = room_id
        self.enviar(protocol.RoomJoinRequest(room_id))

    def iniciar_partida(self):
        self.enviar(protocol.RoomStartRequest(self.sala_id))

    def sair_sala(self):
        if self.em_partida:
            confirma = self.ler("Partida em andamento. Sair mesmo? Seus pontos serão perdidos. (s/n): ")
            if confirma.strip().lower() != "s":
                return
        self.enviar(protocol.RoomLeaveRequest(self.sala_id))

    def jogar(self, palpite):
        if not self.minha_vez:
            self.aviso(colorir("Não é sua vez. Aguarde o painel mostrar SUA VEZ.", AMARELO))
            return
        if palpite:
            resposta = self.ler("Palpite da palavra: ")
            # Palpite errado custa pontos e um erro: confirma antes de enviar
            confirma = self.ler(f"Confirma o palpite '{resposta.strip()}'? "
                                f"Se errar: -{PENALIDADE_PALPITE} pontos e 1 erro. (s/n): ")
            if confirma.strip().lower() != "s":
                self.aviso("Palpite cancelado. Ainda é a sua vez.")
                return
        else:
            resposta = self.ler("Letra: ")
        self.enviar(protocol.TurnResponseRequest(self.sala_id, palpite, resposta))

    def enviar(self, mensagem):
        # Devolve False se nao conseguiu enviar (servidor caiu)
        try:
            protocol.send_message(self, mensagem)
            return True
        except OSError as e:
            self.perder_conexao(e)
            return False


if __name__ == "__main__":
    # Uso: python3 -m cliente.client [endereco_do_servidor] [porta]
    host = HOST
    porta = PORT
    if len(sys.argv) > 1:
        host = sys.argv[1]
    if len(sys.argv) > 2:
        porta = int(sys.argv[2])

    try:
        username = input("Nome de usuário: ")
        client = Client(host, porta, username)
        client.iniciar()
    except (KeyboardInterrupt, EOFError):
        # Ctrl+C ou Ctrl+D: fecha a conexao, e o servidor trata como desconexao
        print("\nEncerrando o cliente.")
