"""Prueba del modelo propio contra partidos ya jugados (sin mirar el resultado al predecir)."""
import math, sys, time
from datetime import datetime, timedelta, timezone
sys.path.insert(0, "scripts")
import modelo as M
hoy = datetime.now(timezone(timedelta(hours=-4))).strftime("%Y%m%d")
DIAS_PRUEBA = int(sys.argv[2]) if len(sys.argv) > 2 else 10
for dep in sys.argv[1].split(","):
    t0 = time.time()
    hist = M.historia(dep, hoy, M.DIAS[dep] + DIAS_PRUEBA)
    print(f"\n===== {dep}: {sum(len(v) for v in hist.values())} eventos bajados en {time.time()-t0:.0f}s")
    preds = []
    for i in range(1, DIAS_PRUEBA + 1):
        D = (datetime.strptime(hoy, "%Y%m%d") - timedelta(days=i)).strftime("%Y%m%d")
        par = [x for x in M._terminados(hist, D, dep) if x[0] <= M.DIAS[dep]]
        mod = M.Modelo(dep, par)
        for e in hist.get(D, []):
            if e["g1"] is None or e["g2"] is None or e["e"] not in M.TERMINADO or (dep == "soccer" and e["e"] != "FT"):
                continue
            if dep == "tennis" and not any(x in e["c"] for x in ("ATP", "WTA")):
                continue
            if dep == "tennis" and "Challenger" in e["c"]:
                continue
            res = 0 if e["g1"] > e["g2"] else (1 if e["g1"] == e["g2"] else 2)
            preds.append((mod, e, res))
    print(f"{len(preds)} partidos para evaluar ({time.time()-t0:.0f}s)")
    grid_k = [0.8, 0.9, 1.0, 1.1, 1.2, 1.35, 1.5] if dep != "soccer" else [1.0]
    grid_e = [1.0, 1.1, 1.2, 1.3] if dep == "soccer" else [1.0]
    mejor = None
    for k in grid_k:
        for em in grid_e:
            ll, n, cal = 0, 0, {}
            for mod, e, res in preds:
                p = mod.prob(e["h"], e["a"], k=k, empate=em)
                if not p:
                    continue
                n += 1
                ll -= math.log(max(1e-6, p[res]))
                fav = 0 if p[0] >= p[2] else 2
                pf = p[fav]
                b = 50 if pf < .6 else 60 if pf < .7 else 70 if pf < .8 else 80 if pf < .85 else 85 if pf < .9 else 90
                c = cal.setdefault(b, [0, 0, 0.0]); c[0] += 1; c[1] += res == fav; c[2] += pf
            if not n:
                continue
            txt = " ".join(f"[{b}%: {c[0]} part, dice {100*c[2]/c[0]:.0f} real {100*c[1]/c[0]:.0f}]" for b, c in sorted(cal.items()))
            print(f" k={k} empate={em}: logloss {ll/n:.4f} n={n}  {txt}")
            if not mejor or ll / n < mejor[0]:
                mejor = (ll / n, k, em)
    print("MEJOR", dep, mejor)
