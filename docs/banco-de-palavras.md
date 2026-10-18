# Banco de palavras — Forca Multiplayer

Planejamento do item 7. Complementa as regras de tratamento de letras e palavras de [regras.md](regras.md) (seções 4.1 e 6).

Arquivos relacionados:
- `dados/palavras.json`: o banco inicial (321 palavras, 10 categorias).
- `servidor/banco_palavras.py`: carga, validação e sorteio (rascunho funcional das regras abaixo).
- `servidor/test_banco_palavras.py`: testes automatizados.

## 7.1. Formato do arquivo

**Decisão:** um arquivo JSON em UTF-8, em `dados/palavras.json`, lido com a biblioteca padrão do Python (`json`). Não exige nenhuma dependência externa.

| Formato | A favor | Contra |
| --- | --- | --- |
| TXT (`categoria;palavra`) | Muito simples de editar | Sem lugar para metadados; ambiguidade com `;` e linhas em branco; erros de estrutura são mais difíceis de detectar |
| CSV | Abre em planilha | Problemas de codificação e separador ao salvar em planilhas; acentos corrompidos com frequência |
| **JSON** | Estrutura clara (categoria → lista); metadados de origem; erro de sintaxe é detectado na leitura | Vírgulas e aspas exigem cuidado ao editar à mão |

Estrutura:

```json
{
  "versao": 1,
  "idioma": "pt-BR",
  "descricao": "texto livre",
  "origem": "texto livre (ver 7.8)",
  "categorias": {
    "Frutas": ["maçã", "banana", "pêssego"],
    "Objetos da casa": ["guarda-chuva", "mesa de jantar"]
  }
}
```

- Somente `categorias` é obrigatória; os demais campos são informativos.
- Cada categoria é uma lista de textos. Cada texto é uma resposta.
- As palavras são gravadas com a **grafia correta** (acentos, cedilha, hífens e espaços), em minúsculas ou maiúsculas. O servidor converte para maiúsculas na exibição.
- O nome de uma categoria tem de 1 a 30 caracteres e não pode se repetir no arquivo (nem ao ignorar maiúsculas, minúsculas e acentos).
- Tamanho máximo do arquivo: 1 MB.

Regras de cada resposta (as mesmas de [regras.md](regras.md), 6.4 a 6.6):
- Apenas letras de A a Z, as formas acentuadas e com cedilha previstas (`á à â ã é ê í ó ô õ ú ü ç`), espaço e hífen.
- De 3 a 20 letras, sem contar espaços e hífens, e no máximo 30 caracteres no total.
- Sem hífen no início ou no fim e sem separadores seguidos (`--`, `- `).
- Espaços nas pontas são removidos e sequências de espaços viram um só.
- Números, emojis, pontuação e outras letras (como `ñ`) são recusados.

## 7.2. Categorias

O banco foi dividido em dez categorias de conhecimento geral, para que qualquer jogador consiga participar sem conhecimento especializado:

| Categoria | Palavras |
| --- | ---: |
| Animais | 27 |
| Frutas | 30 |
| Países | 33 |
| Capitais brasileiras | 27 |
| Profissões | 30 |
| Objetos da casa | 35 |
| Esportes | 32 |
| Comidas e bebidas | 35 |
| Corpo humano | 39 |
| Tecnologia | 33 |
| **Total** | **321** |

Critérios usados para escolher e separar as palavras:
- Cada palavra pertence a **uma única** categoria e tem uma única grafia correta.
- Termos de uso corrente em português do Brasil; evitam-se estrangeirismos e siglas.
- A categoria é exibida ao jogador como dica, então a palavra tem de caber claramente nela.
- Categorias novas só entram com pelo menos 5 palavras válidas (ver 7.6).

## 7.3. Quantidade para testar várias partidas

Cada partida usa 5 palavras. O banco entregue tem 321, o que permite dezenas de partidas seguidas com pouca chance de repetir palavras entre elas. Como a repetição só é proibida **dentro da mesma partida**, o mínimo técnico é 5 palavras; para testes, o grupo deve manter pelo menos cerca de 100.

O arquivo foi montado para cobrir os casos especiais das regras:

| Caso | Quantidade | Exemplos |
| --- | ---: | --- |
| Com acento | 85 | LIMÃO, CAFÉ COM LEITE, ÍNDIA |
| Com cedilha | 12 | MAÇÃ, GARÇOM, CORAÇÃO, ENDEREÇO |
| Com hífen | 16 | GUARDA-CHUVA, BEIJA-FLOR, CACHORRO-QUENTE |
| Com espaço | 37 | PÃO DE QUEIJO, RIO DE JANEIRO, MESA DE JANTAR |
| Com letra repetida três vezes ou mais | 58 | BANANA, ABACAXI, MARACUJÁ |
| Menor tamanho (3 letras) | 3 | UVA, RIM, MÃO |
| Maior tamanho (18 letras) | 2 | LEVANTAMENTO DE PESO, SISTEMA OPERACIONAL |

