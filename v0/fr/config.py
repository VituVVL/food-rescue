"""
Parâmetros da simulação e definição dos cenários de teste (S1–S4).

Unidades: tempo em MINUTOS SIMULADOS, distâncias em km (grelha de 10x10 km,
distância Manhattan), massa em kg.
"""
from dataclasses import dataclass, field, replace


@dataclass
class Config:
    name: str = "S1"
    seed: int = 42

    # --- tempo -----------------------------------------------------------
    real_sec_per_sim_min: float = 0.05   # 1 min simulado = 0.05 s reais
    duration_min: int = 480              # duração do dia simulado (8 h)
    drain_min: int = 120                 # tempo extra para terminar entregas em curso

    # --- espaço / descoberta ---------------------------------------------
    grid_km: int = 10
    radius_km: float = 7.0               # vizinhança: cada agente só conhece pares neste raio

    # --- população ---------------------------------------------------------
    n_donors: int = 10
    n_rescuers: int = 15
    n_fridges: int = 3
    n_recipients: int = 8

    # --- doadores ----------------------------------------------------------
    gen_every_min: int = 20              # de quanto em quanto tempo o doador "olha" para o stock
    p_surplus: float = 0.35              # prob. de haver excedente em cada verificação
    peak_after_min: int = 360            # a partir daqui (fecho das lojas) há pico
    peak_multiplier: float = 1.0         # >1 aumenta a probabilidade no pico
    kg_range: tuple = (3, 25)
    p_bad_label: float = 0.0             # S4: rotulagem errada (alimento impróprio)

    # --- voluntários -------------------------------------------------------
    p_cancel: float = 0.05               # desiste depois de aceitar (avisa com FAILURE)
    p_noshow: float = 0.0                # S4: aceita e simplesmente não aparece (silêncio)
    frac_unreliable: float = 0.0         # fração de voluntários a que se aplica p_noshow
    frac_cold_vehicles: float = 0.3
    frac_on_shift: float = 1.0           # S2: menos voluntários disponíveis

    # --- segurança alimentar ----------------------------------------------
    cold_max_out_min: int = 60           # tempo máximo fora do frio para refrigerados
    shelf_life_min: dict = field(default_factory=lambda: {
        "ambient": (360, 900),           # pão, enlatados
        "chilled": (150, 360),           # pratos prontos, lacticínios
    })
    p_chilled: float = 0.5

    # --- frigoríficos ------------------------------------------------------
    fridge_capacity_kg: float = 60.0
    fridge_fail_at_min: int | None = None   # S3: um frigorífico avaria neste instante
    fridge_reoffer_every_min: int = 30

    # --- rede / protocolo --------------------------------------------------
    msg_loss: float = 0.0                # prob. de perder cada mensagem
    bid_window_s: float = 0.6            # tempo real de espera por propostas (CNP)
    retry_every_min: int = 15
    max_transport_attempts: int = 4

    # --- recetores ---------------------------------------------------------
    need_range_kg: tuple = (30, 80)
    need_regen: float = 0.15             # fração da necessidade máxima renovada por hora


BASE = Config()

SCENARIOS = {
    # Linha de base: oferta e voluntários equilibrados
    "S1": replace(BASE, name="S1"),
    # Pico ao fim do dia + poucos voluntários disponíveis
    "S2": replace(BASE, name="S2", p_surplus=0.25, peak_multiplier=3.0,
                  frac_on_shift=0.4),
    # Falhas em cascata: 30% cancelamentos, frigorífico avaria, perda de mensagens
    "S3": replace(BASE, name="S3", p_cancel=0.30, fridge_fail_at_min=200,
                  msg_loss=0.05),
    # Participantes pouco fiáveis (testa a reputação)
    "S4": replace(BASE, name="S4", p_bad_label=0.25, frac_unreliable=0.3,
                  p_noshow=0.6),
}
