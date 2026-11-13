# v1/src/: implementação do grupo (Fatias 1 a 3)

Implementação do modelo v1 (ver [`../guia_v1.html`](../guia_v1.html)). Cobre:

- **Fatia 1:** AnunciarOferta + ContratarResgate + EntregarLote (restaurante → ONG, com um resgatador).
- **Fatia 2:** armazém passivo. O restaurante oferece primeiro às ONGs e o excedente ao armazém, que aceita conforme o espaço da zona.
- **Fatia 3:** operadores internos ao armazém (receber, controlar, preparar), doca com limite de frio, controlo de validade, e o armazém a voltar a oferecer o estoque às ONGs como doador.

Falta a Fatia 4: imprevistos com nova tentativa (OL2), reputação local e cenários S1–S4.

## Como correr

```powershell
# na pasta raiz do projeto (food-rescue), com o .venv do projeto
.venv\Scripts\python.exe -m v1.src.main
```

No PyCharm: botão direito em `v1/src/main.py` → *Run 'main'*. Não é preciso
`spade run` noutro terminal: o servidor XMPP vem embutido. Demora ~15 s.
Se a porta 5222 estiver ocupada (uma corrida anterior ficou pendurada), fechem
o Python antigo ou reiniciem o PyCharm.

## Ambiente virtual e servidor XMPP (e a justificativa)

**Ambiente virtual.** É necessário: o SPADE (`spade==4.1.4`, ver `pyproject.toml`)
só está instalado no `.venv`. No PyCharm basta o interpretador do projeto apontar
para o `.venv`; com o Python do sistema dá `ModuleNotFoundError: spade`.

**Servidor XMPP.** Os agentes SPADE são clientes XMPP: cada um tem um endereço
(`ong1@localhost`) e as mensagens passam por um servidor. Normalmente esse
servidor corre à parte (por exemplo, com `spade run` noutro terminal). Aqui
usamos o servidor **embutido** do SPADE 4, ligado na última linha de `main.py`:

```python
spade.run(seguro(), embedded_xmpp_server=True)
```

Ele nasce e morre com o programa, e o `start(auto_register=True)` regista cada
agente nele.

**Justificativa (para a defesa).** Continua a ser SPADE e a comunicação continua
real: cada agente é um processo autónomo, as mensagens são FIPA-ACL com
performativas, e viajam por XMPP e não por chamadas de função. A única diferença
é que o servidor vem embutido em vez de instalado à parte. Vantagens: nada para
instalar, cada corrida começa limpa e é reprodutível (RNF06), e é possível
correr várias simulações em sequência. O foco do trabalho é a coordenação entre
agentes, não a infraestrutura.

> ⚠️ Confirmar com o guia do professor se o assignment exige um servidor XMPP
> específico. Se exigir, a troca é pequena: tirar `embedded_xmpp_server=True` em
> `main.py` e apontar os JIDs para o servidor indicado (`DOMINIO` em `config.py`).

## O que acontece

Para cada lote que o restaurante gera:

```
Restaurante ──cfp──────────────► ONGs no raio    (AnunciarOferta)
            ◄─propose{kg} | refuse                cada uma reserva o que propõe
            ──accept / reject──►                  escolhe quem aceita mais kg
Restaurante ──cfp{excedente}───► Armazém          (AnunciarOferta)
            ◄─propose{kg} | refuse                conforme o espaço livre da zona
Restaurante ──cfp──────────────► Resgatadores    (ContratarResgate, um por parte)
            ◄─propose{tempo} | refuse
            ──accept / reject──►                  escolhe o mais rápido
Resgatador  ──inform{lote, temperatura}──► destino (EntregarLote, com inspeção)
            ◄─inform{confirmada | recusada}
Resgatador  ──inform{resultado}──► Restaurante   fecha o Contract Net
```

Dentro do armazém (sem mensagens: os operadores são internos, decisão D7):