Os limites de 20 letras e de 30 caracteres são cobertos pelos testes automatizados, não pelo arquivo.

## 7.4. Revisão da grafia e das categorias

A revisão acontece em duas camadas.

**Automática** (feita por `banco_palavras.py` a cada carga): caracteres permitidos, tamanhos, separadores, repetição de respostas e estrutura do arquivo. O `palavras.json` entregue passa sem nenhum aviso.

**Manual** (a ser feita pelo grupo antes da entrega): a ferramenta não consegue saber se uma palavra está bem escrita. Passos:
1. Conferir cada palavra no VOLP (Vocabulário Ortográfico da Língua Portuguesa, da Academia Brasileira de Letras): <https://www.academia.org.br/nossa-lingua/busca-no-vocabulario>.
2. Conferir se a palavra pertence mesmo à categoria.
3. Registrar o resultado na tabela abaixo.

Entradas que merecem atenção por causa do Acordo Ortográfico de 1990 ou por hífen/espaço:

| Entrada | Ponto a conferir |
| --- | --- |
| pera | Sem acento depois do Acordo (antes era "pêra") |
| vôlei | Mantém o circunflexo |
| ar-condicionado, guarda-chuva, guarda-roupa, beija-flor, bem-te-vi, cachorro-quente, couve-flor, lava-louças, porta-retrato, saca-rolhas, tatu-bola, água-viva, cavalo-marinho, lobo-guará, onça-pintada, pimenta-do-reino | Hífen mantido |
| pé de moleque, pão de queijo, arroz doce, banco de dados | Escritos sem hífen |
| fibra óptica | "óptica" e "ótica" são aceitas; foi usada "óptica" |
| caratê, paraquedismo, críquete, rúgbi | Variantes e acentuação |

> Observação honesta: não havia dicionário de português disponível no ambiente em que a lista foi gerada. A grafia foi revisada manualmente por quem a escreveu (o Claude), sem consulta ao VOLP. Por isso a conferência do grupo é necessária.

Registro da revisão:

| Categoria | Revisor | Data | Resultado |
| --- | --- | --- | --- |
| Animais | A preencher | A preencher | A preencher |
| Frutas | A preencher | A preencher | A preencher |
| Países | A preencher | A preencher | A preencher |
| Capitais brasileiras | A preencher | A preencher | A preencher |
| Profissões | A preencher | A preencher | A preencher |
| Objetos da casa | A preencher | A preencher | A preencher |
| Esportes | A preencher | A preencher | A preencher |
| Comidas e bebidas | A preencher | A preencher | A preencher |
| Corpo humano | A preencher | A preencher | A preencher |
| Tecnologia | A preencher | A preencher | A preencher |

## 7.5. Palavras repetidas dentro da mesma partida

**Chave de comparação.** Duas entradas são "a mesma resposta" quando têm a mesma forma normalizada (sem acento e cedilha, maiúscula, espaços tratados). Assim MAÇÃ, maca e MACA são a mesma resposta. Hífen e espaço continuam diferentes (`GUARDA-CHUVA` ≠ `GUARDA CHUVA`), como em [regras.md](regras.md) 6.8.

**Na carga do arquivo.** Se a mesma resposta aparece mais de uma vez (na mesma categoria ou em categorias diferentes), vale a primeira ocorrência; as demais são ignoradas com aviso. Depois da carga, cada resposta existe uma única vez no banco.

**Durante a partida.** Ao iniciar uma partida, a sala cria um novo sorteio (`SorteioPartida`) com a lista de palavras livres de cada categoria:

1. Escolhe-se, com igual chance, uma categoria que ainda tenha palavras livres.
2. Escolhe-se, ao acaso, uma palavra livre dessa categoria.
3. A palavra é removida das livres e a chave é anotada em `usadas`.
4. Repete-se a cada rodada (cinco vezes por partida).

Consequências:
- Não há repetição dentro de uma partida, por construção.
- Uma nova partida na mesma sala cria um sorteio novo; palavras de partidas anteriores podem voltar (a regra vale por partida).
- Salas diferentes têm sorteios independentes, então a mesma palavra pode aparecer ao mesmo tempo em salas distintas.
- O estado do sorteio fica na sala, protegido pelo mesmo controle de concorrência que protege as demais informações dela.

## 7.6. Categoria com poucas palavras

| Situação | Comportamento |
| --- | --- |
| Categoria com menos de 5 palavras válidas depois da limpeza | A categoria inteira é **ignorada** na carga, com aviso no log. O servidor continua. |
| Categoria esgotada no meio de uma partida | Não ocorre antes da quinta rodada: toda categoria aceita tem pelo menos 5 palavras. Mesmo assim, o sorteio só considera categorias que ainda tenham palavras livres. |
| Todas as palavras do banco usadas na partida | Não ocorre com 5 rodadas e pelo menos 5 respostas distintas. Se ocorrer por defeito, o servidor não inicia a partida, registra o erro e avisa a sala; o servidor não cai. |
| Menos de 5 respostas distintas no banco inteiro | Erro fatal: o servidor se recusa a iniciar (ver 7.7). |

