"""Robot de respaldo (funciona solo en GitHub, sin Claude).

Si a la hora de correr la pagina NO tiene los picks de hoy, arma el top 10 de
ganadores con las cuotas publicas de ESPN (DraftKings), actualiza el historial
de ayer, publica la pagina y manda el Telegram. Si algo falla, manda una alerta.

Variables: TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, DRY_RUN=1 (solo muestra), FORZAR=1.
"""
import json, os, re, subprocess, sys, urllib.request, urllib.parse
from datetime import datetime, timedelta, timezone

CCS = timezone(timedelta(hours=-4))  # Caracas
ahora = datetime.now(CCS)
hoy = ahora.strftime("%Y-%m-%d")
DRY = os.environ.get("DRY_RUN") == "1"
FORZAR = os.environ.get("FORZAR") == "1"

LIGAS = {  # ruta ESPN: (emoji, nombre)
    "basketball/nba": ("🏀", "NBA"),
    "hockey/nhl": ("🏒", "NHL"),
    "football/nfl": ("🏈", "NFL"),
    "baseball/mlb": ("⚾", "MLB"),
    "soccer/eng.1": ("⚽", "Premier League"),
    "soccer/esp.1": ("⚽", "LaLiga"),
    "soccer/ita.1": ("⚽", "Serie A"),
    "soccer/ger.1": ("⚽", "Bundesliga"),
    "soccer/fra.1": ("⚽", "Ligue 1"),
    "soccer/ned.1": ("⚽", "Eredivisie"),
    "soccer/por.1": ("⚽", "Liga Portugal"),
    "soccer/tur.1": ("⚽", "Superliga Turquía"),
    "soccer/sco.1": ("⚽", "Escocia"),
    "soccer/bel.1": ("⚽", "Bélgica"),
    "soccer/eng.2": ("⚽", "Championship"),
    "soccer/ksa.1": ("⚽", "Liga Saudí"),
    "soccer/usa.1": ("⚽", "MLS"),
    "soccer/mex.1": ("⚽", "Liga MX"),
    "soccer/bra.1": ("⚽", "Brasileirão"),
    "soccer/arg.1": ("⚽", "Liga Argentina"),
    "soccer/col.1": ("⚽", "Liga BetPlay"),
    "soccer/chi.1": ("⚽", "Chile"),
    "soccer/ecu.1": ("⚽", "Ecuador"),
    "soccer/uefa.champions": ("⚽", "Champions League"),
    "soccer/uefa.europa": ("⚽", "Europa League"),
    "soccer/uefa.europa.conf": ("⚽", "Conference League"),
    "soccer/conmebol.libertadores": ("⚽", "Libertadores"),
    "soccer/conmebol.sudamericana": ("⚽", "Sudamericana"),
    "soccer/eng.fa": ("⚽", "FA Cup"),
    "soccer/eng.league_cup": ("⚽", "Copa de la Liga (ING)"),
    "soccer/esp.copa_del_rey": ("⚽", "Copa del Rey"),
    "soccer/ita.coppa_italia": ("⚽", "Coppa Italia"),
    "soccer/ger.dfb_pokal": ("⚽", "Copa de Alemania"),
    "soccer/fra.coupe_de_france": ("⚽", "Copa de Francia"),
    "soccer/uefa.nations": ("⚽", "Nations League"),
    "soccer/fifa.friendly": ("⚽", "Amistoso de selecciones"),
    "soccer/fifa.worldq.uefa": ("⚽", "Eliminatorias UEFA"),
    "soccer/fifa.worldq.conmebol": ("⚽", "Eliminatorias CONMEBOL"),
}


def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.load(r)


def american_a_prob(ml):
    try:
        ml = float(str(ml).replace("+", ""))
    except (TypeError, ValueError):
        return None
    if ml == 0:
        return None
    return 100 / (ml + 100) if ml > 0 else -ml / (-ml + 100)


