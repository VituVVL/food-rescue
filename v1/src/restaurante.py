"""
Restaurante: papel DOADOR.

É quem tem o lote, por isso é quem conduz a conversa (é o "gestor" do Contract
Net). Para cada lote faz, em ordem:

  1. AnunciarOferta às ONGs que conhece    -> uma ONG fica com o que precisa
  2. AnunciarOferta do excedente ao armazém -> o armazém guarda o que couber
  3. ContratarResgate para cada parte       -> um resgatador leva cada parte

Não há ninguém a mandar: o restaurante só fala com quem conhece (as ONGs dentro
de RAIO_DOADOR_KM e os armazéns), e cada um responde ou recusa por conta própria.
O código das conversas está em doador.py (é o mesmo que o armazém usa).
"""
from __future__ import annotations

import asyncio

from spade.agent import Agent
from spade.behaviour import OneShotBehaviour

from . import mensagens as M
from .config import PAUSA_ENTRE_LOTES_S
from .doador import ConduzirLote
from .registo import agora_min, registar


class RestauranteAgent(Agent):
    def __init__(self, jid, senha, pos, ongs, resgatadores, armazens, lotes, ao_terminar):
        """
        ongs         : lista de (jid, pos) das ONGs que este restaurante conhece
        resgatadores : lista de jids dos resgatadores que conhece
        armazens     : lista de (jid, pos) dos armazéns que conhece
        lotes        : lista de dicionários (categoria, kg, validade_min)
        ao_terminar  : função chamada quando todos os lotes tiverem acabado
        """
        super().__init__(jid, senha)
        self.pos = pos
        self.ongs = ongs
        self.resgatadores = resgatadores
        self.armazens = armazens
        self.lotes = lotes
        self.ao_terminar = ao_terminar
        self.nome = str(jid).split("@")[0]
        self.lotes_pendentes = len(lotes)

    async def setup(self):
        self.add_behaviour(self.GerarLotes())

    # -------------------------------------------------------------------------
    class GerarLotes(OneShotBehaviour):
        """Gera os lotes um a um e lança uma GerirLote para cada um."""

        async def run(self):
            a = self.agent
            for i, dados in enumerate(a.lotes, start=1):
                await asyncio.sleep(PAUSA_ENTRE_LOTES_S)
                lote = {"id": f"{a.nome}-L{i}", "doador": str(a.jid), "origem": list(a.pos),
                        "criado_min": round(agora_min(), 1), **dados}
                registar(a.nome, "lote_gerado", lote["id"],
                         categoria=lote["categoria"], kg=lote["kg"])
                # Cada lote tem o seu comportamento, que só vê as RESPOSTAS desse lote.
                a.add_behaviour(a.GerirLote(lote), M.template_respostas(lote["id"]))

    # -------------------------------------------------------------------------
    class GerirLote(ConduzirLote):
        """A vida de um lote, do ponto de vista do restaurante."""

        def __init__(self, lote: dict):
            super().__init__()
            self.lote = lote

        async def run(self):
            try:
                await self.conduzir()
            finally:
                self.agent.lotes_pendentes -= 1
                if self.agent.lotes_pendentes == 0:
                    self.agent.ao_terminar()

        async def conduzir(self):
            a, lote = self.agent, self.lote
            partes = []                         # (lote com os kg da parte, destino, tipo)

            # ---- 1. primeiro as ONGs (entrega direta a quem precisa) -------
            ong = await self.anunciar_oferta(lote, a.ongs)
            if ong:
                partes.append(({**lote, "kg": ong["kg"]}, ong, "ong"))
            excedente = lote["kg"] - (ong["kg"] if ong else 0)

            # ---- 2. o excedente vai para o armazém (serviço de armazenagem) -
            if excedente > 0:
                armazem = await self.anunciar_oferta({**lote, "kg": excedente}, a.armazens)
                if armazem:
                    partes.append(({**lote, "kg": armazem["kg"]}, armazem, "armazem"))
                    excedente -= armazem["kg"]
            if excedente > 0:
                registar(a.nome, "sem_destino", lote["id"], kg=excedente,
                         motivo="nenhum destino com capacidade")

            # ---- 3. um resgatador para cada parte --------------------------
            # Em sequência: com poucos resgatadores, em paralelo daria "ocupado".
            for parte, destino, tipo in partes:
                await self.contratar_resgate(parte, destino, tipo)