O mínimo de 5 por categoria foi escolhido para que qualquer categoria sozinha consiga sustentar uma partida completa. Isso deixa aberta, sem retrabalho, a evolução futura de permitir que a sala escolha a categoria.

## 7.7. Arquivo ausente ou inválido

O arquivo é lido **uma vez**, ao iniciar o servidor. Alterações exigem reiniciar o servidor, e partidas em andamento não são afetadas (os dados já estão em memória).

Caminho padrão: `dados/palavras.json`, calculado a partir da pasta do projeto (não do diretório em que o comando foi executado). Poderá ser trocado por um argumento de linha de comando (por exemplo `--palavras CAMINHO`) a ser definido na implementação do servidor.

| Situação | Comportamento |
| --- | --- |
| Arquivo inexistente, ilegível ou é uma pasta | **Fatal.** Mensagem clara em `stderr`, código de saída 1; o servidor não abre a porta. |
| Arquivo maior que 1 MB | **Fatal.** |
| Não está em UTF-8 | **Fatal.** (Um BOM no início é tolerado.) |
| JSON mal formado, vazio, ou estrutura diferente da esperada | **Fatal**, com a mensagem de erro do analisador. |
| Categoria repetida no arquivo (chave duplicada no JSON) | **Fatal**, pois o JSON comum perderia uma delas sem avisar. |
| Palavra inválida (caracteres, tamanho, separadores, tipo errado) | Palavra ignorada, com aviso que indica categoria, posição e motivo. |
| Palavra repetida | Ignorada, com aviso (ver 7.5). |
| Categoria com menos de 5 palavras válidas, nome vazio/longo/repetido ou valor que não é lista | Categoria ignorada, com aviso. |
| Menos de 5 respostas distintas utilizáveis no total | **Fatal.** |

Decisão: **não há banco embutido de reserva.** Um padrão escondido mascararia o erro e poderia causar surpresas na demonstração. É melhor o servidor falhar na partida do processo, com mensagem clara.

Conferência antes de apresentar:

```
python servidor/banco_palavras.py dados/palavras.json
python servidor/banco_palavras.py dados/palavras.json --simular 1000
```

## 7.8. Origem das palavras e materiais externos

| Item | Origem |
| --- | --- |
| Palavras e categorias de `dados/palavras.json` | Lista autoral elaborada com apoio do **Claude (IA, da Anthropic)** em 18/10/2026, a partir de conhecimento geral. |
| Cópia de terceiros | **Nenhuma.** Nenhuma palavra foi copiada de dicionário, site, lista, banco de dados ou material de outro grupo. |
| Nomes de países e capitais | Informação geográfica de conhecimento público. |
| Referência para a grafia | O VOLP/ABL é a referência a ser usada na revisão (7.4). Até o registro da revisão, a consulta ainda não foi feita. |
| Ferramentas de apoio | Somente a biblioteca padrão do Python 3 (`json`, `unicodedata`, `re`, `random`, `unittest`). |

Os mesmos dados constam no campo `origem` do arquivo JSON. Sempre que o grupo incluir palavras de outra fonte, deve atualizar esta tabela e o campo `origem`. A declaração de uso de IA do `README.md` deve refletir esse uso.

## Testes planejados

Todos automatizados em `servidor/test_banco_palavras.py` (`python -m unittest discover -s servidor -v`):

| Cenário | Seção |
| --- | --- |
| `maçã`, `MAÇÃ` e `maca` geram a mesma chave; `guarda chuva` ≠ `guarda-chuva` | 7.5 |
| Letras acentuadas decompostas (c + cedilha) equivalem às compostas | 7.1 |
| Palavras válidas e inválidas (vazia, 2 letras, 21 letras, número, `!`, `ñ`, emoji, hífen nas pontas, separadores seguidos, 39 caracteres) | 7.1 |
| Arquivo ausente, pasta no lugar do arquivo, vazio, JSON inválido, não UTF-8, estrutura errada, categoria duplicada | 7.7 |
| Categoria curta ignorada com aviso; palavras inválidas ignoradas; resposta repetida entre categorias contada uma vez | 7.5, 7.6 |
| Banco com menos de 5 respostas é fatal | 7.6, 7.7 |
| 500 partidas sem repetição; banco mínimo de 5 palavras usa todas e depois esgota | 7.5, 7.6 |
| Partidas diferentes não compartilham estado | 7.5 |
| `palavras.json` carrega sem avisos, com pelo menos 10 categorias de 20 palavras ou mais | 7.2, 7.3 |
