"""
Cliente bruto: envia mensagens fora do protocolo para mostrar como o servidor reage.
Uso (na raiz do repositorio): python3 desenvolvimento/testes/cliente_bruto.py [endereco] [porta]

Depois do CONNECT aceito, o cliente bruto cifra os corpos com a Box da conexao (como o
cliente normal), para que o servidor consiga decifra-los e avaliar o conteudo.
"""

import socket
import struct
import sys

import caminho_entrega  # noqa: F401 (precisa vir antes do codigo do jogo)

from nacl.encoding import Base64Encoder
from nacl.public import Box, PrivateKey, PublicKey

from protocol import protocol

HOST = "127.0.0.1"
PORT = 38905


def enviar_corpo(sock, corpo, box=None):
    # Monta o enquadramento a mao: 4 bytes de tamanho + corpo (cifrado, se houver box)
    if box is not None:
        corpo = protocol.cifrar(corpo, box)
    sock.sendall(struct.pack("!I", len(corpo)) + corpo)


def mostrar_resposta(sock, box=None):
    try:
        resposta = protocol.receive_message(sock, box)
        texto = resposta.to_text().strip().replace("\r\n", " | ")
        print("   resposta:", texto)
        return resposta
    except socket.timeout:
        print("   resposta: (nenhuma)")
    except ConnectionError:
        print("   resposta: (o servidor fechou a conexao)")
    return None


def caso(titulo, sock, corpo, box=None, cifrar=True):
    print()
    print(titulo)
    print("   enviado: ", corpo, "(cifrado)" if box is not None and cifrar else "(texto puro)")
    if cifrar:
        enviar_corpo(sock, corpo, box)
    else:
        enviar_corpo(sock, corpo)
    return mostrar_resposta(sock, box)


def main():
    host = HOST
    porta = PORT
    if len(sys.argv) > 1:
        host = sys.argv[1]
    if len(sys.argv) > 2:
        porta = int(sys.argv[2])

    sock = socket.create_connection((host, porta))
    sock.settimeout(3)
    minha_chave = PrivateKey.generate()
    chave = minha_chave.public_key.encode(encoder=Base64Encoder).decode()
    versao = protocol.VERSION

    # --- Antes do CONNECT: tudo em texto puro ---
    caso("1. Pedido antes do CONNECT", sock,
         b"ROOM JOIN\r\nroom-id: K7XP\r\n")
    caso("2. CONNECT com versao antiga (forca1.0, sem cifragem)", sock,
         ("CONNECT forca1.0\r\npublic-key: " + chave + "\r\nusername: bruto\r\n").encode("utf-8"))
    caso("3. CONNECT com chave publica invalida", sock,
         ("CONNECT " + versao + "\r\npublic-key: nao-e-uma-chave\r\nusername: bruto\r\n").encode("utf-8"))
    resposta = caso("4. CONNECT correto", sock,
                    ("CONNECT " + versao + "\r\npublic-key: " + chave + "\r\nusername: bruto\r\n").encode("utf-8"))
    if not isinstance(resposta, protocol.ConnectOk):
        print("\nO servidor nao aceitou o CONNECT; encerrando.")
        return

    # --- Depois do CONNECT: corpos cifrados com a Box da conexao ---
    chave_servidor = PublicKey(resposta.public_key, encoder=Base64Encoder)
    box = Box(minha_chave, chave_servidor)

    caso("5. Pedido valido, mas enviado sem cifrar", sock,
         b"ROOM JOIN\r\nroom-id: ZZZZ\r\n", box, cifrar=False)
    print()
    print("6. Pedido cifrado com a chave de outra pessoa")
    intruso = Box(PrivateKey.generate(), chave_servidor)
    enviar_corpo(sock, b"ROOM JOIN\r\nroom-id: ZZZZ\r\n", intruso)
    mostrar_resposta(sock, box)
    print()
    print("7. Pedido cifrado e adulterado no caminho (um bit trocado)")
    cifrado = protocol.cifrar(b"ROOM JOIN\r\nroom-id: ZZZZ\r\n", box)
    cifrado = cifrado[:-1] + bytes([cifrado[-1] ^ 1])
    sock.sendall(struct.pack("!I", len(cifrado)) + cifrado)
    mostrar_resposta(sock, box)

    caso("8. Comando desconhecido", sock, b"PULAR VEZ\r\n", box)
    caso("9. ROOM JOIN sem o atributo room-id", sock, b"ROOM JOIN\r\n", box)
    caso("10. Linha de atributo sem ':'", sock, b"ROOM JOIN\r\nroom-id K7XP\r\n", box)
    caso("11. Numero invalido", sock,
         b"ROOM CREATE\r\nnum-players: dois\r\ndificuldade: easy\r\nroom-name: x\r\nrounds: 1\r\ncategoria: qualquer\r\n", box)
    caso("12. Corpo que nao e UTF-8", sock, b"\xff\xfe\xfd", box)
    caso("13. Mensagem que so o servidor envia", sock, b"ROOM CREATE OK\r\nroom-id: K7XP\r\n", box)
    caso("14. CONNECT repetido", sock,
         ("CONNECT " + versao + "\r\npublic-key: " + chave + "\r\nusername: outro\r\n").encode("utf-8"), box)
    caso("15. A conexao continua funcionando: pedido valido", sock, b"ROOM JOIN\r\nroom-id: ZZZZ\r\n", box)

    print()
    print("16. Tamanho anunciado de 2 GB (o servidor encerra a conexao)")
    sock.sendall(struct.pack("!I", 2 ** 31) + b"abc")
    mostrar_resposta(sock, box)
    mostrar_resposta(sock, box)
    sock.close()


if __name__ == "__main__":
    main()
