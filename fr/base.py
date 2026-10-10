"""
Classe base comum a todos os agentes: posição, vizinhos conhecidos,
reputação local e a Inbox (um CyclicBehaviour que trata as mensagens 'init').
"""
from __future__ import annotations

from spade.agent import Agent
from spade.behaviour import CyclicBehaviour

from .config import Config
from .protocol import inbox_template, perf
from .world import M


class FRAgent(Agent):
    """Agente genérico do Food Rescue."""

    def __init__(self, jid: str, password: str, cfg: Config, pos: tuple):
        super().__init__(jid, password)
        self.cfg = cfg
        self.pos = pos
        # Descoberta descentralizada (RF03): cada agente só conhece os pares
        # dentro do seu raio. Preenchido em run.py antes do start().
        self.recipients: list[tuple[str, tuple]] = []
        self.rescuers: list[str] = []
        self.fridges: list[tuple[str, tuple]] = []
        # Reputação LOCAL (RF09): jid -> valor em [0.1, 1.0]. Começa em 0.7.
        self.rep: dict[str, float] = {}

    @property
    def name_(self) -> str:
        return str(self.jid).split("@")[0]

    # --- reputação ---------------------------------------------------------
    def reputation(self, jid: str) -> float:
        return self.rep.get(jid, 0.7)

    def update_rep(self, jid: str, success: bool) -> None:
        """Média móvel exponencial: sucesso puxa para 1, falha para 0."""
        r = self.reputation(jid)
        target = 1.0 if success else 0.0
        self.rep[jid] = max(0.1, min(1.0, 0.7 * r + 0.3 * target))

    # --- inbox ---------------------------------------------------------------
    async def handle(self, behaviour, msg) -> None:   # implementado nas subclasses
        pass

    class Inbox(CyclicBehaviour):
        async def run(self):
            msg = await self.receive(timeout=1)
            if msg:
                try:
                    await self.agent.handle(self, msg)
                except Exception as e:  # nunca deixar a inbox morrer
                    M.log("error", agent=self.agent.name_, perf=perf(msg), err=repr(e))

    async def setup(self):
        self.add_behaviour(self.Inbox(), inbox_template())
