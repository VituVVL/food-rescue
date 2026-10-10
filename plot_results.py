"""
Lê results/*_summary.json e gera results/comparison.png + results/table.csv
(média ± desvio padrão por cenário). Base para o Performance Report.
"""
import glob
import json
import os
import statistics as st
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

METRICS = [("rescue_rate", "Taxa de resgate"),
           ("kg_wasted", "Desperdício (kg)"),
           ("avg_offer_to_delivery_min", "Oferta→entrega (min)"),
           ("recovery_rate", "Recuperação após falha"),
           ("jain_fairness", "Equidade (Jain)"),
           ("msgs_per_delivery", "Mensagens / entrega")]

os.chdir(os.path.dirname(os.path.abspath(__file__)))
runs = defaultdict(list)
for f in sorted(glob.glob("results/*_summary.json")):
    d = json.load(open(f, encoding="utf-8"))
    runs[d["scenario"]].append(d)
scen = sorted(runs)
if not scen:
    raise SystemExit("Sem resultados em results/. Corre primeiro run.py ou run_all.py.")

def stats(sc, k):
    xs = [r[k] for r in runs[sc] if r.get(k) is not None]
    if not xs:
        return 0, 0
    return st.mean(xs), (st.stdev(xs) if len(xs) > 1 else 0)

with open("results/table.csv", "w", encoding="utf-8") as f:
    f.write("scenario,n_runs," + ",".join(f"{k}_mean,{k}_std" for k, _ in METRICS) + "\n")
    for sc in scen:
        vals = [f"{v:.3f}" for k, _ in METRICS for v in stats(sc, k)]
        f.write(f"{sc},{len(runs[sc])}," + ",".join(vals) + "\n")

fig, axes = plt.subplots(2, 3, figsize=(13, 7))
for ax, (k, title) in zip(axes.flat, METRICS):
    m = [stats(sc, k) for sc in scen]
    ax.bar(scen, [x[0] for x in m], yerr=[x[1] for x in m], capsize=4, color="#3b7dd8")
    ax.set_title(title)
    ax.spines[["top", "right"]].set_visible(False)
fig.suptitle("Food Rescue — comparação de cenários (média ± dp)")
fig.tight_layout()
fig.savefig("results/comparison.png", dpi=130)
print("Gravado results/comparison.png e results/table.csv")
