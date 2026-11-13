"""
Ponto de entrada da simulação (Fatias 1 a 3).

    python -m v1.src.main       (a partir da pasta raiz do projeto)
ou, no PyCharm, botão direito neste ficheiro -> Run 'main'.

Cria os agentes, deixa-os trabalhar até todos os lotes terminarem e mostra um
resumo. O servidor XMPP embutido do SPADE é arrancado automaticamente: NÃO é
preciso correr `spade run` noutro terminal.
"""
from __future__ import annotations

import asyncio
import multiprocessing
import os
import sys
import traceback
from pathlib import Path

# Permite correr este ficheiro diretamente (PyCharm) além de `python -m v1.src.main`.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # pasta raiz do projeto
    __package__ = "v1.src"

import spade

from . import config as C
from . import registo
from .ong import OngAgent
from .restaurante import RestauranteAgent
from .resgatador import ResgatadorAgent
from .armazem import ArmazemAgent

TEMPO_MAXIMO_S = 120    # se algo ficar preso, a corrida acaba ao fim disto


def jid(nome: str) -> str:
    return f"{nome}@{C.DOMINIO}"


async def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")   # acentos corretos na consola do Windows
    except Exception:
        pass
    restaurantes_ativos = [len(C.RESTAURANTES)]

    def contar_restaurante():
        restaurantes_ativos[0] -= 1

    # --- criar os agentes ----------------------------------------------------
    ongs = [OngAgent(jid(d["nome"]), C.SENHA, d["pos"], d["categorias"], d["necessidade_kg"])
            for d in C.ONGS]
    resgatadores = [ResgatadorAgent(jid(d["nome"]), C.SENHA, d["pos"], d["capacidade_kg"],
                                    d["caixa_termica"], d["velocidade_km_min"])
                    for d in C.RESGATADORES]

    # Cada agente só conhece os pares que lhe passamos aqui (não há diretório
    # central). O armazém conhece todos os receptores; um restaurante só os que
    # estão dentro de RAIO_DOADOR_KM.
    resgatadores_conhecidos = [str(r.jid) for r in resgatadores]
    todas_ongs = [(str(o.jid), o.pos) for o in ongs]
    armazens = [ArmazemAgent(jid(d["nome"]), C.SENHA, d["pos"], d["zonas"], d["operadores"],
                             todas_ongs, resgatadores_conhecidos)
                for d in C.ARMAZENS]
    armazens_conhecidos = [(str(a.jid), a.pos) for a in armazens]

    restaurantes = []
    for d in C.RESTAURANTES:
        perto = [(j, p) for j, p in todas_ongs if C.distancia(d["pos"], p) <= C.RAIO_DOADOR_KM]
        restaurantes.append(RestauranteAgent(jid(d["nome"]), C.SENHA, d["pos"], perto,
                                             resgatadores_conhecidos, armazens_conhecidos,
                                             C.LOTES, contar_restaurante))

    # --- arrancar: primeiro quem responde, por fim quem inicia ---------------
    todos = ongs + resgatadores + armazens + restaurantes
    for a in todos:
        await a.start(auto_register=True)
    print(f"{len(todos)} agentes a correr.\n", flush=True)

    # --- esperar o fim ------------------------------------------------------
    # A corrida acaba quando todos os restaurantes terminaram os seus lotes E
    # os armazéns já não têm nada em andamento (receções, envios, estoque novo).
    async def fim():
        while not (restaurantes_ativos[0] == 0 and all(a.ocioso() for a in armazens)):
            await asyncio.sleep(0.5)
    try:
        await asyncio.wait_for(fim(), timeout=TEMPO_MAXIMO_S)
    except asyncio.TimeoutError:
        print("\nAVISO: tempo máximo atingido; algum lote ficou preso.", flush=True)

    estoque = sum(i["kg"] for a in armazens for i in a.inventario.values())
    gerados = [{"kg": d["kg"]} for d in C.LOTES] * len(C.RESTAURANTES)
    print("\nResumo:", registo.resumo(gerados, estoque), flush=True)

    for a in todos:                      # parar com limite de tempo (no Windows pode ficar pendurado)
        try:
            await asyncio.wait_for(a.stop(), timeout=3)
        except Exception:
            pass


def sair(codigo: int) -> None:
    """Termina o processo E o servidor XMPP embutido (senão fica a ocupar a porta 5222)."""
    for filho in multiprocessing.active_children():
        filho.kill()
    sys.stdout.flush()
    os._exit(codigo)


async def seguro():
    # O spade.run esconde exceções do main; por isso mostramo-las aqui.
    try:
        await main()
    except Exception:
        traceback.print_exc()
        sair(1)
    sair(0)


if __name__ == "__main__":
    spade.run(seguro(), embedded_xmpp_server=True)
