"""
OfferBehaviour — o "coração" do sistema. Corre no agente que tem o alimento
(doador ou frigorífico) e trata todo o ciclo de vida de UM item:

  1. offer-cnp     : escolhe o recetor (urgência, necessidade, equidade, distância)
  2. deposit       : se nenhum recetor serve e ainda há tempo, tenta um frigorífico
  3. transport-cnp : contrata um voluntário (ETA, km, frio, reputação)
  4. espera pelo inform{done}; se houver FAILURE ou silêncio -> realoca (RF07)

Não há despachante central: cada item é negociado pelo agente que o detém,
apenas com os pares que conhece (vizinhança).
"""
from __future__ import annotations

import asyncio
import time

from spade.behaviour import OneShotBehaviour

from . import protocol as P
from .world import Clock, Item, M, dist

HANDLING_MIN = 10   # tempo de carga/descarga


class OfferBehaviour(OneShotBehaviour):
    def __init__(self, item: Item):
        super().__init__()
        self.item = item
        self.round = 0

    @property
    def thread(self) -> str:
        return f"{self.item.id}@{self.agent.name_}"

    # ----------------------------------------------------------------- utils
    async def collect(self, round_id: str, expected: int, wait_s: float):
        """Recolhe respostas desta ronda até `expected` ou até acabar o tempo."""
        out = []
        deadline = time.monotonic() + wait_s
        while len(out) < expected:
            rem = deadline - time.monotonic()
            if rem <= 0:
                break
            msg = await self.receive(timeout=rem)
            if msg is None:
                break
            c = P.body(msg)
            if c.get("round") == round_id:
                out.append((msg, c))
        return out

    def new_round(self, tag: str) -> str:
        self.round += 1
        return f"{tag}{self.round}"

    async def send(self, msg):  # sobrepõe para aplicar perda de mensagens
        await P.send(super(), msg, self.agent.cfg.msg_loss)

    # --------------------------------------------------------- 1. recetor
    async def choose_recipient(self):
        a, it = self.agent, self.item
        cands = [(j, p) for j, p in a.recipients]
        if not cands:
            return None
        rid = self.new_round("R")
        for j, _ in cands:
            await self.send(P.make(j, "cfp", "offer-cnp", self.thread, "init",
                                   {"round": rid, "item": it.to_dict()}))
        props = await self.collect(rid, len(cands), a.cfg.bid_window_s)
        best, best_score = None, -1e9
        for msg, c in props:
            if P.perf(msg) != "propose":
                continue
            d = dist(it.pos, tuple(c["pos"]))
            # Equidade (RF10): quem já recebeu muito pontua menos.
            score = (c["urgency"] * min(c["kg_wanted"], it.kg)
                     / (1 + c["received_kg"] / 20) - 0.5 * d)
            if score > best_score:
                best, best_score = (str(msg.sender), tuple(c["pos"])), score
        for msg, c in props:
            if P.perf(msg) == "propose":
                p = "accept-proposal" if best and str(msg.sender) == best[0] else "reject-proposal"
                await self.send(P.make(str(msg.sender), p, "offer-cnp", self.thread, "init",
                                       {"round": rid, "item_id": it.id}))
        return best

    # ------------------------------------------------------- 2. frigorífico
    async def choose_fridge(self):
        a, it = self.agent, self.item
        for j, p in sorted(a.fridges, key=lambda f: dist(it.pos, f[1])):
            rid = self.new_round("F")
            await self.send(P.make(j, "request", "deposit", self.thread, "init",
                                   {"round": rid, "item": it.to_dict()}))
            ans = await self.collect(rid, 1, a.cfg.bid_window_s)
            if ans and P.perf(ans[0][0]) == "agree":
                return (j, p)
        return None

    # ------------------------------------------------------- 3. transporte
    async def contract_rescuer(self, dest):
        a, it = self.agent, self.item
        if not a.rescuers:
            return None
        rid = self.new_round("T")
        for j in a.rescuers:
            await self.send(P.make(j, "cfp", "transport-cnp", self.thread, "init",
                                   {"round": rid, "item": it.to_dict(),
                                    "to": dest[0], "to_pos": list(dest[1])}))
        props = await self.collect(rid, len(a.rescuers), a.cfg.bid_window_s)
        best, best_cost = None, 1e9
        for msg, c in props:
            if P.perf(msg) != "propose":
                continue
            if Clock.now() + c["eta_total"] > it.expires:   # chegaria tarde demais
                continue
            # Custo: tempo total penalizado por baixa reputação do voluntário.
            cost = c["eta_total"] / a.reputation(str(msg.sender))
            if cost < best_cost:
                best, best_cost = (str(msg.sender), c), cost
        for msg, c in props:
            if P.perf(msg) == "propose":
                p = "accept-proposal" if best and str(msg.sender) == best[0] else "reject-proposal"
                await self.send(P.make(str(msg.sender), p, "transport-cnp", self.thread, "init",
                                       {"round": rid, "item": it.to_dict(),
                                        "to": dest[0], "to_pos": list(dest[1])}))
        return (best[0], best[1], rid) if best else None

    async def wait_outcome(self, rescuer: str, rid: str, eta: float) -> str:
        """Espera inform{done} ou failure. Silêncio = no-show."""
        deadline = time.monotonic() + Clock.secs(eta * 1.5 + 20)
        while True:
            rem = deadline - time.monotonic()
            if rem <= 0:
                return "timeout"
            msg = await self.receive(timeout=rem)
            if msg is None:
                return "timeout"
            c = P.body(msg)
            if c.get("round") == rid and str(msg.sender) == rescuer:
                return "done" if P.perf(msg) == "inform" else "failure"

    async def cancel(self, dest):
        await self.send(P.make(dest[0], "cancel", "offer-cnp", self.thread, "init",
                               {"item_id": self.item.id, "kg": self.item.kg}))

    # ------------------------------------------------------------- ciclo
    async def run(self):
        a, it, cfg = self.agent, self.item, self.agent.cfg
        is_fridge = getattr(a, "is_fridge", False)

        while not M.is_final(it.id):
            if it.remaining() <= 15:
                M.finish(it.id, "wasted", "expired_unmatched")
                break

            dest = await self.choose_recipient()
            if dest is None and not is_fridge:
                dest = await self.choose_fridge()
            if dest is None:
                await asyncio.sleep(Clock.secs(cfg.retry_every_min))
                continue

            # Contratar transporte, com realocação em caso de falha (RF07)
            delivered = False
            for _ in range(cfg.max_transport_attempts):
                if M.is_final(it.id) or it.remaining() <= 15:
                    break
                deal = await self.contract_rescuer(dest)
                if deal is None:
                    await asyncio.sleep(Clock.secs(cfg.retry_every_min / 2))
                    continue
                rescuer, offer, rid = deal
                outcome = await self.wait_outcome(rescuer, rid, offer["eta_total"])
                a.update_rep(rescuer, outcome == "done")
                if outcome == "done":
                    delivered = True
                    break
                M.transport_failure(it.id)
                M.log("transport_failure", item=it.id, rescuer=rescuer, why=outcome)

            if delivered:
                if is_fridge:
                    a.release(it)
                break
            await self.cancel(dest)          # liberta reserva e tenta outro destino

        if is_fridge:
            a.offering.discard(it.id)
