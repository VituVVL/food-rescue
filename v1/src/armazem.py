"""
Armazém: papéis ARMAZENADOR e OPERADOR (Gaia: um agente pode desempenhar
vários papéis).

O armazém é um SERVIÇO de armazenagem, não um coordenador: não decide destinos
por ninguém, só decide o que entra (conforme o espaço da zona) e o que volta a
oferecer. Se o armazém falhar, os restaurantes continuam a oferecer direto às ONGs.

Ciclo de um lote no armazém:
  1. AnunciarOferta (respondente) -> propõe os kg que cabem na zona e RESERVA-os
  2. EntregarLote                  -> inspeciona; aceite, o lote fica na doca
  3. tarefa "receber" (operador)   -> da doca para a zona; se um lote de frio
                                      esperou mais que LIMITE_FORA_DO_FRIO_MIN
                                      na doca, estragou e é descartado
  4. tarefa "controlar" (operador) -> em cada ciclo, descarta o que passou da validade
  5. AnunciarOferta (doador)       -> volta a oferecer o estoque às ONGs que conhece
  6. tarefa "preparar" (operador)  -> separa o pedido
  7. ContratarResgate (doador)     -> mesmo código do restaurante (doador.py)

Operadores: não são agentes separados (decisão do grupo). São um recurso
interno: cada um tem um nome e as funções que sabe fazer, e só faz uma tarefa
de cada vez. Se não houver operador livre com a função certa, a tarefa espera.
É isto que limita a vazão do armazém.
"""
from __future__ import annotations

import asyncio

from spade.agent import Agent
from spade.behaviour import CyclicBehaviour, OneShotBehaviour, PeriodicBehaviour

from . import mensagens as M
from .config import (CICLO_ESTOQUE_MIN, DURACAO_TAREFAS_MIN, ESCALA_S,
                     LIMITE_FORA_DO_FRIO_MIN, TEMP_MAX_CONGELADO_C, TEMP_MAX_REFRIGERADO_C)
from .doador import ConduzirLote
from .registo import agora_min, registar

CATEGORIAS_DE_FRIO = ("refrigerado", "congelado")


