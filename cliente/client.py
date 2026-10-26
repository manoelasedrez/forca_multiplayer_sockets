import socket
import threading
import time
from protocol import protocol
from nacl.public import PrivateKey, PublicKey
from nacl.encoding import Base64Encoder

HOST = "127.0.0.1"
PORT = 38906


class Client(socket.socket):
    def __init__(self, host, port, username):
        super().__init__(socket.AF_INET, socket.SOCK_STREAM)
        self.host = host
        self.port = port
        self.username = username
        self.public_key = None
        self.private_key = None

        self.server_public_key = None  # Chave publica recebida do servidor

        self.sala_id = None  # Id da sala criada

    def print(self, msg):
        print(msg)

    def iniciar(self):
        try:
            self.connect((self.host, self.port))
        except OSError as e:
            self.print(f"Erro ao conectar no servidor: {e}")
            self.connect((self.host, self.port + 1))  # Tenta conectar na próxima porta
            return
        self.print(f"Conectado ao servidor em {self.host}:{self.port}")

        self.private_key = PrivateKey.generate()
        self.public_key = self.private_key.public_key

        if not self.conectar():
            self.close()
            return

        threading.Thread(target=self.receber_mensagens_thread, daemon=True).start()
        self.menu()

    def conectar(self):
        # Envia o CONNECT e espera a resposta do servidor
        chave_texto = self.public_key.encode(encoder=Base64Encoder).decode()
        self.enviar(protocol.ConnectRequest(chave_texto, self.username))
        
        try:
            resposta = protocol.receive_message(self)
        except Exception as e:
            self.print(f"Erro de conexão com o servidor: {e}")
            return False

        if isinstance(resposta, protocol.ConnectOk):
            self.server_public_key = PublicKey(resposta.public_key, encoder=Base64Encoder)
            self.print("Conexão com o servidor estabelecida")
            return True

        if isinstance(resposta, protocol.ConnectError):
            self.print(f"Servidor recusou a conexão: {resposta.data}")
            return False

        self.print(f"Resposta inesperada do servidor: {resposta}")
        return False

    def receber_mensagens_thread(self):
        while True:
            try:
                mensagem = protocol.receive_message(self)
                if not mensagem:
                    break
                self.print(f"Recebido do servidor: {mensagem.to_text()}")

            except Exception as e:
                self.print(f"Erro de conexão com o servidor: {e}")
                break

            self.handle_mensagem(mensagem)

    def handle_mensagem(self, mensagem):
        if isinstance(mensagem, protocol.RoomCreateOk):
            self.sala_id = mensagem.room_id
            self.print(f"Sala criada com sucesso! Id da sala: {self.sala_id}")

        if isinstance(mensagem, protocol.ErrorMessage):
            self.print(f"Erro do servidor: {mensagem.error}")

    def menu(self):
        while True:
            self.print("\n1 - Criar sala")
            self.print("0 - Sair")
            opcao = input("Escolha uma opção: ")

            if opcao == "1":
                numero_jogadores = int(input("Número de jogadores: "))
                dificuldade = input("Dificuldade: ")
                self.criar_sala(dificuldade, numero_jogadores)

            elif opcao == "0":
                self.print("Encerrando o cliente.")
                self.close()
                break

            elif opcao == "2":
                self.entrar_sala()

            else:
                self.print("Opção inválida")

    def criar_sala(self, dificuldade, numero_jogadores):
        self.enviar(protocol.RoomCreateRequest(numero_jogadores, dificuldade))

    def entrar_sala(self):
        room_id = input("Digite o ID da sala que deseja entrar: ")
        self.enviar(protocol.RoomJoinRequest(room_id))

    def enviar(self, mensagem):
        protocol.send_message(self, mensagem)


if __name__ == "__main__":
    username = input("Nome de usuário: ")
    client = Client(HOST, PORT, username)
    client.iniciar()

    comandos = """
    Comandos disponíveis:
    iniciar <username> - Iniciar o jogo
    criar_sala <dificuldade> <numero_jogadores> - Criar sala
    sair - Encerrar o cliente
    """
