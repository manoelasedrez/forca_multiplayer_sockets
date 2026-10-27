#!/bin/sh
# Gera o pacote de entrega (.tar.gz) com o conteudo da pasta entrega/.
# Uso, na raiz do repositorio:  sh desenvolvimento/empacotar.sh MATRICULA1 MATRICULA2 ...
# Exemplo: sh desenvolvimento/empacotar.sh 171896 39199  ->  171896_39199.tar.gz

set -e

if [ $# -eq 0 ]; then
    echo "Uso: sh desenvolvimento/empacotar.sh MATRICULA1 [MATRICULA2 ...]"
    exit 1
fi

NOME=$(echo "$@" | tr ' ' '_')
RAIZ=$(cd "$(dirname "$0")/.." && pwd)
TEMP=$(mktemp -d)

# Copia a entrega para uma pasta com o nome do pacote, sem arquivos de cache
cp -r "$RAIZ/entrega" "$TEMP/$NOME"
find "$TEMP/$NOME" -name "__pycache__" -type d -prune -exec rm -rf {} +

tar -czf "$RAIZ/$NOME.tar.gz" -C "$TEMP" "$NOME"
rm -rf "$TEMP"

echo "Pacote gerado: $RAIZ/$NOME.tar.gz"
tar -tzf "$RAIZ/$NOME.tar.gz"
