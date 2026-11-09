"""
Restaurante: papel DOADOR.

É quem tem o lote, por isso é quem conduz a conversa (é o "gestor" do Contract
Net). Para cada lote faz, em ordem:

  1. AnunciarOferta   -> pergunta às ONGs vizinhas quem quer o lote e escolhe uma
  2. ContratarResgate -> pergunta aos resgatadores quem leva e escolhe um (Contract Net)
  3. espera o resultado da entrega

Não há ninguém a mandar: o restaurante só fala com quem conhece, e cada um
responde (ou recusa) por conta própria.
"""
from __future__ import annotations

import asyncio

from spade.agent import Agent
from spade.behaviour import OneShotBehaviour

from . import mensagens as M
from .config import ESCALA_S, PAUSA_ENTRE_LOTES_S, PRAZO_RESPOSTAS_S, distancia
from .registo import registar


# =============================================================================
# DECISÕES DO RESTAURANTE
# São funções pequenas e separadas de propósito: é aqui que o grupo vai mexer
# para melhorar o comportamento (urgência, equidade, reputação, ...).
# =============================================================================
def escolher_destino(propostas: list[dict]) -> dict | None:
    """
    Cada proposta é {"jid", "kg", "pos"}. Regra atual: quem aceita mais kg;
    em empate, a mais perto. Devolve None se não houver propostas.
    """
    if not propostas:
        return None
    return max(propostas, key=lambda p: (p["kg"], -p["distancia"]))


def escolher_resgatador(propostas: list[dict]) -> dict | None:
    """Cada proposta é {"jid", "tempo_min"}. Regra atual: o mais rápido."""
    if not propostas:
        return None
    return min(propostas, key=lambda p: p["tempo_min"])


