"""
Esquema das mensagens (entregável "message schemas").

Todas as mensagens são FIPA-ACL sobre XMPP (SPADE) com:
  metadata.performative : cfp | propose | refuse | accept-proposal | reject-proposal
                          | request | agree | failure | inform | cancel
  metadata.ontology     : "food-rescue"
  metadata.protocol     : offer-cnp | transport-cnp | deposit | delivery
  metadata.dir          : "init"  -> mensagem do iniciador da conversa (vai para a Inbox)
                          "reply" -> resposta ao iniciador (vai para o comportamento da conversa)
  thread                : identificador da conversa = "<item_id>@<iniciador>"
  body                  : JSON (ver exemplos abaixo)

Protocolos:
  offer-cnp      Doador --cfp(item)--> Recetores ; Recetor --propose{kg,urgency,received}|refuse-->
                 Doador --accept-proposal / reject-proposal--> Recetor
  deposit        Doador --request(item)--> Frigorífico ; --agree|refuse-->
  transport-cnp  Doador --cfp(item,from,to)--> Voluntários ; --propose{eta,km}|refuse-->
                 Doador --accept/reject--> ; Voluntário --inform{done}|failure--> Doador
  delivery       Voluntário --inform(item, checks)--> Recetor/Frigorífico
  (cancel)       Doador --cancel--> Recetor/Frigorífico (liberta a reserva)
"""
from __future__ import annotations

import json

from spade.message import Message
from spade.template import Template

from .world import M, RNG

ONTOLOGY = "food-rescue"


def make(to: str, performative: str, protocol: str, thread: str,
         direction: str, content: dict) -> Message:
    msg = Message(to=str(to), thread=thread)
    msg.set_metadata("performative", performative)
    msg.set_metadata("ontology", ONTOLOGY)
    msg.set_metadata("protocol", protocol)
    msg.set_metadata("dir", direction)
    msg.body = json.dumps(content)
    return msg


def reply(msg: Message, performative: str, content: dict) -> Message:
    """Resposta na mesma conversa (dir=reply)."""
    return make(str(msg.sender), performative, msg.get_metadata("protocol"),
                msg.thread, "reply", content)


def body(msg: Message) -> dict:
    try:
        return json.loads(msg.body or "{}")
    except json.JSONDecodeError:
        return {}


def perf(msg: Message) -> str:
    return msg.get_metadata("performative")


async def send(behaviour, msg: Message, loss: float) -> None:
    """Envio com perda simulada de mensagens (cenário S3)."""
    if RNG.random() < loss:
        M.msgs_lost += 1
        return
    M.msgs_sent += 1
    await behaviour.send(msg)


def inbox_template() -> Template:
    return Template(metadata={"dir": "init", "ontology": ONTOLOGY})


def conversation_template(thread: str) -> Template:
    return Template(thread=thread, metadata={"dir": "reply", "ontology": ONTOLOGY})
