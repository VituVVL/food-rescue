"""
Parâmetros da simulação (Fatias 1 a 3).

Tudo o que é "número" fica aqui, para que ninguém tenha de caçar valores
espalhados pelo código. Estes valores vêm da tabela de parâmetros do guia
(v1/guia_v1.html, secção "Antes do código"). Mudem à vontade.
"""

DOMINIO = "localhost"      # o servidor XMPP embutido do SPADE usa este domínio
SENHA = "secret"           # senha de todos os agentes (é só uma simulação local)

# ---- Tempo -----------------------------------------------------------------
# 1 minuto simulado = ESCALA_S segundos reais. Com 0.05, uma viagem de 20 min
# simulados demora 1 segundo real.
ESCALA_S = 0.05

# Tempo máximo (em segundos REAIS) que quem lança um pedido espera pelas
# respostas. É o "reply-by" do Contract Net: sem ele, esperaríamos para sempre
# por quem nunca responde.
PRAZO_RESPOSTAS_S = 3.0

# ---- Mapa ------------------------------------------------------------------
# Posições são (x, y) em km numa grelha; a distância é Manhattan.
def distancia(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])

# ---- Segurança alimentar ---------------------------------------------------
TEMP_MAX_REFRIGERADO_C = 5      # acima disto, quem recebe recusa um lote refrigerado
TEMP_MAX_CONGELADO_C = -18      # acima disto, quem recebe recusa um lote congelado
LIMITE_FORA_DO_FRIO_MIN = 60    # "limite L": um lote de frio parado na doca do armazém
                                # mais do que isto estraga e é descartado

# ---- Armazém (Fatia 3) -----------------------------------------------------
# Os operadores não são agentes: são um recurso interno do armazém. Cada tarefa
# ocupa um operador que saiba fazê-la durante estes minutos simulados.
DURACAO_TAREFAS_MIN = {"receber": 10, "controlar": 5, "preparar": 15}
CICLO_ESTOQUE_MIN = 60          # de quanto em quanto tempo o armazém controla e reoferece

# Um restaurante só conhece as ONGs a esta distância (km, Manhattan). O armazém,
# por estar no centro, conhece todas: é por ele que a comida chega às mais longe.
RAIO_DOADOR_KM = 10

# ---- Cenário ----------------------------------------------------------------
# Pequeno de propósito, para ler o log. Para testar outros tamanhos, basta
# acrescentar entradas nestas listas.

RESTAURANTES = [
    {"nome": "restaurante1", "pos": (2, 3)},
]

RESGATADORES = [
    # velocidade em km por minuto simulado: carro ~30 km/h = 0.5 ; bicicleta ~15 km/h = 0.25
    {"nome": "resgatador1", "pos": (5, 5), "capacidade_kg": 60,
     "caixa_termica": True, "velocidade_km_min": 0.5},
    {"nome": "resgatador2", "pos": (4, 7), "capacidade_kg": 15,
     "caixa_termica": False, "velocidade_km_min": 0.25},
]

# ONGs e abrigos são o mesmo agente (papel Receptor) com parâmetros diferentes.
# O abrigo1 fica fora do raio do restaurante: só recebe através do armazém.
ONGS = [
    {"nome": "ong1", "pos": (8, 7), "categorias": {"seco", "refrigerado"},
     "necessidade_kg": 30},
    {"nome": "abrigo1", "pos": (9, 9), "categorias": {"seco", "congelado"},
     "necessidade_kg": 25},
]

ARMAZENS = [
    {"nome": "armazem1", "pos": (6, 6),
     "zonas": {"seco": 500, "refrigerado": 200, "congelado": 100},
     "operadores": [
         {"nome": "op1", "funcoes": {"receber", "controlar"}},
         {"nome": "op2", "funcoes": {"preparar"}},
     ]},
]

# Lotes que o restaurante gera (um de cada vez, com pausa entre eles).
#  L1 seco: a ONG fica com tudo.
#  L2 refrigerado: a ONG só precisa de parte; o resto vai para o armazém.
#  L3 congelado: a ONG não aceita; vai para o armazém, que o passa ao abrigo.
LOTES = [
    {"categoria": "seco",        "kg": 20, "validade_min": 3 * 24 * 60},
    {"categoria": "refrigerado", "kg": 15, "validade_min": 6 * 60},
    {"categoria": "congelado",   "kg": 10, "validade_min": 7 * 24 * 60},
]
# Com poucos resgatadores, um lote novo enquanto eles ainda estão na estrada
# recebe "ocupado". Baixem para 1.0 para ver isso.
PAUSA_ENTRE_LOTES_S = 7.0