def moneylines(odds):
    """Devuelve (home, away, draw) en formato americano, o None."""
    h = (odds.get("homeTeamOdds") or {}).get("moneyLine")
    a = (odds.get("awayTeamOdds") or {}).get("moneyLine")
    d = (odds.get("drawOdds") or {}).get("moneyLine")
    if isinstance(h, dict): h = (h.get("close") or h.get("open") or {}).get("odds")
    if isinstance(a, dict): a = (a.get("close") or a.get("open") or {}).get("odds")
    ml = odds.get("moneyline") or {}
    def pick(side):
        s = ml.get(side) or {}
        for k in ("close", "current", "open"):
            v = (s.get(k) or {}).get("odds")
            if v not in (None, "", "OFF", "EVEN"):
                return v
            if v == "EVEN":
                return 100
        return None
    h = h if h is not None else pick("home")
    a = a if a is not None else pick("away")
    d = d if d is not None else pick("draw")
    return h, a, d


def eventos(ruta, fecha_yyyymmdd):
    url = f"https://site.api.espn.com/apis/site/v2/sports/{ruta}/scoreboard?dates={fecha_yyyymmdd}"
    try:
        return get_json(url).get("events", [])
    except Exception as e:
        print("  sin datos", ruta, e)
        return []


def leer_pagina():
    html = open("index.html", encoding="utf-8").read()
    m = re.search(r'(<script id="data" type="application/json">)(.*?)(</script>)', html, re.S)
    return html, m, json.loads(m.group(2))


def telegram(texto):
    api = f"https://api.telegram.org/bot{os.environ['TELEGRAM_TOKEN']}"
    data = urllib.parse.urlencode({"chat_id": os.environ["TELEGRAM_CHAT_ID"], "text": texto}).encode()
    print(json.load(urllib.request.urlopen(f"{api}/sendMessage", data=data)))


