"""
Ponto de entrada da Fatia 1.

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

TEMPO_MAXIMO_S = 60     # se algo ficar preso, a corrida acaba ao fim disto


def jid(nome: str) -> str:
    return f"{nome}@{C.DOMINIO}"


async def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")   # acentos corretos na consola do Windows
    except Exception:
        pass
    terminou = asyncio.Event()

    # --- criar os agentes ----------------------------------------------------
    ongs = [OngAgent(jid(d["nome"]), C.SENHA, d["pos"], d["categorias"], d["necessidade_kg"])
            for d in C.ONGS]
    resgatadores = [ResgatadorAgent(jid(d["nome"]), C.SENHA, d["pos"], d["capacidade_kg"],
                                    d["caixa_termica"], d["velocidade_km_min"])
                    for d in C.RESGATADORES]

    
    # Cada armazém recebe a sua localização e as capacidades das zonas.
    armazens = [
        ArmazemAgent(jid(d["nome"]), C.SENHA, d["pos"], d["zonas"])
        for d in C.ARMAZENS
    ]


    # Cada restaurante só conhece os pares que lhe passamos aqui (sem diretório
    # central). Na Fatia 1 conhecem todos; depois pode limitar-se por raio.
    ongs_conhecidas = [(str(o.jid), o.pos) for o in ongs]
    resgatadores_conhecidos = [str(r.jid) for r in resgatadores]
    # Armazéns conhecidos pelos restaurantes (identificador e localização).
    armazens_conhecidos = [(str(a.jid), a.pos) for a in armazens]
    
    restaurantes = [RestauranteAgent(jid(d["nome"]), C.SENHA, d["pos"], ongs_conhecidas,
                                     resgatadores_conhecidos, C.LOTES, terminou.set, armazens_conhecidos)
                    for d in C.RESTAURANTES]

    

    # --- arrancar: primeiro quem responde, por fim quem inicia ---------------
    todos = ongs + armazens + resgatadores + restaurantes
    for a in todos:
        await a.start(auto_register=True)
    print(f"{len(todos)} agentes a correr.\n", flush=True)

    # --- esperar o fim ------------------------------------------------------
    try:
        await asyncio.wait_for(terminou.wait(), timeout=TEMPO_MAXIMO_S)
    except asyncio.TimeoutError:
        print("\nAVISO: tempo máximo atingido; algum lote ficou preso.", flush=True)

    gerados = [{"kg": d["kg"]} for d in C.LOTES] * len(C.RESTAURANTES)
    print("\nResumo:", registo.resumo(gerados), flush=True)

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
