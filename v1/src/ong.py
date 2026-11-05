"""
ONG: papel RECEPTOR.

Responde às ofertas dos restaurantes e recebe as entregas. Um abrigo seria o
mesmo código com outros parâmetros (categorias aceites e necessidade).

Regra de segurança do guia: "não declara necessidade acima do que consegue
guardar". Aqui: kg reservados + kg já recebidos nunca passam da necessidade.
"""
from __future__ import annotations

from spade.agent import Agent
from spade.behaviour import CyclicBehaviour

from . import mensagens as M
from .config import TEMP_MAX_REFRIGERADO_C
from .registo import registar


class OngAgent(Agent):
    def __init__(self, jid, senha, pos, categorias, necessidade_kg):
        super().__init__(jid, senha)
        self.pos = pos
        self.categorias = categorias            # o que aceita (ex.: {"seco", "refrigerado"})
        self.necessidade_kg = necessidade_kg    # quanto quer receber no total
        self.reservado_kg = 0.0                 # prometido a lotes que ainda não chegaram
        self.recebido_kg = 0.0
        self.reservas: dict[str, float] = {}    # lote -> kg reservados
        self.nome = str(jid).split("@")[0]

    @property
    def livre_kg(self) -> float:
        return self.necessidade_kg - self.reservado_kg - self.recebido_kg

    async def setup(self):
        # A Inbox só vê PEDIDOS (ver mensagens.py).
        self.add_behaviour(self.Inbox(), M.template_pedidos())

    class Inbox(CyclicBehaviour):
        async def run(self):
            msg = await self.receive(timeout=1)
            if msg is None:
                return
            a = self.agent
            proto, perf, lote_id = M.protocolo(msg), M.performativa(msg), M.lote(msg)

            # ------------------ AnunciarOferta (somos o respondente) -------
            if proto == "oferta" and perf == "cfp":
                lote = M.conteudo(msg)["lote"]
                aceita = lote["categoria"] in a.categorias and a.livre_kg > 0
                if not aceita:
                    registar(a.nome, "oferta_recusada", lote_id, categoria=lote["categoria"])
                    await self.send(M.responder(msg, "refuse", {"motivo": "não preciso"}))
                    return
                kg = min(lote["kg"], a.livre_kg)
                a.reservas[lote_id] = kg            # reserva JÁ na proposta, para não prometer em duplicado
                a.reservado_kg += kg
                registar(a.nome, "oferta_proposta", lote_id, kg=kg)
                await self.send(M.responder(msg, "propose", {"kg": kg, "pos": list(a.pos)}))

            # reject-proposal = não fomos escolhidos; cancel = o restaurante desistiu depois.
            # Nos dois casos libertamos a reserva (senão os kg ficavam presos para sempre).
            elif proto == "oferta" and perf in ("reject-proposal", "cancel"):
                a.reservado_kg -= a.reservas.pop(lote_id, 0)
                registar(a.nome, "reserva_libertada", lote_id, motivo=perf)

            elif proto == "oferta" and perf == "accept-proposal":
                registar(a.nome, "destino_confirmado", lote_id)

            # ------------------ EntregarLote (somos o destino) -------------
            elif proto == "entrega" and perf == "inform":
                c = M.conteudo(msg)
                lote = c["lote"]
                kg_reservado = a.reservas.pop(lote_id, 0)
                a.reservado_kg -= kg_reservado
                motivo = self.inspecionar(lote, c["temperatura_c"], kg_reservado)
                if motivo:
                    registar(a.nome, "entrega_recusada", lote_id, motivo=motivo)
                    await self.send(M.responder(msg, "inform", {"resultado": "recusada", "motivo": motivo}))
                else:
                    a.recebido_kg += lote["kg"]
                    registar(a.nome, "entrega_aceita", lote_id, kg=lote["kg"],
                             total_recebido=a.recebido_kg)
                    await self.send(M.responder(msg, "inform", {"resultado": "confirmada"}))

        def inspecionar(self, lote: dict, temperatura_c: float, kg_reservado: float) -> str | None:
            """InspecionarLote. Devolve o motivo da recusa, ou None se estiver tudo bem."""
            if lote["kg"] > kg_reservado + 1e-9:
                return "kg acima do reservado"
            if lote["categoria"] == "refrigerado" and temperatura_c > TEMP_MAX_REFRIGERADO_C:
                return "quebra da cadeia de frio"
            return None
