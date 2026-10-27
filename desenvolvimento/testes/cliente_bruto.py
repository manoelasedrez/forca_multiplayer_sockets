"""
Cliente bruto: envia mensagens fora do protocolo para mostrar como o servidor reage.
Uso (na raiz do repositorio): python3 desenvolvimento/testes/cliente_bruto.py [endereco] [porta]
"""

import socket
import struct
import sys

import caminho_entrega  # noqa: F401 (precisa vir antes do codigo do jogo)

from nacl.encoding import Base64Encoder
from nacl.public import PrivateKey

from protocol import protocol

HOST = "127.0.0.1"
PORT = 38905


def enviar_corpo(sock, corpo):
    # Monta o enquadramento a mao: 4 bytes de tamanho + corpo
    sock.sendall(struct.pack("!I", len(corpo)) + corpo)


def mostrar_resposta(sock):
    try:
        resposta = protocol.receive_message(sock)
        texto = resposta.to_text().strip().replace("\r\n", " | ")
        print("   resposta:", texto)
    except socket.timeout:
        print("   resposta: (nenhuma)")
    except ConnectionError:
        print("   resposta: (o servidor fechou a conexao)")


def caso(titulo, sock, corpo):
    print()
    print(titulo)
    print("   enviado: ", corpo)
    enviar_corpo(sock, corpo)
    mostrar_resposta(sock)


def main():
    host = HOST
    porta = PORT
    if len(sys.argv) > 1:
        host = sys.argv[1]
    if len(sys.argv) > 2:
        porta = int(sys.argv[2])

    sock = socket.create_connection((host, porta))
    sock.settimeout(3)
    chave = PrivateKey.generate().public_key.encode(encoder=Base64Encoder).decode()

    caso("1. Pedido antes do CONNECT", sock,
         b"ROOM JOIN\r\nroom-id: K7XP\r\n")
    caso("2. CONNECT com chave publica invalida", sock,
         b"CONNECT forca1.0\r\npublic-key: nao-e-uma-chave\r\nusername: bruto\r\n")
    caso("3. CONNECT correto", sock,
         ("CONNECT forca1.0\r\npublic-key: " + chave + "\r\nusername: bruto\r\n").encode("utf-8"))
    caso("4. Comando desconhecido", sock,
         b"PULAR VEZ\r\n")
    caso("5. ROOM JOIN sem o atributo room-id", sock,
         b"ROOM JOIN\r\n")
    caso("6. Linha de atributo sem ':'", sock,
         b"ROOM JOIN\r\nroom-id K7XP\r\n")
    caso("7. Numero invalido", sock,
         b"ROOM CREATE\r\nnum-players: dois\r\ndificuldade: easy\r\nroom-name: x\r\nrounds: 1\r\ncategoria: qualquer\r\n")
    caso("8. Corpo que nao e UTF-8", sock,
         b"\xff\xfe\xfd")
    caso("9. Mensagem que so o servidor envia", sock,
         b"ROOM CREATE OK\r\nroom-id: K7XP\r\n")
    caso("10. CONNECT repetido", sock,
         ("CONNECT forca1.0\r\npublic-key: " + chave + "\r\nusername: outro\r\n").encode("utf-8"))
    caso("11. A conexao continua funcionando: pedido valido", sock,
         b"ROOM JOIN\r\nroom-id: ZZZZ\r\n")

    print()
    print("12. Tamanho anunciado de 2 GB (o servidor encerra a conexao)")
    sock.sendall(struct.pack("!I", 2 ** 31) + b"abc")
    mostrar_resposta(sock)
    mostrar_resposta(sock)
    sock.close()


if __name__ == "__main__":
    main()
