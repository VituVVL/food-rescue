"""
Ponto de entrada da simulação.

    python run.py --scenario S1 --seed 42
    python run.py --scenario S3 --seed 7 --speed 0.02    (mais rápido)

Arranca o servidor XMPP embutido do SPADE (não é preciso `spade run` noutro
terminal), cria os agentes, deixa correr o dia simulado e grava as métricas em
results/<cenário>_seed<seed>_summary.json e _events.csv.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import multiprocessing
import os
import sys
import traceback
from dataclasses import replace
from pathlib import Path

# Os caminhos são sempre relativos a ESTA pasta, corra-se de onde se correr
# (PyCharm, terminal noutra pasta, etc.).
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
os.chdir(HERE)

import spade

from fr import world  # noqa: E402
from fr.config import SCENARIOS
from fr.donor import DonorAgent
from fr.fridge import FridgeAgent
from fr.recipient import RecipientAgent
from fr.rescuer import RescuerAgent
from fr.world import RNG, Clock, M, dist

DOMAIN = "localhost"
PWD = "secret"


def rand_pos(cfg):
    return (RNG.randint(0, cfg.grid_km), RNG.randint(0, cfg.grid_km))


def build_agents(cfg):
    donors = [DonorAgent(f"donor{i}@{DOMAIN}", PWD, cfg=cfg, pos=rand_pos(cfg))
              for i in range(cfg.n_donors)]
    fridges = [FridgeAgent(f"fridge{i}@{DOMAIN}", PWD, cfg=cfg, pos=rand_pos(cfg),
                           capacity=cfg.fridge_capacity_kg,
                           fail_at=cfg.fridge_fail_at_min if i == 0 else None)
               for i in range(cfg.n_fridges)]
    kinds = ["bakery", "produce", "prepared", "dairy"]
    recipients = [RecipientAgent(f"recipient{i}@{DOMAIN}", PWD, cfg=cfg, pos=rand_pos(cfg),
                                 accepts=set(RNG.sample(kinds, RNG.randint(2, 4))),
                                 need_kg=RNG.uniform(*cfg.need_range_kg),
                                 urgency=RNG.randint(1, 3))
                  for i in range(cfg.n_recipients)]
    rescuers = []
    for i in range(cfg.n_rescuers):
        car = RNG.random() < 0.6
        rescuers.append(RescuerAgent(
            f"rescuer{i}@{DOMAIN}", PWD, cfg=cfg, pos=rand_pos(cfg),
            capacity=60 if car else 15,
            cold=RNG.random() < cfg.frac_cold_vehicles,
            speed=0.5 if car else 0.25,
            on_shift=RNG.random() < cfg.frac_on_shift,
            unreliable=RNG.random() < cfg.frac_unreliable))

    # Vizinhança (RF03): cada iniciador só conhece quem está dentro do raio.
    for a in donors + fridges:
        a.recipients = [(str(r.jid), r.pos) for r in recipients if dist(a.pos, r.pos) <= cfg.radius_km]
        a.rescuers = [str(r.jid) for r in rescuers if dist(a.pos, r.pos) <= cfg.radius_km]
        a.fridges = [(str(f.jid), f.pos) for f in fridges
                     if f is not a and dist(a.pos, f.pos) <= cfg.radius_km]
    return donors, rescuers, fridges, recipients


async def main(cfg, outdir):
    world.seed(cfg.seed)
    M.reset()
    donors, rescuers, fridges, recipients = build_agents(cfg)
    everyone = recipients + rescuers + fridges + donors   # doadores por último

    for a in everyone[:-len(donors)]:
        await a.start(auto_register=True)
    Clock.start(cfg.real_sec_per_sim_min)
    for a in donors:
        await a.start(auto_register=True)

    total = cfg.duration_min + cfg.drain_min
    print(f"[{cfg.name}] {len(everyone)} agentes a correr, {total} min simulados "
          f"(~{Clock.secs(total):.0f} s reais)")
    while Clock.now() < total:
        await asyncio.sleep(Clock.secs(60))
        print(f"  t={Clock.now():5.0f} min | itens={len(M.items):3d} "
              f"| msgs={M.msgs_sent}")

    # 1) GRAVAR PRIMEIRO (no Windows o stop() dos agentes pode ficar pendurado)
    summary = M.summary([r.name_ for r in recipients])
    summary = {"scenario": cfg.name, "seed": cfg.seed, **summary}
    out = (HERE / outdir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    M.save(str(out / f"{cfg.name}_seed{cfg.seed}"), summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\nResultados gravados em: {out}", flush=True)

    # 2) Só depois parar os agentes, com limite de tempo
    for a in everyone:
        try:
            await asyncio.wait_for(a.stop(), timeout=3)
        except Exception:
            pass


def hard_exit(code: int) -> None:
    """Termina o processo E os processos-filho do servidor XMPP embutido.
    Sem isto, o servidor pode ficar órfão a ocupar a porta 5222 e a corrida
    seguinte falha sem mensagem nenhuma."""
    for child in multiprocessing.active_children():
        child.kill()
    sys.stdout.flush()
    os._exit(code)


async def safe_main(cfg, outdir):
    # NOTA: o spade.run() esconde as exceções do main (silencia o logger quando
    # usa o servidor embutido). Por isso apanhamos e mostramos tudo aqui.
    try:
        await main(cfg, outdir)
    except Exception:
        traceback.print_exc()
        (HERE / "error.log").write_text(traceback.format_exc(), encoding="utf-8")
        print(f"\nERRO, detalhes em {HERE / 'error.log'}", flush=True)
        hard_exit(1)
    hard_exit(0)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="S1", choices=SCENARIOS)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--speed", type=float, default=None,
                    help="segundos reais por minuto simulado (default 0.05)")
    ap.add_argument("--out", default="results")
    args = ap.parse_args()
    cfg = replace(SCENARIOS[args.scenario], seed=args.seed)
    if args.speed:
        cfg = replace(cfg, real_sec_per_sim_min=args.speed)
    spade.run(safe_main(cfg, args.out), embedded_xmpp_server=True)
