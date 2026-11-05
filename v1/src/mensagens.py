"""
Mensagens entre agentes.

Cada mensagem SPADE leva:
  - performativa FIPA   (cfp, propose, refuse, accept-proposal, reject-proposal, inform, failure)
  - protocolo           ("oferta", "resgate" ou "entrega": os 3 protocolos da Fatia 1)
  - lote                (id do lote a que a conversa se refere)
  - fase                ("pedido" = quem inicia a conversa; "resposta" = quem responde)
  - corpo               (um dicionário Python convertido em JSON)

Para que serve a "fase"? No SPADE, uma mensagem recebida é entregue a TODOS os
comportamentos cujo Template combina com ela. Se dois comportamentos do mesmo
agente combinarem, ambos recebem a mesma mensagem e fica confuso. Separando
"pedido" e "resposta" garantimos que:
  - a caixa de entrada geral do agente (Inbox) só vê PEDIDOS;
  - o comportamento que espera respostas de um lote só vê RESPOSTAS desse lote.
"""
from __future__ import annotations

import asyncio
import json
import time

from spade.message import Message
from spade.template import Template

ONTOLOGIA = "food-rescue"


def criar(para: str, performativa: str, protocolo: str, lote_id: str,
          conteudo: dict, fase: str = "pedido") -> Message:
    """Cria uma mensagem nova."""
    msg = Message(to=str(para), thread=lote_id)
    msg.set_metadata("performative", performativa)
    msg.set_metadata("ontologia", ONTOLOGIA)
    msg.set_metadata("protocolo", protocolo)
    msg.set_metadata("lote", lote_id)
    msg.set_metadata("fase", fase)
    msg.body = json.dumps(conteudo)
    return msg


def responder(msg: Message, performativa: str, conteudo: dict) -> Message:
    """Cria a resposta a uma mensagem recebida (mesmo protocolo e mesmo lote)."""
    return criar(str(msg.sender), performativa, protocolo(msg), lote(msg),
                 conteudo, fase="resposta")


# ---- Ler uma mensagem recebida ---------------------------------------------
def conteudo(msg: Message) -> dict:
    try:
        return json.loads(msg.body or "{}")
    except json.JSONDecodeError:
        return {}


def performativa(msg: Message) -> str:
    return msg.get_metadata("performative")


def protocolo(msg: Message) -> str:
    return msg.get_metadata("protocolo")


def lote(msg: Message) -> str:
    return msg.get_metadata("lote")


def quem(msg: Message) -> str:
    """JID de quem enviou, sem a parte do recurso (ex.: 'ong1@localhost')."""
    return str(msg.sender).split("/")[0]


# ---- Templates (filtros de mensagens) --------------------------------------
def template_pedidos() -> Template:
    """Para a Inbox geral de cada agente: só mensagens que abrem uma conversa."""
    return Template(metadata={"ontologia": ONTOLOGIA, "fase": "pedido"})


def template_respostas(lote_id: str) -> Template:
    """Para um comportamento que espera respostas sobre UM lote."""
    return Template(metadata={"ontologia": ONTOLOGIA, "fase": "resposta", "lote": lote_id})


# ---- Esperar respostas (o "reply-by" do Contract Net) ----------------------
async def esperar_respostas(comportamento, protocolo_esperado: str, quantas: int,
                            prazo_s: float, performativas: set[str] | None = None) -> list[Message]:
    """
    Espera até `quantas` respostas do protocolo indicado, ou até o prazo acabar.
    Respostas que não chegam a tempo são simplesmente ignoradas.
    `performativas` (opcional) filtra por tipo, útil para descartar propostas
    atrasadas de uma fase anterior.
    """
    recebidas: list[Message] = []
    limite = time.monotonic() + prazo_s
    while len(recebidas) < quantas:
        restante = limite - time.monotonic()
        if restante <= 0:
            break
        msg = await comportamento.receive(timeout=restante)
        if msg is None:
            break
        if protocolo(msg) == protocolo_esperado and (
                performativas is None or performativa(msg) in performativas):
            recebidas.append(msg)
    return recebidas


async def dormir_minutos(minutos_simulados: float) -> None:
    """Passa tempo simulado (ver ESCALA_S em config.py)."""
    from .config import ESCALA_S
    await asyncio.sleep(minutos_simulados * ESCALA_S)
