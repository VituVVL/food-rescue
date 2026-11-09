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


def registar(agente: str, evento: str, lote: str = "", **dados) -> None:
    t = time.monotonic() - _inicio
    EVENTOS.append({"t_s": round(t, 2), "agente": agente, "evento": evento,
                    "lote": lote, **dados})
    detalhe = " ".join(f"{k}={v}" for k, v in dados.items())
    print(f"[{t:6.2f}s] {agente:<13} {evento:<22} {lote:<16} {detalhe}", flush=True)



def resumo(lotes_gerados: list[dict]) -> dict:
    """Distingue entregas a ONGs de lotes guardados em armazém."""

    entregas = [
        e for e in EVENTOS
        if e["evento"] == "lote_entregue"
        and e.get("resultado") == "confirmada"
    ]

    kg_gerados = sum(l["kg"] for l in lotes_gerados)
    kg_ongs = sum(
        e["kg"] for e in entregas if e.get("tipo_destino") == "ong"
    )
    kg_armazens = sum(
        e["kg"] for e in entregas if e.get("tipo_destino") == "armazem"
    )
    kg_entregues = kg_ongs + kg_armazens

    return {
        "lotes_gerados": len(lotes_gerados),
        "lotes_entregues": len({e["lote"] for e in entregas}),
        "entregas_confirmadas": len(entregas),
        "kg_gerados": kg_gerados,
        "kg_entregues": kg_entregues,
        "kg_ongs": kg_ongs,
        "kg_armazens": kg_armazens,
        "kg_sem_entrega": round(kg_gerados - kg_entregues, 2),
        "taxa_de_resgate": round(kg_entregues / kg_gerados, 2)
                           if kg_gerados else 0,
        "taxa_entrega_direta_ongs": round(kg_ongs / kg_gerados, 2)
                                   if kg_gerados else 0,
    }