```
entrega aceite ─► doca ─► "receber" (op. livre que saiba) ─► zona
                    └─ frio > LIMITE_FORA_DO_FRIO_MIN à espera ─► descartado
a cada CICLO_ESTOQUE_MIN: "controlar" (descarta o que expirou)
                          ─► AnunciarOferta do estoque às ONGs (como doador)
                          ─► "preparar" ─► ContratarResgate (o mesmo código, doador.py)
```

Cenário de demonstração (em `config.py`): 1 restaurante, 2 resgatadores (carro
com caixa térmica e bicicleta sem), 1 ONG, 1 abrigo fora do raio do restaurante,
1 armazém com 2 operadores. Lotes:

- **L1 seco 20 kg:** a ONG fica com tudo.
- **L2 refrigerado 15 kg:** a ONG fica com 10 kg e os 5 kg restantes vão para o armazém. Ninguém os quer depois (fica em estoque até expirar).
- **L3 congelado 10 kg:** a ONG não aceita, vai para o armazém, e o armazém passa-o ao abrigo, que o restaurante não alcança.

O resumo no fim separa o que chegou direto aos receptores, o que passou pelo
armazém, o que ficou em estoque e o que foi descartado ou perdido.

## Ficheiros

| Ficheiro | Papel Gaia | O que tem |
|---|---|---|
| `config.py` | | **Todos os números** (mapa, tempos, raio, armazém, operadores, agentes, lotes) |
| `mensagens.py` | | Como se cria e se lê uma mensagem; templates; esperar respostas com prazo |
| `registo.py` | | Relógio simulado; imprime e guarda os eventos; métricas do resumo. **Não** é um agente |
| `doador.py` | Doador | Código partilhado de AnunciarOferta e ContratarResgate. As decisões estão em `escolher_destino` e `escolher_resgatador` |
| `restaurante.py` | Doador | Gera lotes; ONGs primeiro, excedente ao armazém, um resgatador por parte |
| `armazem.py` | Armazenador + Operador (+ Doador do estoque) | Reserva por zona, inspeciona, operadores internos, controlo de validade, reoferta do estoque |
| `resgatador.py` | Resgatador | Propõe ou recusa transportes; recolhe e entrega |
| `ong.py` | Receptor | Reserva kg ao propor, inspeciona na entrega. Serve para ONGs e abrigos |
| `main.py` | | Cria os agentes (com o que cada um conhece), espera o fim, mostra o resumo |

## SPADE em 4 ideias (o suficiente para ler o código)

1. **Agent**: cada restaurante, ONG e resgatador é um processo autónomo com um endereço (`ong1@localhost`).
2. **Behaviour**: o que o agente faz. `CyclicBehaviour` repete para sempre (a *Inbox* que espera pedidos); `OneShotBehaviour` corre uma vez (a vida de um lote).
3. **Message**: tem uma *performative* FIPA (`cfp`, `propose`, ...) e um corpo JSON.
4. **Template**: filtro que decide que comportamento recebe cada mensagem. Aqui usamos o campo `fase` ("pedido" / "resposta") para a mensagem nunca ir parar a dois comportamentos ao mesmo tempo.

## Limitações conhecidas (o que falta)

- Se o resgatador **desiste ou não aparece**, ou se não há resgatador livre, o doador só cancela e essa parte perde-se. Falta reabrir o `ContratarResgate` (regra OL2). → Fatia 4
- Falta a reputação local (OL3). → Fatia 4
- O restaurante contrata o transporte das partes em sequência (com poucos resgatadores, em paralelo daria `ocupado`).
- Os operadores pegam tarefas por ordem de chegada (não pela mais urgente) e não têm turnos.
- O armazém só volta a oferecer um item quando há novidade (acabou de chegar, sobrou ou falhou). Um item que ninguém quis fica em estoque até expirar.
- Falta o `ConfirmarColeta` (comparar kg e temperatura declarados com os medidos).
- A temperatura é fixa por tipo de veículo e categoria.

## Próxima fatia

4. Imprevistos com nova tentativa (OL2), reputação local (OL3), métricas em ficheiro e cenários S1–S4.
