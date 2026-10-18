# Forca Multiplayer

Jogo de forca competitivo em rede, com dois a seis jogadores por sala, pontuação e partidas de cinco rodadas. O mesmo jogador poderá participar de várias salas simultaneamente usando uma única conexão.

## Situação do projeto

Planejamento inicial. Este pacote contém a estrutura e as regras propostas. Ainda não há código executável de cliente ou servidor.

## Integrantes

| Nome | Matrícula |
| --- | --- |
| Manoela Rodrigues Sedrez | 171896 |
| A preencher | A preencher |

## Tecnologias previstas

- Python 3 (versão exata a definir e registrar quando o desenvolvimento começar).
- Biblioteca nativa `socket` para comunicação.
- TCP e arquitetura cliente-servidor.
- Interface no terminal.
- Mecanismo de concorrência ou multiplexação a definir antes da implementação.
- Nenhuma biblioteca externa definida nesta etapa.

O servidor centralizará palavras secretas, salas, turnos, validação, pontuação e resultados. A escolha de TCP considera a necessidade de entrega confiável e ordenada das mensagens. O protocolo próprio deverá definir os limites das mensagens, pois TCP transmite um fluxo de bytes.

## Estrutura

- `cliente/`: interface e comunicação do jogador.
- `servidor/`: conexões, salas e gerenciamento de partidas.
- `dados/`: futuro arquivo de palavras e categorias.
- `docs/regras.md`: proposta, escopo e regras iniciais.

Os arquivos `.gitkeep` apenas permitem registrar as pastas ainda vazias no Git e poderão ser removidos quando elas tiverem conteúdo.

## Regras e funcionalidades

Consulte [a proposta e as regras](docs/regras.md). As decisões são uma base para revisão pelo grupo antes da implementação.

## Execução, dependências e testes

Ainda não existem comandos de execução ou testes, pois a aplicação não foi implementada. Atualizar esta seção com a versão do Python, dependências, comandos para servidor e cliente, endereços e portas, instruções para rede local e cenários de teste conforme o desenvolvimento avançar.

## Próxima etapa

Definir o protocolo e o mecanismo de concorrência. Em seguida, implementar uma conexão básica cliente-servidor com envio e recebimento de uma mensagem, antes de avançar para vários clientes e identificação por apelido.

## Documentação pendente

Criar a especificação detalhada do protocolo, incluindo formato e delimitação de mensagens, atributos, requisições, respostas, eventos, sequências de interação e tratamento de erros.

## Uso de Inteligência Artificial

O ChatGPT foi utilizado para discutir a aplicação, organizar o plano de desenvolvimento, propor regras e preparar esta documentação e estrutura inicial. Nenhum código de funcionamento do jogo foi produzido neste pacote. Esta declaração deverá ser atualizada para refletir os usos reais durante o projeto.
