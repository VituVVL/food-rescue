"""
Corre todos os cenários com várias seeds (um processo por corrida, porque cada
corrida arranca o seu próprio servidor XMPP) e depois gera o gráfico comparativo.

    python run_all.py                 # S1..S4 x seeds 1,2,3
    python run_all.py --seeds 1 2 3 4 5 --speed 0.02
    python run_all.py --scenarios S1 S3 --seeds 1
"""
import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from fr.config import SCENARIOS  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3])
ap.add_argument("--scenarios", nargs="+", default=list(SCENARIOS))
ap.add_argument("--speed", type=float, default=0.03)
args = ap.parse_args()

failed = []
for sc in args.scenarios:
    for s in args.seeds:
        print(f"=== {sc} seed={s} ===", flush=True)
        r = subprocess.run([sys.executable, str(HERE / "run.py"), "--scenario", sc,
                            "--seed", str(s), "--speed", str(args.speed)],
                           cwd=HERE, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=600)
        if r.returncode != 0 or not (HERE / "results" / f"{sc}_seed{s}_summary.json").exists():
            failed.append(f"{sc}/seed{s}")
            print(f"   FALHOU (código {r.returncode}). Últimas linhas:")
            print("\n".join((r.stdout + r.stderr).splitlines()[-25:]))
        else:
            print("   ok")

if failed:
    print("\nCorridas com erro:", ", ".join(failed))
subprocess.run([sys.executable, str(HERE / "plot_results.py")], cwd=HERE, check=False)
