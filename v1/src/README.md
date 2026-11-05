# v1/src/: implementação do grupo (Fatia 1)

Esqueleto funcional do modelo v1 (ver [`../guia_v1.html`](../guia_v1.html)).
Cobre o núcleo: **AnunciarOferta + ContratarResgate + EntregarLote**, com um
restaurante, um resgatador e uma ONG. O armazém e os operadores entram nas
Fatias 2 e 3.

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
Restaurante ──cfp──────────────► ONGs            (AnunciarOferta)
            ◄─propose{kg} | refuse
            ──accept / reject──►                  escolhe quem aceita mais kg
Restaurante ──cfp──────────────► Resgatadores    (ContratarResgate, Contract Net)
            ◄─propose{tempo} | refuse
            ──accept / reject──►                  escolhe o mais rápido
Resgatador  ──inform{lote, temperatura}──► ONG   (EntregarLote)
            ◄─inform{confirmada | recusada}
Resgatador  ──inform{resultado}──► Restaurante   fecha o Contract Net
```

Três lotes de demonstração (em `config.py`): um seco e um refrigerado que
chegam ao fim, e um congelado que a ONG não quer (caminho "sem destino").

## Ficheiros

| Ficheiro | Papel Gaia | O que tem |
|---|---|---|
| `config.py` | | **Todos os números** (mapa, tempos, quantos agentes, lotes) |
| `mensagens.py` | | Como se cria e se lê uma mensagem; templates; esperar respostas com prazo |
| `registo.py` | | Imprime e guarda os eventos (base das métricas); **não** é um agente |
| `restaurante.py` | Doador | Gera lotes e conduz AnunciarOferta e ContratarResgate. As decisões estão em `escolher_destino` e `escolher_resgatador` |
| `resgatador.py` | Resgatador | Propõe ou recusa transportes; recolhe e entrega |
| `ong.py` | Receptor | Reserva kg ao propor, inspeciona na entrega |
| `main.py` | | Cria os agentes, espera o fim, mostra o resumo |

## SPADE em 4 ideias (o suficiente para ler o código)

1. **Agent**: cada restaurante, ONG e resgatador é um processo autónomo com um endereço (`ong1@localhost`).
2. **Behaviour**: o que o agente faz. `CyclicBehaviour` repete para sempre (a *Inbox* que espera pedidos); `OneShotBehaviour` corre uma vez (a vida de um lote).
3. **Message**: tem uma *performative* FIPA (`cfp`, `propose`, ...) e um corpo JSON.
4. **Template**: filtro que decide que comportamento recebe cada mensagem. Aqui usamos o campo `fase` ("pedido" / "resposta") para a mensagem nunca ir parar a dois comportamentos ao mesmo tempo.

## Limitações conhecidas da Fatia 1 (o que falta)

- Se o resgatador **desiste ou não aparece**, o restaurante só cancela. Falta reabrir o `ContratarResgate` (regra OL2). → Fatia 4
- Falta o `ConfirmarColeta` (comparar kg e temperatura declarados com os medidos).
- O resgatador responde `ocupado` em vez de reservar-se entre o *propose* e o *accept*.
- A cadeia de frio ainda só é verificada na entrega (a temperatura é fixa por tipo de veículo).
- Sem armazém, operadores, falhas aleatórias, métricas em ficheiro e cenários S1–S4.
- Um só restaurante: com vários, cada um deve conhecer só as ONGs e resgatadores do seu raio (ver `main.py`).

## Próximas fatias

2. `armazem.py`: responde às ofertas conforme a capacidade da zona; recebe lotes.
3. `operador.py` + quadro de tarefas; o armazém passa a ter tempo de processamento e volta a oferecer o estoque.
4. Imprevistos, métricas em CSV/JSON e cenários S1–S4.