class ArmazemAgent(Agent):
    def __init__(self, jid, senha, pos, zonas, operadores, ongs, resgatadores):
        """
        zonas        : {categoria: capacidade em kg}
        operadores   : lista de {"nome", "funcoes"} (funções: receber, controlar, preparar)
        ongs         : lista de (jid, pos) dos receptores a quem oferece o estoque
        resgatadores : lista de jids dos resgatadores que conhece
        """
        super().__init__(jid, senha)
        self.nome = str(jid).split("@")[0]
        self.pos = pos
        self.ongs = ongs
        self.resgatadores = resgatadores

        self.capacidades_kg = dict(zonas)
        self.armazenado_kg = {c: 0.0 for c in zonas}   # inclui o que está na doca
        self.reservado_kg = {c: 0.0 for c in zonas}    # prometido a entregas a caminho
        self.reservas: dict[str, tuple[str, float]] = {}   # lote -> (categoria, kg)

        # Estoque: id do item -> lote (com os kg que ainda há). O id do item é
        # diferente do id do lote original, para as conversas não se misturarem.
        self.inventario: dict[str, dict] = {}
        self.em_curso: set[str] = set()       # itens a ser oferecidos/enviados agora
        self.por_oferecer: set[str] = set()   # itens com novidade, a oferecer no próximo ciclo
        self.tarefas_ativas = 0               # receções e envios em andamento

        self.operadores = [{"nome": o["nome"], "funcoes": set(o["funcoes"]), "livre": True}
                           for o in operadores]
        self._operador_livre: asyncio.Condition | None = None

    # ---- capacidade ----------------------------------------------------------
    def livre_kg(self, categoria: str) -> float:
        """Capacidade disponível = capacidade - armazenado - reservado."""
        if categoria not in self.capacidades_kg:
            return 0.0
        return (self.capacidades_kg[categoria]
                - self.armazenado_kg[categoria] - self.reservado_kg[categoria])

    def ocioso(self) -> bool:
        """Sem tarefas em andamento e sem estoque com novidade por oferecer."""
        return self.tarefas_ativas == 0 and not self.por_oferecer and not self.em_curso

    def tirar_do_estoque(self, item_id: str, kg: float, motivo: str | None = None):
        item = self.inventario[item_id]
        kg = min(kg, item["kg"])
        item["kg"] -= kg
        self.armazenado_kg[item["categoria"]] -= kg
        if motivo:
            registar(self.nome, "lote_descartado", item_id, kg=kg, motivo=motivo)
        if item["kg"] <= 1e-9:
            del self.inventario[item_id]
            self.por_oferecer.discard(item_id)

    # ---- operadores (papel OPERADOR) -----------------------------------------
    async def executar_tarefa(self, funcao: str, item_id: str, antes=None) -> bool:
        """
        Espera por um operador livre que saiba `funcao`, ocupa-o durante a duração
        da tarefa e liberta-o. `antes(espera_min)` é chamada quando o operador pega
        na tarefa; se devolver False, a tarefa termina logo (ex.: lote estragado).
        """
        pedido_min = agora_min()
        async with self._operador_livre:
            await self._operador_livre.wait_for(
                lambda: any(o["livre"] and funcao in o["funcoes"] for o in self.operadores))
            op = next(o for o in self.operadores if o["livre"] and funcao in o["funcoes"])
            op["livre"] = False
        try:
            espera = round(agora_min() - pedido_min, 1)
            registar(self.nome, "tarefa_iniciada", item_id, operador=op["nome"],
                     funcao=funcao, espera_min=espera)
            if antes is not None and not antes(espera):
                return False
            await M.dormir_minutos(DURACAO_TAREFAS_MIN[funcao])
            return True
        finally:
            async with self._operador_livre:
                op["livre"] = True
                self._operador_livre.notify_all()

    # -------------------------------------------------------------------------
    async def setup(self):
        self._operador_livre = asyncio.Condition()
        self.add_behaviour(self.Inbox(), M.template_pedidos())
        self.add_behaviour(self.CicloEstoque(period=CICLO_ESTOQUE_MIN * ESCALA_S))

    # ---- pedidos que chegam (papel ARMAZENADOR, respondente) ------------------
    class Inbox(CyclicBehaviour):
        async def run(self):
            msg = await self.receive(timeout=1)
            if msg is None:
                return
            a = self.agent
            proto, perf, lote_id = M.protocolo(msg), M.performativa(msg), M.lote(msg)

            # ---- AnunciarOferta: alguém quer guardar um lote ----------------
            if proto == "oferta" and perf == "cfp":
                lote = M.conteudo(msg)["lote"]
                kg = min(lote["kg"], a.livre_kg(lote["categoria"]))
                if kg <= 0:
                    registar(a.nome, "armazem_recusou", lote_id, motivo="sem capacidade na zona")
                    await self.send(M.responder(msg, "refuse", {"motivo": "sem capacidade na zona"}))
                    return
                # Reservar já, para não prometer o mesmo espaço a dois doadores.
                a.reservas[lote_id] = (lote["categoria"], kg)
                a.reservado_kg[lote["categoria"]] += kg
                registar(a.nome, "armazem_propos", lote_id, kg=kg)
                await self.send(M.responder(msg, "propose", {"kg": kg, "pos": list(a.pos)}))

            elif proto == "oferta" and perf == "accept-proposal":
                registar(a.nome, "destino_confirmado", lote_id)

            elif proto == "oferta" and perf in ("reject-proposal", "cancel"):
                reserva = a.reservas.pop(lote_id, None)
                if reserva:
                    a.reservado_kg[reserva[0]] -= reserva[1]
                registar(a.nome, "reserva_libertada", lote_id, motivo=perf)

            # ---- EntregarLote: inspeção na passagem de mão -------------------
            elif proto == "entrega" and perf == "inform":
                c = M.conteudo(msg)
                lote = c["lote"]
                reserva = a.reservas.pop(lote_id, None)
                if reserva:
                    a.reservado_kg[reserva[0]] -= reserva[1]
                motivo = self.inspecionar(lote, c["temperatura_c"], reserva)
                if motivo:
                    registar(a.nome, "entrega_recusada", lote_id, motivo=motivo)
                    await self.send(M.responder(msg, "inform", {"resultado": "recusada", "motivo": motivo}))
                    return

                # Aceite: o espaço passa de reservado a ocupado e o lote fica na doca.
                a.armazenado_kg[lote["categoria"]] += lote["kg"]
                registar(a.nome, "entrega_aceita", lote_id, categoria=lote["categoria"],
                         kg=lote["kg"], total_armazenado=a.armazenado_kg[lote["categoria"]])
                await self.send(M.responder(msg, "inform", {"resultado": "confirmada"}))
                a.tarefas_ativas += 1
                a.add_behaviour(a.Receber(lote))

        @staticmethod
        def inspecionar(lote: dict, temperatura_c: float, reserva) -> str | None:
            """InspecionarLote. Devolve o motivo da recusa, ou None se estiver tudo bem."""
            if reserva is None:
                return "lote sem reserva"
            categoria, kg = reserva
            if lote["categoria"] != categoria:
                return "categoria diferente da reserva"
            if lote["kg"] > kg + 1e-9:
                return "kg acima do reservado"
            if categoria == "refrigerado" and temperatura_c > TEMP_MAX_REFRIGERADO_C:
                return "quebra da cadeia de frio"
            if categoria == "congelado" and temperatura_c > TEMP_MAX_CONGELADO_C:
                return "quebra da cadeia de frio"
            return None

    # ---- tarefa "receber": da doca para a zona --------------------------------
    class Receber(OneShotBehaviour):
        def __init__(self, lote: dict):
            super().__init__()
            self.lote = lote

        async def run(self):
            a, lote = self.agent, self.lote
            item_id = f"{lote['id']}-A"          # nova identidade dentro do armazém
            a.inventario[item_id] = {**lote, "id": item_id}
            try:
                def ainda_seguro(espera_min: float) -> bool:
                    if lote["categoria"] in CATEGORIAS_DE_FRIO and espera_min > LIMITE_FORA_DO_FRIO_MIN:
                        a.tirar_do_estoque(item_id, lote["kg"], motivo="esperou demais fora do frio")
                        return False
                    return True

                if await a.executar_tarefa("receber", item_id, antes=ainda_seguro):
                    registar(a.nome, "lote_armazenado", item_id, categoria=lote["categoria"],
                             kg=lote["kg"])
                    a.por_oferecer.add(item_id)
            finally:
                a.tarefas_ativas -= 1

    # ---- ciclo: "controlar" e voltar a oferecer o estoque ----------------------
    class CicloEstoque(PeriodicBehaviour):
        async def run(self):
            a = self.agent
            livres = [i for i in a.inventario if i not in a.em_curso]
            if not livres:
                return

            # Controlar estoque: descartar o que passou da validade.
            await a.executar_tarefa("controlar", a.nome)
            agora = agora_min()
            for item_id in livres:
                item = a.inventario.get(item_id)
                if item and agora > item["criado_min"] + item["validade_min"]:
                    a.tirar_do_estoque(item_id, item["kg"], motivo="validade expirada")

            # Voltar a oferecer o que tem novidade (acabou de chegar, ou sobrou).
            for item_id in list(a.por_oferecer):
                if item_id in a.inventario and item_id not in a.em_curso:
                    a.por_oferecer.discard(item_id)
                    a.em_curso.add(item_id)
                    a.tarefas_ativas += 1
                    a.add_behaviour(a.OferecerEstoque(item_id), M.template_respostas(item_id))

    # ---- o armazém como DOADOR do seu estoque ----------------------------------
    class OferecerEstoque(ConduzirLote):
        def __init__(self, item_id: str):
            super().__init__()
            self.item_id = item_id

        async def run(self):
            a, item_id = self.agent, self.item_id
            try:
                item = a.inventario[item_id]
                oferta = {**item, "doador": str(a.jid), "origem": list(a.pos)}
                destino = await self.anunciar_oferta(oferta, a.ongs)
                if destino is None:
                    registar(a.nome, "estoque_sem_procura", item_id, kg=item["kg"])
                    return          # fica em estoque até haver novidade ou expirar

                await a.executar_tarefa("preparar", item_id)
                entregue = await self.contratar_resgate({**oferta, "kg": destino["kg"]},
                                                        destino, "ong")
                if entregue:
                    a.tirar_do_estoque(item_id, destino["kg"])
                if item_id in a.inventario:
                    a.por_oferecer.add(item_id)   # sobrou ou falhou: tentar no próximo ciclo
            finally:
                a.em_curso.discard(item_id)
                a.tarefas_ativas -= 1
