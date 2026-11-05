"""
Parâmetros da simulação (Fatia 1).

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
TEMP_MAX_REFRIGERADO_C = 5      # acima disto, a ONG recusa um lote refrigerado
LIMITE_FORA_DO_FRIO_MIN = 60    # "limite L" do guia (usado a partir da Fatia 2)

# ---- Cenário da Fatia 1 ----------------------------------------------------
# Um restaurante, um resgatador, uma ONG. Para testar outros tamanhos, basta
# acrescentar entradas nestas listas.

RESTAURANTES = [
    {"nome": "restaurante1", "pos": (2, 3)},
]

RESGATADORES = [
    # velocidade em km por minuto simulado: carro ~30 km/h = 0.5 ; bicicleta ~15 km/h = 0.25
    {"nome": "resgatador1", "pos": (5, 5), "capacidade_kg": 60,
     "caixa_termica": True, "velocidade_km_min": 0.5},
]

ONGS = [
    {"nome": "ong1", "pos": (8, 7), "categorias": {"seco", "refrigerado"},
     "necessidade_kg": 40},
]

# Lotes que o restaurante gera (um de cada vez, com pausa entre eles).
# O terceiro é de propósito uma categoria que a ONG não aceita: mostra o
# caminho "ninguém quer" do protocolo AnunciarOferta.
LOTES = [
    {"categoria": "seco",        "kg": 20, "validade_min": 3 * 24 * 60},
    {"categoria": "refrigerado", "kg": 15, "validade_min": 6 * 60},
    {"categoria": "congelado",   "kg": 10, "validade_min": 7 * 24 * 60},
]
# Com 1 só resgatador, um lote novo enquanto ele ainda está na estrada recebe
# "ocupado" e o restaurante cancela a oferta. Baixem para 1.0 para ver isso.
PAUSA_ENTRE_LOTES_S = 4.0
