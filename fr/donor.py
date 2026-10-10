"""
DonorAgent (papel Gaia: Doador / OfferInitiator).
Gera excedentes de forma estocástica (picos ao fecho) e lança um
OfferBehaviour por cada item.
"""
from __future__ import annotations

from spade.behaviour import PeriodicBehaviour

from .base import FRAgent
from .offer import OfferBehaviour
from .protocol import conversation_template
from .world import RNG, Clock, Item, M

KINDS = ["bakery", "produce", "prepared", "dairy"]


class DonorAgent(FRAgent):
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.counter = 0

    def launch_offer(self, item: Item) -> None:
        b = OfferBehaviour(item)
        self.add_behaviour(b, conversation_template(f"{item.id}@{self.name_}"))

    class Generate(PeriodicBehaviour):
        async def run(self):
            a, cfg = self.agent, self.agent.cfg
            now = Clock.now()
            if now > cfg.duration_min:
                self.kill()
                return
            p = cfg.p_surplus * (cfg.peak_multiplier if now >= cfg.peak_after_min else 1.0)
            if RNG.random() >= min(p, 0.95):
                return
            a.counter += 1
            cold = RNG.random() < cfg.p_chilled
            lo, hi = cfg.shelf_life_min["chilled" if cold else "ambient"]
            item = Item(
                id=f"{a.name_}-{a.counter}",
                donor=str(a.jid),
                kind=RNG.choice(KINDS[2:] if cold else KINDS[:2]),
                kg=round(RNG.uniform(*cfg.kg_range), 1),
                cold=cold,
                created=now,
                expires=now + RNG.uniform(lo, hi),
                pos=a.pos,
                label_ok=RNG.random() >= cfg.p_bad_label,
            )
            M.offered(item)
            a.launch_offer(item)

    async def handle(self, behaviour, msg):
        pass  # o doador só fala dentro das suas conversas (OfferBehaviour)

    async def setup(self):
        await super().setup()
        self.add_behaviour(self.Generate(period=Clock.secs(self.cfg.gen_every_min)))
