"""
Papel DOADOR, partilhado pelo Restaurante e pelo Armazém.

Quem tem um lote conduz duas conversas:

  1. AnunciarOferta   -> pergunta a candidatos (ONGs, armazém) quem quer o lote
  2. ContratarResgate -> pergunta aos resgatadores quem leva (Contract Net) e
                         espera o resultado da entrega

O Restaurante e o Armazém usam exatamente o mesmo código: o Armazém, quando
volta a oferecer o estoque, faz de doador (decisão do grupo: reaproveitar o
ContratarResgate em vez de criar um protocolo de retirada).
"""
from __future__ import annotations

from spade.behaviour import OneShotBehaviour

from . import mensagens as M
from .config import ESCALA_S, PRAZO_RESPOSTAS_S, distancia
from .registo import registar


# =============================================================================
# DECISÕES DO DOADOR
# Funções pequenas e separadas de propósito: é aqui que o grupo mexe para
# mudar o comportamento (urgência, equidade, reputação, ...).
# =============================================================================
def escolher_destino(propostas: list[dict]) -> dict | None:
    """
    Cada proposta é {"jid", "kg", "pos", "distancia"}. Regra atual: quem aceita
    mais kg; em empate, a mais perto. Devolve None se não houver propostas.
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
class ConduzirLote(OneShotBehaviour):
    """
    Base dos comportamentos que conduzem a vida de UM lote do lado de quem o tem.
    Tem de ser adicionada com M.template_respostas(lote_id), para só ver as
    respostas desse lote. O agente precisa de `nome`, `pos` e `resgatadores`.
    """

    # ---- AnunciarOferta ----------------------------------------------------
    async def anunciar_oferta(self, lote: dict, candidatos: list[tuple[str, tuple]]) -> dict | None:
        """
        Envia cfp a cada candidato (jid, pos), escolhe uma proposta, avisa todos
        (accept ao escolhido, reject aos outros, que assim libertam a reserva)
        e devolve {"jid", "kg", "pos", "distancia"} ou None.
        """
        if not candidatos:
            return None
        a = self.agent
        for jid, _ in candidatos:
            await self.send(M.criar(jid, "cfp", "oferta", lote["id"], {"lote": lote}))
        respostas = await M.esperar_respostas(self, "oferta", len(candidatos), PRAZO_RESPOSTAS_S)

        propostas = []
        for r in respostas:
            if M.performativa(r) == "propose":
                c = M.conteudo(r)
                pos = tuple(c["pos"])
                propostas.append({"jid": M.quem(r), "kg": min(c["kg"], lote["kg"]),
                                  "pos": pos, "distancia": distancia(a.pos, pos)})
        escolhido = escolher_destino([p for p in propostas if p["kg"] > 0])

        for p in propostas:
            perf = "accept-proposal" if p is escolhido else "reject-proposal"
            await self.send(M.criar(p["jid"], perf, "oferta", lote["id"], {}))
        if escolhido:
            registar(a.nome, "destino_escolhido", lote["id"],
                     destino=escolhido["jid"], kg=escolhido["kg"])
        return escolhido

    async def cancelar_oferta(self, jid_destino: str, lote_id: str):
        """CancelarOferta: o destino liberta os kg que tinha reservado."""
        await self.send(M.criar(jid_destino, "cancel", "oferta", lote_id, {}))

    # ---- ContratarResgate + espera da entrega -------------------------------
    async def contratar_resgate(self, lote: dict, destino: dict, tipo_destino: str) -> bool:
        """
        Contract Net com os resgatadores para levar `lote` (já com os kg certos)
        até `destino`. Devolve True só se o destino confirmar a entrega.
        Em caso de falha, cancela a oferta junto do destino.
        """
        a = self.agent
        for jid in a.resgatadores:
            await self.send(M.criar(jid, "cfp", "resgate", lote["id"],
                                    {"lote": lote, "destino": destino["jid"],
                                     "pos_destino": list(destino["pos"])}))
        respostas = await M.esperar_respostas(self, "resgate", len(a.resgatadores),
                                              PRAZO_RESPOSTAS_S, performativas={"propose", "refuse"})
        propostas = [{"jid": M.quem(r), "tempo_min": M.conteudo(r)["tempo_min"]}
                     for r in respostas if M.performativa(r) == "propose"]
        escolhido = escolher_resgatador(propostas)
        for p in propostas:
            perf = "accept-proposal" if p is escolhido else "reject-proposal"
            await self.send(M.criar(p["jid"], perf, "resgate", lote["id"], {}))

        if escolhido is None:
            registar(a.nome, "sem_resgatador", lote["id"], motivo="ninguém pôde levar", kg=lote["kg"])
            await self.cancelar_oferta(destino["jid"], lote["id"])
            return False
        registar(a.nome, "resgatador_escolhido", lote["id"],
                 resgatador=escolhido["jid"], tempo_min=escolhido["tempo_min"])

        # O resgatador responde com inform (resultado da entrega) ou failure.
        # Sem resposta até ao prazo, consideramos que não apareceu (Fatia 4: reabrir).
        prazo = escolhido["tempo_min"] * ESCALA_S * 3 + PRAZO_RESPOSTAS_S
        fim = await M.esperar_respostas(self, "resgate", 1, prazo,
                                        performativas={"inform", "failure"})
        if fim and M.performativa(fim[0]) == "inform":
            resultado = M.conteudo(fim[0]).get("resultado")
            if resultado == "confirmada":
                registar(a.nome, "lote_entregue", lote["id"], kg=lote["kg"],
                         destino=destino["jid"], tipo_destino=tipo_destino, resultado=resultado)
                return True
            motivo = f"entrega {resultado}"
        else:
            motivo = "failure" if fim else "sem resposta (no-show?)"
        registar(a.nome, "entrega_falhou", lote["id"], motivo=motivo, kg=lote["kg"])
        await self.cancelar_oferta(destino["jid"], lote["id"])
        return False
