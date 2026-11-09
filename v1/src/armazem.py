
"""
Armazém: papel ARMAZÉM (destino de armazenamento).

Recebe os lotes, ou partes de lotes, que não foram atribuídos às ONGs.
Tem três zonas de armazenamento: seco, refrigerado e congelado.

Cada zona tem uma capacidade máxima. O armazém controla os kg já
armazenados e os kg reservados para entregas ainda não realizadas.

Nesta fase, definimos apenas os atributos do agente.
Os comportamentos de negociação e receção serão adicionados depois.
"""

from spade.agent import Agent
from spade.behaviour import CyclicBehaviour

from . import mensagens as M
from .registo import registar
from .config import TEMP_MAX_REFRIGERADO_C


class ArmazemAgent(Agent):
    def __init__(self, jid, senha, pos, zonas):
        super().__init__(jid, senha)
    
        # Identificação e localização do armazém.
        self.nome = str(jid).split("@")[0]
        self.pos = pos

        # Capacidade máxima de cada zona (em kg).
        self.capacidades_kg = dict(zonas)

        # Quantidade atualmente armazenada em cada zona.
        self.armazenado_kg = {
            categoria: 0.0 for categoria in zonas
        }

        # Espaço reservado para entregas ainda não recebidas.
        self.reservado_kg = {
            categoria: 0.0 for categoria in zonas
        }

        # Reservas: identificador do lote -> (categoria, kg).
        self.reservas = {}

        # Inventário: identificador do lote -> dados do lote recebido.
        self.inventario = {}

    def livre_kg(self, categoria: str) -> float:
            """Devolve a capacidade disponível na zona da categoria indicada."""
    
            # Se não existir uma zona para esta categoria, não podemos guardar o lote.
            if categoria not in self.capacidades_kg:
                return 0.0
    
            # Capacidade disponível = capacidade máxima - armazenado - reservado.
            return (self.capacidades_kg[categoria]
                    - self.armazenado_kg[categoria]
                    - self.reservado_kg[categoria])

    
    async def setup(self):
        # A Inbox recebe os pedidos enviados ao armazém.
        self.add_behaviour(self.Inbox(), M.template_pedidos())

    
    class Inbox(CyclicBehaviour):
        async def run(self):
            msg = await self.receive(timeout=1)

            if msg is None:
                return

            
            # Aceitar mensagens de oferta e de entrega.
            proto = M.protocolo(msg)

            if proto not in ("oferta", "entrega"):
                return

            a = self.agent
            lote_id = M.lote(msg)
            perf = M.performativa(msg)

            # ---- Receber uma nova oferta ---------------------------------
            if proto == "oferta" and perf == "cfp":
                lote = M.conteudo(msg)["lote"]
                categoria = lote["categoria"]

                # Calcular quantos kg podemos guardar na zona correspondente.
                kg = min(lote["kg"], a.livre_kg(categoria))

                if kg <= 0:
                    registar(a.nome, "armazem_recusou", lote_id,
                             motivo="sem capacidade na zona")
                    await self.send(M.responder(
                        msg, "refuse", {"motivo": "sem capacidade na zona"}))
                    return

                # Reservar espaço para não prometer a mesma capacidade
                # a vários restaurantes.
                a.reservas[lote_id] = (categoria, kg)
                a.reservado_kg[categoria] += kg

                registar(a.nome, "armazem_propos", lote_id, kg=kg)
                await self.send(M.responder(
                    msg, "propose", {"kg": kg, "pos": list(a.pos)}))

            # ---- Proposta aceite pelo restaurante -------------------------
            elif proto == "oferta" and perf == "accept-proposal":
                # Mantemos a reserva até o lote ser entregue ou cancelado.
                registar(a.nome, "destino_confirmado", lote_id)

            # ---- Proposta rejeitada ou entrega cancelada ------------------
            elif proto == "oferta" and perf in ("reject-proposal", "cancel"):

                # Retirar a reserva correspondente ao lote.
                reserva = a.reservas.pop(lote_id, None)

                if reserva is not None:
                    categoria, kg = reserva
                    a.reservado_kg[categoria] -= kg

                registar(a.nome, "reserva_libertada", lote_id,
                         motivo=perf)

            
            # ---- Receber e inspecionar um lote entregue --------------------
            elif proto == "entrega" and perf == "inform":
                c = M.conteudo(msg)
                lote = c["lote"]
                categoria = lote["categoria"]

                # Recuperar a reserva e libertar os kg reservados.
                reserva = a.reservas.pop(lote_id, None)

                if reserva is None:
                    motivo = "lote sem reserva"
                else:
                    categoria_reservada, kg_reservados = reserva
                    a.reservado_kg[categoria_reservada] -= kg_reservados

                    # Verificar a categoria, a quantidade e a temperatura.
                    if categoria != categoria_reservada:
                        motivo = "categoria diferente da reserva"
                    elif lote["kg"] > kg_reservados + 1e-9:
                        motivo = "kg acima do reservado"
                    elif (categoria == "refrigerado"
                          and c["temperatura_c"] > TEMP_MAX_REFRIGERADO_C):
                        motivo = "quebra da cadeia de frio"
                    elif (categoria == "congelado"
                            and c["temperatura_c"] > -18):
                        motivo = "quebra da cadeia de frio"
                    else:
                        motivo = None

                # Recusar a entrega se a inspeção detetar um problema.
                if motivo:
                    registar(a.nome, "entrega_recusada", lote_id, motivo=motivo)
                    await self.send(M.responder(
                        msg, "inform", {"resultado": "recusada", "motivo": motivo}))
                    return

                # Entrega aceite: atualizar a ocupação e o inventário.
                a.armazenado_kg[categoria] += lote["kg"]
                a.inventario[lote_id] = dict(lote)

                registar(a.nome, "entrega_aceita", lote_id,
                         categoria=categoria, kg=lote["kg"],
                         total_armazenado=a.armazenado_kg[categoria])

                # Confirmar ao resgatador que o lote foi recebido.
                await self.send(M.responder(
                    msg, "inform", {"resultado": "confirmada"}))