# =============================================================================
class RestauranteAgent(Agent):
    def __init__(self, jid, senha, pos, ongs, resgatadores, lotes, ao_terminar, armazens):
        """
        ongs         : lista de (jid, pos) das ONGs que este restaurante conhece
        resgatadores : lista de jids dos resgatadores que conhece
        lotes        : lista de dicionários (categoria, kg, validade_min)
        ao_terminar  : função chamada quando todos os lotes tiverem acabado
        """
        super().__init__(jid, senha)
        self.pos = pos
        self.ongs = ongs
        self.resgatadores = resgatadores
        self.lotes = lotes
        self.ao_terminar = ao_terminar
        self.nome = str(jid).split("@")[0]
        self.lotes_pendentes = len(lotes)
        self.armazens = armazens

    async def setup(self):
        self.add_behaviour(self.GerarLotes())

    # -------------------------------------------------------------------------
    class GerarLotes(OneShotBehaviour):
        """Gera os lotes um a um e lança uma GerirLote para cada um."""

        async def run(self):
            a = self.agent
            for i, dados in enumerate(a.lotes, start=1):
                await asyncio.sleep(PAUSA_ENTRE_LOTES_S)
                lote = {"id": f"{a.nome}-L{i}", "doador": str(a.jid),
                        "origem": list(a.pos), **dados}
                registar(a.nome, "lote_gerado", lote["id"],
                         categoria=lote["categoria"], kg=lote["kg"])
                # Cada lote tem o seu comportamento, que só vê as RESPOSTAS desse lote.
                a.add_behaviour(a.GerirLote(lote), M.template_respostas(lote["id"]))

    # -------------------------------------------------------------------------
    class GerirLote(OneShotBehaviour):
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
            """Oferece primeiro às ONGs; o excedente segue para o armazém."""
            a, lote = self.agent, self.lote
            kg_restantes = lote["kg"]

            # ---- 1. Negociar primeiro com as ONGs -------------------------
            for jid, _ in a.ongs:
                await self.send(M.criar(jid, "cfp", "oferta", lote["id"], {"lote": lote}))

            respostas = await M.esperar_respostas(
                self, "oferta", len(a.ongs), PRAZO_RESPOSTAS_S
            )
            propostas = []
            for r in respostas:
                if M.performativa(r) == "propose":
                    c = M.conteudo(r)
                    propostas.append({
                        "jid": M.quem(r), "kg": c["kg"],
                        "distancia": distancia(a.pos, tuple(c["pos"]))
                    })

            destino_ong = escolher_destino(propostas)
            for p in propostas:
                perf = "accept-proposal" if p is destino_ong else "reject-proposal"
                await self.send(M.criar(p["jid"], perf, "oferta", lote["id"], {}))

            if destino_ong is not None:
                kg_ong = min(destino_ong["kg"], kg_restantes)
                registar(a.nome, "destino_escolhido", lote["id"],
                         destino=destino_ong["jid"], kg=kg_ong)

                # A quantidade atribuída à ONG deixa de ser excedente.
                kg_restantes -= kg_ong
                await self._transportar(lote, destino_ong, kg_ong, "ong")

            # ---- 2. Oferecer o excedente ao armazém ------------------------
            if kg_restantes > 0 and a.armazens:
                # Nesta versão, utilizamos apenas o primeiro armazém.
                jid_arm, pos_arm = a.armazens[0]
                lote_excedente = {**lote, "kg": kg_restantes}

                await self.send(M.criar(
                    jid_arm, "cfp", "oferta", lote["id"], {"lote": lote_excedente}
                ))

                respostas_arm = await M.esperar_respostas(
                    self, "oferta", 1, PRAZO_RESPOSTAS_S
                )

                if respostas_arm:
                    r = respostas_arm[0]
                    if M.performativa(r) == "propose" and M.quem(r) == jid_arm:
                        kg_arm = min(M.conteudo(r)["kg"], kg_restantes)

                        if kg_arm > 0:
                            destino_arm = {
                                "jid": jid_arm, "kg": kg_arm,
                                "distancia": distancia(a.pos, pos_arm)
                            }
                            await self.send(M.criar(
                                jid_arm, "accept-proposal", "oferta", lote["id"], {}
                            ))
                            registar(a.nome, "destino_escolhido", lote["id"],
                                     destino=jid_arm, kg=kg_arm)

                            kg_restantes -= kg_arm
                            await self._transportar(lote, destino_arm, kg_arm, "armazem")
                        else:
                            # Uma proposta de 0 kg não é válida.
                            await self.send(M.criar(
                                jid_arm, "reject-proposal", "oferta", lote["id"], {}
                            ))

            if kg_restantes > 0:
                registar(a.nome, "sem_destino", lote["id"],
                         motivo="excedente sem capacidade", kg=kg_restantes)

        async def _transportar(self, lote, destino, kg, tipo_destino):
            """Contrata um resgatador e aguarda a confirmação de uma entrega."""
            a = self.agent
            lote_a_levar = {**lote, "kg": kg}

            # ---- 3. Pedir propostas aos resgatadores -----------------------
            for jid in a.resgatadores:
                await self.send(M.criar(
                    jid, "cfp", "resgate", lote["id"],
                    {"lote": lote_a_levar, "destino": destino["jid"],
                     "pos_destino": list(self._pos_destino(destino["jid"]))}
                ))

            respostas = await M.esperar_respostas(
                self, "resgate", len(a.resgatadores), PRAZO_RESPOSTAS_S
            )
            propostas = [
                {"jid": M.quem(r), "tempo_min": M.conteudo(r)["tempo_min"]}
                for r in respostas if M.performativa(r) == "propose"
            ]
            escolhido = escolher_resgatador(propostas)

            for p in propostas:
                perf = "accept-proposal" if p is escolhido else "reject-proposal"
                await self.send(M.criar(p["jid"], perf, "resgate", lote["id"], {}))

            if escolhido is None:
                registar(a.nome, "sem_resgatador", lote["id"],
                         motivo="ninguém pôde levar", kg=kg)
                await self._cancelar_oferta(destino["jid"], lote["id"])
                return False

            registar(a.nome, "resgatador_escolhido", lote["id"],
                     resgatador=escolhido["jid"],
                     tempo_min=escolhido["tempo_min"])

            # ---- 4. Esperar a confirmação da entrega ----------------------
            prazo = escolhido["tempo_min"] * ESCALA_S * 3 + PRAZO_RESPOSTAS_S
            fim = await M.esperar_respostas(
                self, "resgate", 1, prazo,
                performativas={"inform", "failure"}
            )

            if fim and M.performativa(fim[0]) == "inform":
                resultado = M.conteudo(fim[0]).get("resultado")
                if resultado == "confirmada":
                    registar(a.nome, "lote_entregue", lote["id"], kg=kg,
                             destino=destino["jid"], tipo_destino=tipo_destino,
                             resultado=resultado)
                    return True

            motivo = "entrega recusada ou falhada" if fim else "sem resposta"
            registar(a.nome, "entrega_falhou", lote["id"],
                     motivo=motivo, kg=kg)
            await self._cancelar_oferta(destino["jid"], lote["id"])
            return False


        async def _cancelar_oferta(self, jid_ong: str, lote_id: str):
            """CancelarOferta: a ONG liberta os kg que tinha reservado para este lote."""
            await self.send(M.criar(jid_ong, "cancel", "oferta", lote_id, {}))

        
        def _pos_destino(self, jid: str):
            """Devolve a posição de uma ONG ou de um armazém conhecido."""

            # Procurar o destino entre todas as ONGs e armazéns conhecidos.
            destinos = self.agent.ongs + self.agent.armazens

            return next(pos for j, pos in destinos if j == jid)

