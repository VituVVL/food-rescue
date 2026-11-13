"""
Registo de eventos.

Cada agente chama `registar(...)` quando algo relevante acontece. Isto serve a
dois fins:
  1. Ver na consola, em ordem, o que cada agente fez (útil na demo).
  2. Guardar os eventos numa lista para calcular métricas no fim
     (taxa de resgate, tempo até à entrega, ...) a partir da Fatia 4.

IMPORTANTE: isto é instrumentação, NÃO é um agente. Nenhum agente lê esta lista
para tomar decisões; seria uma visão global, que o modelo proíbe.
"""
from __future__ import annotations

import time

EVENTOS: list[dict] = []
_inicio = time.monotonic()


def agora_min() -> float:
    """Relógio simulado: minutos desde o início da corrida (ver ESCALA_S)."""
    from .config import ESCALA_S
    return (time.monotonic() - _inicio) / ESCALA_S


def registar(agente: str, evento: str, lote: str = "", **dados) -> None:
    t = time.monotonic() - _inicio
    EVENTOS.append({"t_s": round(t, 2), "agente": agente, "evento": evento,
                    "lote": lote, **dados})
    detalhe = " ".join(f"{k}={v}" for k, v in dados.items())
    print(f"[{t:6.2f}s] {agente:<13} {evento:<22} {lote:<16} {detalhe}", flush=True)



def resumo(lotes_gerados: list[dict], kg_em_estoque: float = 0.0) -> dict:
    """
    Métricas no fim da corrida. A comida pode chegar a um receptor por dois
    caminhos: direto do restaurante, ou passando pelo armazém. Os kg que entram
    no armazém só contam como resgatados quando saem para um receptor.
    """
    entregas = [e for e in EVENTOS
                if e["evento"] == "lote_entregue" and e.get("resultado") == "confirmada"]
    kg_gerados = sum(l["kg"] for l in lotes_gerados)
    kg_direto = sum(e["kg"] for e in entregas
                    if e["tipo_destino"] == "ong" and not e["lote"].endswith("-A"))
    kg_via_armazem = sum(e["kg"] for e in entregas if e["lote"].endswith("-A"))
    kg_para_armazem = sum(e["kg"] for e in entregas if e["tipo_destino"] == "armazem")
    kg_descartados = sum(e["kg"] for e in EVENTOS if e["evento"] == "lote_descartado")
    kg_receptores = kg_direto + kg_via_armazem

    def taxa(x):
        return round(x / kg_gerados, 2) if kg_gerados else 0

    return {
        "lotes_gerados": len(lotes_gerados),
        "kg_gerados": kg_gerados,
        "kg_direto_receptores": kg_direto,
        "kg_entraram_armazem": kg_para_armazem,
        "kg_armazem_para_receptores": kg_via_armazem,
        "kg_em_estoque_no_fim": round(kg_em_estoque, 2),
        "kg_descartados": kg_descartados,
        "kg_perdidos": round(kg_gerados - kg_direto - kg_para_armazem, 2),
        "taxa_de_resgate": taxa(kg_receptores),        # chegou a quem precisa
        "taxa_entrega_direta": taxa(kg_direto),
    }
