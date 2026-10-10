# Food Rescue Descentralizado — SPADE (Tópico K, ISIA 2026/27)

Esqueleto **funcional** do sistema multiagente. Já corre de ponta a ponta:
doadores geram excedentes, negoceiam com recetores e frigoríficos, contratam
voluntários por *Contract Net*, há cancelamentos, realocação, verificação à
entrega, reputação local e métricas por cenário. O trabalho do grupo é
**perceber, melhorar, documentar (Gaia) e avaliar**, não começar do zero.

---

## 1. Como correr (10 minutos)

```powershell
# na pasta do projeto, com o venv do SPADE ativo (o mesmo do hello_agent.py)
.\spade_venv\Scripts\Activate          # ou o caminho do vosso venv
pip install -r requirements.txt
python run.py --scenario S1            # ~35 s; NÃO é preciso "spade run" noutro terminal
python run.py --scenario S3 --seed 7   # outro cenário / seed
python run_all.py                      # S1..S4 x 3 seeds + gráfico (≈ 6–8 min)
```

Resultados em `results/`: `<cenário>_seed<n>_summary.json` (métricas),
`_events.csv` (log de eventos, base para a visualização), `comparison.png` e
`table.csv` (média ± desvio padrão por cenário).

> Windows: se aparecerem erros de SSL/timeouts, `pip uninstall winloop` (está no guia do professor).
> Se a porta 5222 estiver ocupada (ex.: ficou um `spade run` aberto), fechem-no.

---

## 2. SPADE em 5 conceitos, e onde estão no código

| Conceito SPADE | O que é | Onde está |
|---|---|---|
| `Agent` + `setup()` | Um processo autónomo com JID (`donor0@localhost`) | `fr/base.py` → `FRAgent` |
| `CyclicBehaviour` | Ciclo infinito, ex.: "esperar mensagens" | `FRAgent.Inbox` |
| `PeriodicBehaviour` | Corre de X em X segundos | `DonorAgent.Generate`, `FridgeAgent.Maintain`, `RecipientAgent.Consume` |
| `OneShotBehaviour` | Corre uma vez (uma tarefa) | `OfferBehaviour` (1 por item), `RescuerAgent.Job` |
| `Message` + `Template` | Mensagem FIPA (performative, thread, metadata) e filtro que decide que comportamento a recebe | `fr/protocol.py` |

**O truque de encaminhamento** (é o que mais confunde no início): cada mensagem
tem `metadata.dir`. As mensagens `init` (alguém começa ou continua uma conversa)
vão para a **Inbox** do agente. As mensagens `reply` (respostas) vão para o
`OfferBehaviour` daquela conversa, filtradas pelo `thread`.

---

## 3. Arquitetura (o que entra na apresentação)

**Estrutura organizacional (Gaia 2a):** coletivo de pares com mecanismo de
mercado. Não há despachante: **quem tem o alimento negoceia o seu destino**,
e só com os pares dentro do raio (`radius_km`).

```
Doador ──cfp(item)──────────────► Recetores       (offer-cnp)
       ◄─propose{kg,urgência,recebido} | refuse
       ──accept / reject───────►
  [se nenhum recetor] ──request──► Frigorífico     (deposit)  ◄─agree|refuse
Doador ──cfp(item,origem,destino)► Voluntários    (transport-cnp)
       ◄─propose{eta,km,frio} | refuse
       ──accept / reject───────►
Voluntário ──inform(item, checks)─► Recetor/Frigorífico (delivery) → verificação
           ──inform{done} | failure──► Doador   → reputação; se falhar, nova ronda (RF07)
Frigorífico volta a oferecer o stock (reutiliza o mesmo OfferBehaviour)
```

| Ficheiro | Papel Gaia | Requisitos cobertos |
|---|---|---|
| `fr/donor.py` | Doador | RF01 |
| `fr/offer.py` | Protocolos de oferta, depósito e transporte | RF03, RF04, RF05 (parcial), RF07, RF10 |
| `fr/rescuer.py` | Transportador | RF04, cancelamentos e no-show |
| `fr/recipient.py` | Recetor + verificador | RF02, RF08, RF09 |
| `fr/fridge.py` | Armazenamento | RF06, avaria (S3) |
| `fr/world.py` | Modelo de ambiente + métricas | RNF06 |
| `fr/config.py` | Parâmetros e cenários S1–S4 | — |

`Metrics` é instrumentação do experimento, **não é um agente**: nenhum agente o
consulta para decidir. Convém dizê-lo na defesa.

---

## 4. Primeiros resultados (seed 42, 1 corrida, só indicativos)

| | S1 normal | S2 pico+escassez | S3 falhas | S4 pouco fiáveis |
|---|---|---|---|---|
| Taxa de resgate | 0.69 | 0.44 | 0.70 | 0.56 |
| Oferta→entrega (min) | 62 | 99 | 94 | 83 |
| Falhas de transporte | 3 | 5 | 30 | 22 |
| Recuperação após falha | 0.67 | 0.75 | 0.88 | 0.59 |
| Mensagens / entrega | 110 | 527 | 59 | 123 |

