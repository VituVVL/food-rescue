"""
RecipientAgent (papel Gaia: Recetor / NeedPublisher + Verifier).
Responde a ofertas conforme a sua necessidade e verifica o alimento à chegada (RF08).
"""
from __future__ import annotations

from spade.behaviour import PeriodicBehaviour

from .base import FRAgent
from . import protocol as P
from .world import RNG, Clock, M


class RecipientAgent(FRAgent):
    def __init__(self, *args, accepts: set, need_kg: float, urgency: int, **kw):
        super().__init__(*args, **kw)
        self.accepts = accepts
        self.need = need_kg          # necessidade agregada (RNF05: sem dados pessoais)
        self.need_max = need_kg
        self.urgency = urgency       # 1..3
        self.received = 0.0
        self.reserved: dict[str, float] = {}

    async def handle(self, b, msg):
        p, c = P.perf(msg), P.body(msg)
        proto = msg.get_metadata("protocol")

        if proto == "offer-cnp" and p == "cfp":
            it = c["item"]
            donor = it["donor"]
            ok = (it["kind"] in self.accepts and self.need > 0
                  and self.reputation(donor) >= 0.35)      # recusa doadores com má reputação
            if ok:
                await P.send(b, P.reply(msg, "propose", {
                    "round": c["round"], "kg_wanted": min(self.need, it["kg"]),
                    "urgency": self.urgency, "received_kg": self.received,
                    "pos": list(self.pos)}), self.cfg.msg_loss)
            else:
                await P.send(b, P.reply(msg, "refuse", {"round": c["round"]}), self.cfg.msg_loss)

        elif proto == "offer-cnp" and p == "accept-proposal":
            kg = M.items.get(c["item_id"], {}).get("kg", 0)
            self.reserved[c["item_id"]] = kg
            self.need -= kg

        elif proto == "offer-cnp" and p == "cancel":
            self.need += self.reserved.pop(c["item_id"], 0)

        elif proto == "delivery" and p == "inform":
            await self.verify(c)

    class Consume(PeriodicBehaviour):
        """A necessidade renova-se ao longo do dia (as pessoas continuam a comer)."""
        async def run(self):
            a = self.agent
            a.need = min(a.need_max, a.need + a.cfg.need_regen * a.need_max)

    async def setup(self):
        await super().setup()
        self.add_behaviour(self.Consume(period=Clock.secs(60)))

    async def verify(self, c):
        """Verificação à entrega (RF08): validade, cadeia de frio, aspeto/rótulo."""
        it = c["item"]
        self.reserved.pop(it["id"], None)
        reason = ""
        if Clock.now() > it["expires"]:
            reason = "expired_on_arrival"
        elif c.get("cold_violation"):
            reason = "cold_chain"
            M.cold_violations += 1
        elif not it["label_ok"] and RNG.random() < 0.85:   # inspeção deteta 85%
            reason = "failed_inspection"
        if reason:
            M.finish(it["id"], "wasted", reason)
            self.update_rep(it["donor"], False)
        else:
            self.received += it["kg"]
            M.finish(it["id"], "delivered", recipient=self.name_)
            self.update_rep(it["donor"], True)
