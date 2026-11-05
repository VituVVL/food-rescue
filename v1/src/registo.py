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
    """Resumo simples no fim da corrida."""
    entregues = [e for e in EVENTOS if e["evento"] == "lote_entregue"]
    kg_gerados = sum(l["kg"] for l in lotes_gerados)
    kg_entregues = sum(e.get("kg", 0) for e in entregues)
    return {
        "lotes_gerados": len(lotes_gerados),
        "lotes_entregues": len(entregues),
        "kg_gerados": kg_gerados,
        "kg_entregues": kg_entregues,
        "taxa_de_resgate": round(kg_entregues / kg_gerados, 2) if kg_gerados else 0,
    }
