# Forca Multiplayer — guia rápido
<img width="900" height="600" alt="image" src="https://github.com/user-attachments/assets/d263ea46-0725-4bc6-84ff-a94db014c4d1" />

Jogo de forca em rede (cliente-servidor, TCP, Python), com as mensagens cifradas por chaves públicas e privadas (PyNaCl). Este arquivo é só para quem clonou o repositório e quer rodar o jogo rápido.

> A documentação oficial do trabalho, que vai para o professor, é o [entrega/README.md](entrega/README.md).

## Organização do repositório

| Pasta | Conteúdo | Vai na entrega? |
| --- | --- | --- |
| `entrega/` | Código do jogo, README oficial, especificação do protocolo e regras | **Sim** |
| `desenvolvimento/` | Testes automatizados, roteiro de demonstração, pendências e script de empacotamento | Não |

## 1. Preparar (uma vez)

Requisitos: **Python 3.10 ou mais recente** e o Git.

```
git clone https://github.com/manoelasedrez/forca_multiplayer_sockets.git
cd forca_multiplayer_sockets
```

Crie um ambiente virtual e instale a única dependência, o PyNaCl:

**Linux / macOS**

```
python3 -m venv .venv
source .venv/bin/activate
pip install pynacl
```

**Windows (PowerShell)**

```
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install pynacl
```

Nas próximas vezes, basta ativar o ambiente (`source .venv/bin/activate` ou `.venv\Scripts\Activate.ps1`). No Windows, troque `python3` por `py` nos comandos abaixo.

## 2. Rodar o jogo

O jogo roda **de dentro da pasta `entrega/`**. Abra um terminal para o servidor e um para cada jogador.

**Terminal 1: servidor**

```
cd entrega
python3 -m servidor.server
```

**Terminais 2, 3...: um cliente por jogador**

```
cd entrega
python3 -m cliente.client
```

Para jogar sozinho, abra dois clientes no mesmo computador e jogue com os dois.

## 3. Jogar uma partida

1. Em cada cliente, digite um apelido diferente.
2. No primeiro cliente: **1 - Criar sala**. Responda nome, máximo de jogadores, rodadas, dificuldade e categoria. Anote o **código** da sala (ex.: `K7XP`).
3. Nos outros clientes: **2 - Entrar em sala** e digite o código.
4. No cliente de quem criou a sala: **3 - Iniciar partida** (precisa de pelo menos 2 jogadores).
5. Quando o painel mostrar **SUA VEZ**, use **4** para tentar uma letra ou **5** para chutar a palavra.

Pontuação: letra certa vale +1 por ocorrência, palavra certa vale +5 e palavra errada tira 2. Regras completas em [entrega/regras.md](entrega/regras.md).

## 4. Jogar em computadores diferentes (mesma rede)

1. Na máquina do servidor, descubra o IP: `ip addr` (Linux), `ipconfig` (Windows) ou `ifconfig` (macOS). Exemplo: `192.168.0.10`.
2. Libere a porta TCP **38905** no firewall dessa máquina.
3. Nos outros computadores, passe o IP para o cliente:

   ```
   cd entrega
   python3 -m cliente.client 192.168.0.10
   ```

Para usar outra porta: `python3 -m servidor.server 40000` e `python3 -m cliente.client 192.168.0.10 40000`.

## 5. Rodar os testes

Na **raiz do repositório** (não dentro de `entrega/`):

```
python3 -m unittest discover desenvolvimento/testes
```

Devem passar 61 testes. Os avisos "Palavra ignorada" que aparecem são esperados.

Para ver como o servidor reage a mensagens fora do protocolo (com o servidor rodando):

```
python3 desenvolvimento/testes/cliente_bruto.py
```

## Problemas comuns

| Problema | Solução |
| --- | --- |
| `ModuleNotFoundError: No module named 'protocol'` (ou `servidor`, `cliente`) | Rode o servidor e o cliente de dentro da pasta `entrega/`, com `python3 -m ...` |
| `ModuleNotFoundError: No module named 'nacl'` | Ative o ambiente virtual e rode `pip install pynacl` |
| `error: externally-managed-environment` no `pip install` | Use o ambiente virtual do passo 1 |
| "versao nao suportada, use forca1.1" ao conectar | Cliente e servidor de versões diferentes: rode `git pull` para os dois usarem o mesmo código |
| `Connection refused` no cliente | O servidor não está rodando, ou o IP/porta estão errados |
| Funciona na mesma máquina, mas não pela rede | Libere a porta 38905 no firewall do servidor e confira se as máquinas estão na mesma rede |
| Símbolos estranhos (`[32m`, `[2J`) no terminal | O terminal não suporta cores ANSI: use o Windows Terminal, ou mude `USAR_CORES` e `LIMPAR_TELA` para `False` em `entrega/cliente/client.py` |
| "Porta 38905 já está em uso" | Já existe um servidor rodando; o novo usa a porta seguinte (38906), que deve ser passada ao cliente |

## Mais informações

| Documento | Para quê |
| --- | --- |
| [entrega/README.md](entrega/README.md) | Documentação oficial: arquitetura, TCP, concorrência, bibliotecas |
| [entrega/protocolo.md](entrega/protocolo.md) | Especificação do protocolo |
| [entrega/regras.md](entrega/regras.md) | Regras do jogo |
| [desenvolvimento/demonstracao.md](desenvolvimento/demonstracao.md) | Roteiro para a apresentação |
| [desenvolvimento/pendencias.md](desenvolvimento/pendencias.md) | O que ainda está em aberto |

Para gerar o pacote de entrega: `sh desenvolvimento/empacotar.sh MATRICULA1 MATRICULA2`.