def main():
    html, m, D = leer_pagina()
    if D.get("fecha") == hoy and not FORZAR:
        print("OK, la página ya tiene los picks de hoy"); return

    dias = [ahora.strftime("%Y%m%d"), (ahora + timedelta(days=1)).strftime("%Y%m%d")]
    ayer = (ahora - timedelta(days=1)).strftime("%Y%m%d")
    candidatos, ganadores_ayer, vistos = [], {}, set()

    for ruta, (emoji, liga) in LIGAS.items():
        es_futbol = ruta.startswith("soccer")
        # resultados de ayer (para el historial)
        for ev in eventos(ruta, ayer) + eventos(ruta, dias[0]):
            c = ev["competitions"][0]
            if ((c.get("status") or ev.get("status") or {}).get("type") or {}).get("completed"):
                for t in c["competitors"]:
                    ganadores_ayer[t["team"]["displayName"]] = (
                        "ok" if t.get("winner") else "ko",
                        " - ".join(f"{x['team']['shortDisplayName']} {x.get('score','')}" for x in c["competitors"]))
        # partidos de hoy por empezar
        for dia in dias:
            for ev in eventos(ruta, dia):
                if ev["id"] in vistos:
                    continue
                vistos.add(ev["id"])
                c = ev["competitions"][0]
                if os.environ.get("DEBUG_ODDS") != "hecho" and c.get("odds"):
                    os.environ["DEBUG_ODDS"] = "hecho"; print("MUESTRA ODDS:", json.dumps(c["odds"][0])[:1500])
                if ((c.get("status") or ev.get("status") or {}).get("type") or {}).get("state") != "pre":
                    continue
                ini = datetime.fromisoformat(ev["date"].replace("Z", "+00:00")).astimezone(CCS)
                if ini.strftime("%Y-%m-%d") != hoy or ini < ahora:
                    continue
                if not c.get("odds"):
                    continue
                h, a, d = moneylines(c["odds"][0])
                ph, pa = american_a_prob(h), american_a_prob(a)
                pd = american_a_prob(d) if es_futbol else 0
                if not ph or not pa or (es_futbol and not pd):
                    continue
                tot = ph + pa + (pd or 0)  # quitar el margen de la casa
                local = next(t for t in c["competitors"] if t["homeAway"] == "home")
                visita = next(t for t in c["competitors"] if t["homeAway"] == "away")
                fav, prob, ml = (local, ph / tot, h) if ph >= pa else (visita, pa / tot, a)
                hora = ini.strftime("%I:%M %p").lstrip("0").lower().replace("am", "am").replace("pm", "pm")
                candidatos.append({
                    "deporte": emoji, "liga": liga,
                    "partido": f"{local['team']['displayName']} vs {visita['team']['displayName']}",
                    "hora": hora, "apuesta": f"Gana {fav['team']['displayName']}",
                    "prob": round(prob * 100, 1),
                    "nota": f"Cuota {ml} ({(c['odds'][0].get('provider') or {}).get('name') or 'casa'}), sin margen."
                            + (" El empate pierde." if es_futbol else ""),
                })

    candidatos.sort(key=lambda p: -p["prob"])
    top = candidatos[:10]
    print(f"{len(candidatos)} partidos con cuota; top:")
    for p in top:
        print(" ", p["prob"], p["liga"], p["apuesta"], p["hora"])
    if not top:
        raise RuntimeError("ESPN no devolvió partidos con cuotas para hoy")

    # historial de los picks anteriores
    if D.get("fecha") != hoy:
        nuevos = []
        for p in D.get("picks", []):
            r = p.get("r") if p.get("r") in ("ok", "ko") else None
            eq = p["apuesta"].replace("Gana ", "", 1)
            if not r and eq in ganadores_ayer:
                r = ganadores_ayer[eq][0]
            nuevos.append({"fecha": D["fecha"], "apuesta": p["apuesta"], "prob": p["prob"], "r": r or "pend"})
        D["historial"] = (nuevos + D.get("historial", []))[:300]

    n85 = sum(p["prob"] >= 85 for p in top); n80 = sum(p["prob"] >= 80 for p in top)
    riesgo = [str(i + 1) for i, p in enumerate(top) if p["prob"] < 65]
    dias_es = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
             "septiembre", "octubre", "noviembre", "diciembre"]
    D.update({
        "fecha": hoy,
        "fecha_texto": f"{dias_es[ahora.weekday()]} {ahora.day} de {meses[ahora.month-1]} de {ahora.year}",
        "actualizado": ahora.strftime("%Y-%m-%d %H:%M") + " (hora de Venezuela) · robot de respaldo automático",
        "resumen": (f"Solo apuestas a ganador. Top armado automáticamente con las cuotas de ESPN/DraftKings "
                    f"(NBA, NHL, NFL, MLB y fútbol de primera). El favorito más alto es {top[0]['apuesta'].replace('Gana ','')} "
                    f"con {top[0]['prob']} %. Pasan del 85 %: {n85}; del 80 %: {n80}."
                    + (f" Riesgo alto (menos de 65 %): {', '.join(riesgo)}." if riesgo else "")),
        "picks": top,
        "fuentes": "Cuotas a ganador de ESPN (proveedor DraftKings), convertidas a probabilidad sin el margen de la casa.",
    })
    D.pop("aviso", None)
    j = json.dumps(D, ensure_ascii=False, indent=1)
    json.loads(j)
    if DRY:
        print("DRY_RUN: no publico nada"); return
    open("index.html", "w", encoding="utf-8").write(html[:m.start(2)] + j + html[m.end(2):])
    git = ["git", "-c", "user.name=franklinperez20", "-c", "user.email=franklinperez20@users.noreply.github.com"]
    subprocess.run(git + ["commit", "-am", f"Picks del {hoy} (respaldo automatico)"], check=True)
    for _ in range(3):
        if subprocess.run(["git", "push", "origin", "HEAD:main"]).returncode == 0:
            break
        subprocess.run(["git", "pull", "--rebase", "origin", "main"])
    else:
        raise RuntimeError("no pude hacer push")
    # el push hecho desde Actions no dispara otro workflow, asi que mando el Telegram aqui
    subprocess.run([sys.executable, "scripts/telegram.py"], check=True,
                   env={**os.environ, "COMMIT_MSG": f"Picks del {hoy}"})


try:
    main()
except Exception as e:
    import traceback; traceback.print_exc()
    print("ERROR:", e)
    if not DRY:
        telegram(f"⚠️ El robot NO pudo publicar los picks de hoy ({hoy}).\nMotivo: {e}\n"
                 "Abre Claude y escribe: \"bot deportivo, no llegaron los picks de hoy\".")
    sys.exit(1)
