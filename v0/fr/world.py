"""
Modelo de ambiente (Gaia, fase 1b): relógio simulado, espaço, itens de alimento
e recolha de métricas.

NOTA: `Metrics` é instrumentação da simulação (o "observador" do experimento),
NÃO é um agente e nunca é consultado pelos agentes para decidir. Assim não viola
o requisito de "sem despachante central" (RNF01).
"""
from __future__ import annotations

import csv
import json
import random
import time
from dataclasses import dataclass, asdict

RNG = random.Random(42)          # reprodutibilidade (RNF06): semeado em run.py


def seed(s: int) -> None:
    RNG.seed(s)


# ---------------------------------------------------------------------------
# Relógio simulado
# ---------------------------------------------------------------------------
class Clock:
    real_per_min = 0.05
    t0 = 0.0

    @classmethod
    def start(cls, real_per_min: float) -> None:
        cls.real_per_min = real_per_min
        cls.t0 = time.monotonic()

    @classmethod
    def now(cls) -> float:
        """Minutos simulados desde o início."""
        return (time.monotonic() - cls.t0) / cls.real_per_min

    @classmethod
    def secs(cls, sim_min: float) -> float:
        """Converte minutos simulados em segundos reais (para asyncio.sleep)."""
        return max(0.0, sim_min) * cls.real_per_min


def dist(a, b) -> float:
    """Distância Manhattan em km (aproximação de uma grelha de ruas)."""
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


# ---------------------------------------------------------------------------
# Item de alimento
# ---------------------------------------------------------------------------
@dataclass
class Item:
    id: str
    donor: str            # JID do doador original
    kind: str             # bakery | produce | prepared | dairy
    kg: float
    cold: bool            # precisa de cadeia de frio?
    created: float        # min simulado em que foi oferecido
    expires: float        # min simulado em que deixa de ser seguro
    pos: tuple            # onde está neste momento
    label_ok: bool = True # S4: False = rotulagem errada / impróprio

    def remaining(self) -> float:
        return self.expires - Clock.now()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["pos"] = list(self.pos)
        return d

    @staticmethod
    def from_dict(d: dict) -> "Item":
        d = dict(d)
        d["pos"] = tuple(d["pos"])
        return Item(**d)


# ---------------------------------------------------------------------------
# Métricas
# ---------------------------------------------------------------------------
class Metrics:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.items: dict[str, dict] = {}        # id -> {kg, status, reason, t_offer, t_end}
        self.msgs_sent = 0
        self.msgs_lost = 0
        self.km = 0.0
        self.cold_violations = 0
        self.cancellations = 0                  # falhas de transporte (cancelamento/no-show)
        self.recovered = 0                      # itens entregues apesar de >=1 falha
        self.received_by: dict[str, float] = {}
        self.events: list[dict] = []

    # --- ciclo de vida dos itens -------------------------------------------
    def offered(self, item: Item) -> None:
        self.items[item.id] = {"kg": item.kg, "status": "pending", "reason": "",
                               "t_offer": item.created, "t_end": None,
                               "cold": item.cold, "failures": 0}
        self.log("offer", item=item.id, kg=item.kg, by=item.donor)

    def is_final(self, item_id: str) -> bool:
        return self.items.get(item_id, {}).get("status") in ("delivered", "wasted")

    def finish(self, item_id: str, status: str, reason: str = "", recipient: str = "") -> None:
        """Estado terminal idempotente: um item só é contado uma vez."""
        rec = self.items.get(item_id)
        if rec is None or rec["status"] in ("delivered", "wasted"):
            return
        rec.update(status=status, reason=reason, t_end=Clock.now())
        if status == "delivered":
            self.received_by[recipient] = self.received_by.get(recipient, 0) + rec["kg"]
            if rec["failures"] > 0:
                self.recovered += 1
        self.log(status, item=item_id, kg=rec["kg"], reason=reason, to=recipient)

    def transport_failure(self, item_id: str) -> None:
        self.cancellations += 1
        if item_id in self.items:
            self.items[item_id]["failures"] += 1

    def log(self, event: str, **kw) -> None:
        self.events.append({"t": round(Clock.now(), 1), "event": event, **kw})

    # --- resumo ----------------------------------------------------------
    def summary(self, recipients: list[str]) -> dict:
        it = self.items.values()
        offered = sum(r["kg"] for r in it)
        delivered = [r for r in it if r["status"] == "delivered"]
        wasted = [r for r in it if r["status"] == "wasted"]
        kg_del = sum(r["kg"] for r in delivered)
        kg_waste = sum(r["kg"] for r in wasted)
        times = [r["t_end"] - r["t_offer"] for r in delivered]
        xs = [self.received_by.get(r, 0.0) for r in recipients]
        jain = (sum(xs) ** 2) / (len(xs) * sum(x * x for x in xs)) if any(xs) else 0.0
        failed_items = [r for r in it if r["failures"] > 0]
        reasons: dict[str, float] = {}
        for r in wasted:
            reasons[r["reason"]] = reasons.get(r["reason"], 0) + r["kg"]
        return {
            "items_offered": len(self.items),
            "kg_offered": round(offered, 1),
            "kg_delivered": round(kg_del, 1),
            "kg_wasted": round(kg_waste, 1),
            "kg_pending_at_end": round(offered - kg_del - kg_waste, 1),
            "rescue_rate": round(kg_del / offered, 3) if offered else 0,
            "waste_by_reason_kg": {k: round(v, 1) for k, v in reasons.items()},
            "avg_offer_to_delivery_min": round(sum(times) / len(times), 1) if times else None,
            "cold_chain_violations": self.cold_violations,
            "transport_failures": self.cancellations,
            "recovery_rate": round(self.recovered / len(failed_items), 3) if failed_items else None,
            "km_per_kg_delivered": round(self.km / kg_del, 3) if kg_del else None,
            "jain_fairness": round(jain, 3),
            "msgs_sent": self.msgs_sent,
            "msgs_lost": self.msgs_lost,
            "msgs_per_delivery": round(self.msgs_sent / len(delivered), 1) if delivered else None,
        }

    def save(self, prefix: str, summary: dict) -> None:
        with open(prefix + "_summary.json", "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        keys = sorted({k for e in self.events for k in e})
        with open(prefix + "_events.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(self.events)


M = Metrics()