Já dá para discutir trade-offs. No S2 o custo de mensagens explode porque os
itens sem par voltam a ser anunciados a cada 15 min. No S3 o sistema é robusto
(88% recuperados), mas mais lento.

---

## 5. O que falta / melhorias (é aqui que está a nota)

Por prioridade:

1. **RF05 explícito:** decidir "direto vs. frigorífico" pelo tempo de vida restante (hoje o frigorífico só serve de último recurso).
2. **Backoff exponencial nas re-ofertas** → baixa as mensagens por entrega no S2 (bom trade-off para o relatório).
3. **Turnos de voluntários com horário** (hoje `on_shift` é fixo para o dia todo).
4. **Reputação melhor:** separar *fiabilidade* (aparece?) de *qualidade* (alimento bom?); partilhar opiniões entre vizinhos (opcional).
5. **Verificar o S3:** o frigorífico 0 avaria ao minuto 200, mas pode estar vazio. Forçar stock ou escolher o mais cheio.
6. **Visualização/demo:** animação matplotlib a partir de `_events.csv` (mapa da grelha + contadores), ou dashboard simples.
7. **Testes** (`pytest`): protocolos com 1 doador + 1 recetor + 1 voluntário; reputação; métricas.
8. *(Opcional)* Um agente em **SPADE-BDI** (ex.: Voluntário com crenças e intenções em AgentSpeak). Valoriza a ligação à matéria, mas só se houver tempo.

---

## 6. Plano até à entrega (19–20 nov)

| Semana | Datas | Documentação (Gaia) | Código |
|---|---|---|---|
| 1 | 9–15 out | Fechar as decisões em aberto; **Análise** (sub-organizações, modelo de ambiente, papéis e interações preliminares, regras organizacionais) | Todos instalam e correm `run.py`; cada um lê o seu ficheiro e muda 1 parâmetro para ver o efeito |
| 2 | 16–22 out | **Design arquitetural** (justificar coletivo de pares + Contract Net) e **design detalhado** (modelo de agentes, serviços; diagramas AUML dos 4 protocolos) | Melhorias 1 e 2 |
| 3 | 23–29 out | Tabela de *failure modes* (falha → deteção → reação) | Melhorias 3, 4 e 5 |
| 4 | 30 out–5 nov | Message schemas finais (a partir de `protocol.py`) | Visualização (6) + testes (7) |
| 5 | 6–12 nov | **Performance report**: S1–S4 × 5 seeds, gráficos, trade-offs, limitações | `run_all.py --seeds 1 2 3 4 5`; congelar código |
| 6 | 13–19 nov | Slides + gravação da demo + ensaio cronometrado | Só correções |

**Divisão sugerida (4 pessoas):**

| Pessoa | Frente | Código | Gaia / documentação |
|---|---|---|---|
| **A — Mercado** | Como as ofertas encontram destino | `donor.py`, `offer.py`; melhorias 1 e 2 | Papéis Doador/Recetor, diagramas AUML dos protocolos offer-cnp e deposit |
| **B — Logística** | Transporte e armazenamento | `rescuer.py`, `fridge.py`; melhorias 3 e 5 | Papéis Voluntário/Frigorífico, protocolo transport-cnp, tabela de *failure modes* |
| **C — Confiança** | Segurança alimentar e reputação | `recipient.py`, reputação em `base.py`; melhoria 4 | Regras organizacionais (liveness/safety), verificação, análise do S4 |
| **D — Avaliação e demo** | Medir e mostrar | `world.py` (métricas), `run_all.py`, `plot_results.py`; melhorias 6 e 7 | Performance report, visualização, montagem final dos slides |

Todos escrevem os modelos Gaia da sua parte. A pessoa D junta tudo no fim.
Para não se pisarem no código, cada um mexe sobretudo nos seus ficheiros e usem Git (GitHub privado).

---

## 7. Resolução de problemas (Windows)

| Sintoma | Causa | Solução |
|---|---|---|
| Não aparece a pasta `results` | Versão antiga do `run.py` | Usar esta versão: grava sempre em `food_rescue/results` e escreve o caminho no fim |
| Corre uma vez e a seguinte falha sem mensagem | Ficou um Python antigo a ocupar a porta 5222 | `taskkill /F /IM python.exe` (fecha TODOS os Python) ou reiniciar o PyCharm; esta versão já não deixa processos órfãos |
| Erro algures | O `spade.run` esconde as exceções | Esta versão mostra-as e grava em `food_rescue/error.log` |
| Erros SSL / timeouts | `winloop` | `pip uninstall winloop` |
| `ModuleNotFoundError: spade` | venv não ativo / interpretador errado no PyCharm | PyCharm → Settings → Python Interpreter → `spade_venv\Scripts\python.exe` |

No PyCharm: botão direito em `run.py` → *Modify Run Configuration* → em *Parameters* pôr `--scenario S1`.
