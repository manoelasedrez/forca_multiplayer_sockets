import socket
import time
import threading

from nacl.encoding import Base64Encoder
from protocol import protocol
import uuid
from nacl.public import PrivateKey, PublicKey, Box

HOST = "127.0.0.1"
PORT = 38905


class Sala:
    def __init__(self, dono_addr, dificuldade, numero_jogadores):
        self.dono_addr = dono_addr
        self.dificuldade = dificuldade
        self.max_jogadores = numero_jogadores
        self.jogadores = [dono_addr]
        self.num_jogadores = 1
        self.estado = "aguardando"  # ou "em andamento", "finalizada"
        self.id = uuid.uuid4().hex  # Gera um ID único para a sala

    def adicionar_jogador(self, jogador_addr):
        if self.num_jogadores < self.max_jogadores:
            self.jogadores.append(jogador_addr)
            self.num_jogadores += 1
            return True
        return False



class Server(socket.socket):
    def __init__(self, host, port):
        super().__init__(socket.AF_INET, socket.SOCK_STREAM)
        self.host = host
        self.port = port
        self.public_key = None
        self.private_key = None

        self.clientes = {}
        self.sockets = {}

        self.users = {}  # Dicionário para armazenar informações dos usuários conectados

        self.salas = {}
        self.encerrando = False

    def print(self, msg):
        print(msg)

    def iniciar(self):
        try:
            self.bind((self.host, self.port))
        except OSError as e:
            if e.errno == 98:
                self.print(f"Porta {self.port} já está em uso. Tentando outra porta...")
                self.port += 1
                self.iniciar()
            else:
                self.print(f"Erro ao iniciar o servidor: {e} \n Encerrando o servidor.")
                return
        self.print(f"Servidor iniciado em {self.host}:{self.port}")
        self.listen(10)
        self.print("Servidor aguardando conexão...")

        self.private_key = PrivateKey.generate()
        self.public_key = self.private_key.public_key

        threading.Thread(target=self.aceitar_conexao_thread, daemon=True).start()

    def aceitar_conexao_thread(self):
        while True:
            try:
                conn, addr = self.accept()
            except OSError:
                if self.encerrando:
                    break
                raise
            id = f"{addr[0]}:{addr[1]}"
            self.print(f"Cliente conectado: {id}")
            # self.sockets[id] = conn
            self.clientes[id] = {"socket": conn, "addr": addr[0], "port": addr[1], "ip": addr[0]}
            threading.Thread(target=self.handle_cliente, args=(conn, id)).start()

    def fechar(self):
        self.encerrando = True
        for cliente in list(self.clientes.values()):
            try:
                cliente["socket"].shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            cliente["socket"].close()
        self.clientes.clear()
        self.close()

    
    def handle_cliente(self, conn, id):
        while True:
            try:
                mensagem = protocol.receive_message(conn)
                if not mensagem:
                    break
                self.print(f"Recebido de {id}: {mensagem.to_text()}")

            except Exception as e:
                self.print(f"Erro de conexão com {id}: {e}")
                break

            self.handle_mensagem(conn, id, mensagem)

    def handle_mensagem(self, conn, id, mensagem):
        
        if isinstance(mensagem, protocol.ConnectRequest):
            self.users[id] = {
                "name": mensagem.username,
                "public_key": PublicKey(mensagem.public_key, encoder=Base64Encoder)
                }
            chave_texto = self.public_key.encode(encoder=Base64Encoder).decode()
            resposta = protocol.ConnectOk(chave_texto)
            protocol.send_message(conn, resposta)
            self.print(f"Conexão com {id} estabelecida. Usuário: {mensagem.username}")


        if isinstance(mensagem, protocol.RoomCreateRequest):
            sala = self.criar_sala(id, mensagem.dificuldade, mensagem.numero_jogadores)
            self.responder(conn, protocol.RoomCreateOk(sala.id))


        if isinstance(mensagem, protocol.RoomJoinRequest):
            sucesso, users, dificuldade = self.entrar_sala(mensagem.room_id, id)
            if sucesso:
                self.responder(conn, protocol.RoomJoinOk(users, dificuldade))
            else:
                self.responder(conn, protocol.RoomJoinError("Não foi possível entrar na sala."))


    def responder(self, conn, mensagem):
        protocol.send_message(conn, mensagem)

    def criar_sala(self, dono_id, dificuldade, numero_jogadores):
        sala = Sala(dono_id, dificuldade, numero_jogadores)
        self.salas[sala.id] = sala
        return sala

    def get_sala(self, sala_id):
        return self.salas.get(sala_id)

    def entrar_sala(self, sala_id, jogador_id):
        sala = self.get_sala(sala_id)
        if sala:
            return sala.adicionar_jogador(jogador_id), sala.jogadores, sala.dificuldade
        return False, None, None

    def atualizar_sala(self, sala_id):
        sala = self.get_sala(sala_id)
        if sala:
            for jogador_id in sala.jogadores:
                if jogador_id in self.clientes:
                    conn = self.clientes[jogador_id]["socket"]
                    self.responder(conn, protocol.RoomUpdate(sala.jogadores, sala.dificuldade))
        



if __name__ == "__main__":
    server = Server(HOST, PORT)
    server.iniciar()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.print("Encerrando servidor...")
    except Exception as e:
        server.print(f"Erro inesperado: {e}")
    finally:
        server.fechar()

        