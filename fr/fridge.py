"""
FridgeAgent (papel Gaia: Armazenamento temporário / Buffer).
Aceita ou recusa depósitos (RF06) consoante capacidade e estado; volta a
oferecer o que guarda (reutiliza o OfferBehaviour). Pode avariar (S3).
"""
from __future__ import annotations

from spade.behaviour import PeriodicBehaviour

from .base import FRAgent
from .offer import OfferBehaviour
from . import protocol as P
from .world import Clock, Item, M


class FridgeAgent(FRAgent):
    is_fridge = True

    def __init__(self, *args, capacity: float, fail_at: float | None, **kw):
        super().__init__(*args, **kw)
        self.capacity = capacity
        self.fail_at = fail_at
        self.working = True
        self.used = 0.0
        self.reserved: dict[str, float] = {}
        self.stock: dict[str, Item] = {}
        self.offering: set[str] = set()

    def free(self) -> float:
        return self.capacity - self.used - sum(self.reserved.values())

    def release(self, item: Item) -> None:
        if self.stock.pop(item.id, None):
            self.used -= item.kg

    async def handle(self, b, msg):
        p, c = P.perf(msg), P.body(msg)
        proto = msg.get_metadata("protocol")
        if proto == "deposit" and p == "request":
            it = c["item"]
            ok = self.working and self.free() >= it["kg"]
            if ok:
                self.reserved[it["id"]] = it["kg"]
            await P.send(b, P.reply(msg, "agree" if ok else "refuse", {"round": c["round"]}),
                         self.cfg.msg_loss)
        elif p == "cancel":
            self.reserved.pop(c["item_id"], None)
        elif proto == "delivery" and p == "inform":
            it = Item.from_dict(c["item"])
            self.reserved.pop(it.id, None)
            if Clock.now() > it.expires or c.get("cold_violation") or not self.working:
                if c.get("cold_violation"):
                    M.cold_violations += 1
                M.finish(it.id, "wasted", "rejected_by_fridge")
                return
            it.pos = self.pos
            self.stock[it.id] = it
            self.used += it.kg
            M.log("stored", item=it.id, fridge=self.name_)

    class Maintain(PeriodicBehaviour):
        """Verifica avaria, validades e volta a oferecer o stock."""
        async def run(self):
            a = self.agent
            now = Clock.now()
            if a.working and a.fail_at is not None and now >= a.fail_at:
                a.working = False
                M.log("fridge_failure", fridge=a.name_)
                for it in list(a.stock.values()):
                    if it.cold:
                        M.cold_violations += 1
                        M.finish(it.id, "wasted", "fridge_failure")
                        a.release(it)
            for it in list(a.stock.values()):
                if M.is_final(it.id) or it.remaining() <= 15:
                    M.finish(it.id, "wasted", "expired_in_fridge")
                    a.release(it)
                elif it.id not in a.offering:
                    a.offering.add(it.id)
                    a.add_behaviour(OfferBehaviour(it),
                                    P.conversation_template(f"{it.id}@{a.name_}"))

    async def setup(self):
        await super().setup()
        self.add_behaviour(self.Maintain(period=Clock.secs(self.cfg.fridge_reoffer_every_min)))
