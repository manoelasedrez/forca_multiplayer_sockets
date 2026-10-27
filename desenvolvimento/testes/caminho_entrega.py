"""
Coloca a pasta entrega/ no caminho de importacao do Python, para que os testes
encontrem o codigo do jogo (protocol, servidor, cliente) sem copia-lo para ca.
Basta importar este modulo antes do codigo do jogo.
"""

import os
import sys

PASTA_ENTREGA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "entrega")
sys.path.insert(0, os.path.normpath(PASTA_ENTREGA))
