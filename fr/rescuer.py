"""
RescuerAgent (papel Gaia: Transportador / Bidder).
Licita em recolhas (RF04) conforme distância, capacidade, frio e turno.
Pode cancelar (FAILURE) ou não aparecer (no-show) — cenários S3/S4.
"""
from __future__ import annotations

import asyncio
import time

from spade.behaviour import OneShotBehaviour

from .base import FRAgent
from . import protocol as P
from .world import RNG, Clock, M, dist

HANDLING_MIN = 10


class RescuerAgent(FRAgent):
    def __init__(self, *args, capacity: float, cold: bool, speed: float,
                 on_shift: bool, unreliable: bool, **kw):
        super().__init__(*args, **kw)
        self.capacity = capacity
        self.has_cold = cold
        self.speed = speed               # km por minuto simulado
        self.on_shift = on_shift
        self.unreliable = unreliable
        self.busy = False
        self.bid_lock_until = 0.0        # evita ganhar duas recolhas ao mesmo tempo

    def estimate(self, it: dict, to_pos):
        d1 = dist(self.pos, tuple(it["pos"]))
        d2 = dist(tuple(it["pos"]), tuple(to_pos))
        return d1, d2, (d1 + d2) / self.speed + 2 * HANDLING_MIN, d2 / self.speed + HANDLING_MIN

    async def handle(self, b, msg):
        p, c = P.perf(msg), P.body(msg)
        if msg.get_metadata("protocol") != "transport-cnp":
            return
        it = c["item"]

        if p == "cfp":
            d1, d2, eta, out_of_cold = self.estimate(it, c["to_pos"])
            feasible = (self.on_shift and not self.busy
                        and time.monotonic() > self.bid_lock_until
                        and self.capacity >= it["kg"]
                        and (not it["cold"] or self.has_cold
                             or out_of_cold <= self.cfg.cold_max_out_min))
            if feasible:
                self.bid_lock_until = time.monotonic() + 2 * self.cfg.bid_window_s
                await P.send(b, P.reply(msg, "propose", {
                    "round": c["round"], "eta_total": round(eta, 1),
                    "km": d1 + d2, "cold": self.has_cold}), self.cfg.msg_loss)
            else:
                await P.send(b, P.reply(msg, "refuse", {"round": c["round"]}), self.cfg.msg_loss)

        elif p == "reject-proposal":
            self.bid_lock_until = 0.0

        elif p == "accept-proposal":
            self.bid_lock_until = 0.0
            if self.busy:
                await P.send(b, P.reply(msg, "failure", {"round": c["round"], "why": "busy"}),
                             self.cfg.msg_loss)
                return
            self.busy = True
            self.add_behaviour(self.Job(msg, c))

    class Job(OneShotBehaviour):
        """Executa a recolha e a entrega em tempo simulado."""
        def __init__(self, msg, c):
            super().__init__()
            self.msg, self.c = msg, c

        async def run(self):
            a, c, cfg = self.agent, self.c, self.agent.cfg
            it = c["item"]
            d1, d2, eta, out_of_cold = a.estimate(it, c["to_pos"])
            try:
                # S4: voluntário não fiável que simplesmente não aparece
                if a.unreliable and RNG.random() < cfg.p_noshow:
                    await asyncio.sleep(Clock.secs(eta))
                    return
                # Cancelamento de última hora (avisa)
                if RNG.random() < cfg.p_cancel:
                    await asyncio.sleep(Clock.secs(RNG.uniform(0, d1 / a.speed + 5)))
                    await P.send(self, P.reply(self.msg, "failure",
                                               {"round": c["round"], "why": "cancelled"}),
                                 cfg.msg_loss)
                    return
                await asyncio.sleep(Clock.secs(eta))
                M.km += d1 + d2
                a.pos = tuple(c["to_pos"])
                cold_violation = it["cold"] and not a.has_cold and out_of_cold > cfg.cold_max_out_min
                it["pos"] = list(a.pos)
                # entrega ao destino + confirmação ao iniciador
                await P.send(self, P.make(c["to"], "inform", "delivery",
                                          f"dlv-{it['id']}", "init",
                                          {"item": it, "cold_violation": cold_violation,
                                           "rescuer": str(a.jid)}), cfg.msg_loss)
                await P.send(self, P.reply(self.msg, "inform",
                                           {"round": c["round"], "done": True}), cfg.msg_loss)
            finally:
                a.busy = False
