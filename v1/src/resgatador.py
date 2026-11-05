"""
Resgatador: papel RESGATADOR (transportador).

Voluntário com veículo. Responde aos pedidos de transporte (Contract Net):
propõe um tempo se conseguir fazer o serviço, recusa se não conseguir. Se for
escolhido, vai buscar o lote ao restaurante e entrega-o ao destino.

Regras de segurança do guia que já aparecem aqui:
  - nunca aceita mais que a capacidade;
  - nunca aceita lote refrigerado ou congelado sem caixa térmica;
  - só leva um lote de cada vez.
"""
from __future__ import annotations

from spade.agent import Agent
from spade.behaviour import CyclicBehaviour, OneShotBehaviour

from . import mensagens as M
from .config import PRAZO_RESPOSTAS_S, distancia
from .registo import registar

TEMPO_DE_MANUSEIO_MIN = 5       # minutos para carregar ou descarregar
TEMPERATURA_COM_CAIXA_C = 3     # temperatura do lote se tiver caixa térmica
TEMPERATURA_SEM_CAIXA_C = 12    # (usada a partir da Fatia 2, para a cadeia de frio)


class ResgatadorAgent(Agent):
    def __init__(self, jid, senha, pos, capacidade_kg, caixa_termica, velocidade_km_min):
        super().__init__(jid, senha)
        self.pos = pos
        self.capacidade_kg = capacidade_kg
        self.caixa_termica = caixa_termica
        self.velocidade = velocidade_km_min
        self.ocupado = False
        self.pedidos: dict[str, dict] = {}   # lote -> detalhes do cfp a que nos propusemos
        self.nome = str(jid).split("@")[0]

    async def setup(self):
        self.add_behaviour(self.Inbox(), M.template_pedidos())

    # ---- EstimarUtilidade: atividade interna (sublinhada no guia) -----------
    def estimar_minutos(self, origem, destino) -> float:
        km = distancia(self.pos, tuple(origem)) + distancia(tuple(origem), tuple(destino))
        return km / self.velocidade + 2 * TEMPO_DE_MANUSEIO_MIN

    def recusa_porque(self, lote: dict) -> str | None:
        """Devolve o motivo para NÃO levar o lote, ou None se puder levar."""
        if self.ocupado:
            return "ocupado"
        if lote["kg"] > self.capacidade_kg:
            return "acima da capacidade"
        if lote["categoria"] in ("refrigerado", "congelado") and not self.caixa_termica:
            return "sem caixa térmica"
        return None

    # -------------------------------------------------------------------------
    class Inbox(CyclicBehaviour):
        async def run(self):
            msg = await self.receive(timeout=1)
            if msg is None or M.protocolo(msg) != "resgate":
                return
            a = self.agent
            perf, lote_id = M.performativa(msg), M.lote(msg)

            # ---- ContratarResgate: pedem-nos uma proposta -------------------
            if perf == "cfp":
                c = M.conteudo(msg)
                motivo = a.recusa_porque(c["lote"])
                if motivo:
                    registar(a.nome, "resgate_recusado", lote_id, motivo=motivo)
                    await self.send(M.responder(msg, "refuse", {"motivo": motivo}))
                    return
                tempo = round(a.estimar_minutos(c["lote"]["origem"], c["pos_destino"]), 1)
                registar(a.nome, "resgate_proposto", lote_id, tempo_min=tempo)
                a.pedidos[lote_id] = c      # guardamos os detalhes para o caso de sermos escolhidos
                await self.send(M.responder(msg, "propose", {"tempo_min": tempo}))
                # NOTA para a Fatia 4: entre o propose e o accept outro cfp pode chegar e
                # nós voltaríamos a propor. Aqui basta tratar isso no accept (abaixo).

            # ---- fomos escolhidos ------------------------------------------
            elif perf == "accept-proposal":
                if a.ocupado or lote_id not in a.pedidos:
                    # Já fomos escolhidos por outro lote: desistimos e avisamos (failure).
                    await self.send(M.responder(msg, "failure", {"motivo": "ocupado"}))
                    return
                a.ocupado = True
                a.add_behaviour(a.Entrega(msg), M.template_respostas(lote_id))

            elif perf == "reject-proposal":
                registar(a.nome, "resgate_nao_escolhido", lote_id)

    # -------------------------------------------------------------------------
    class Entrega(OneShotBehaviour):
        """Vai ao restaurante, vai à ONG, entrega e avisa o restaurante."""

        def __init__(self, msg_accept):
            super().__init__()
            self.accept = msg_accept

        async def run(self):
            a = self.agent
            lote_id = M.lote(self.accept)
            restaurante = M.quem(self.accept)
            try:
                dados = a.pedidos.pop(lote_id)
                lote, destino, pos_destino = dados["lote"], dados["destino"], dados["pos_destino"]

                # 1) ir buscar ao restaurante
                await M.dormir_minutos(distancia(a.pos, tuple(lote["origem"])) / a.velocidade
                                       + TEMPO_DE_MANUSEIO_MIN)
                a.pos = tuple(lote["origem"])
                registar(a.nome, "lote_recolhido", lote_id, kg=lote["kg"])

                # 2) levar ao destino
                await M.dormir_minutos(distancia(a.pos, tuple(pos_destino)) / a.velocidade
                                       + TEMPO_DE_MANUSEIO_MIN)
                a.pos = tuple(pos_destino)

                # 3) EntregarLote: dizemos o que trazemos; a ONG inspeciona e responde
                temperatura = TEMPERATURA_COM_CAIXA_C if a.caixa_termica else TEMPERATURA_SEM_CAIXA_C
                await self.send(M.criar(destino, "inform", "entrega", lote_id,
                                        {"lote": lote, "temperatura_c": temperatura}))
                resposta = await M.esperar_respostas(self, "entrega", 1, PRAZO_RESPOSTAS_S)
                resultado = M.conteudo(resposta[0]).get("resultado") if resposta else "sem resposta"

                # 4) avisar o restaurante (fecha o Contract Net)
                await self.send(M.criar(restaurante, "inform", "resgate", lote_id,
                                        {"resultado": resultado}, fase="resposta"))
            finally:
                a.ocupado = False
