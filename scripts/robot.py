"""Robot de probabilidades deportivas (corre solo en GitHub Actions, sin Claude).

Fuentes:
  * Polymarket (obligatoria): todas las ligas profesionales que tiene Polymarket.
  * DraftKings vía ESPN: cuota sin margen, cuando el partido existe en ESPN.
  * Kalshi: mercado de ganador para NBA, NHL, NFL y MLB.
La probabilidad final es el promedio de las fuentes disponibles.

Modos (variable MODO):
  manana     -> arma la lista del día (todos los ganadores >= 80 %, máx. 15),
                pasa los picks de ayer al historial y manda el Telegram.
  actualizar -> marca terminados / en juego y, por cada terminado, agrega el
                siguiente mejor ganador de hoy que aún no empezó.

Otras variables: TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, DRY_RUN=1, FORZAR=1.
"""
import json, os, re, subprocess, sys, time, unicodedata, urllib.request, urllib.parse
from datetime import datetime, timedelta, timezone

CCS = timezone(timedelta(hours=-4))
UTC = timezone.utc
ahora = datetime.now(CCS)
if os.environ.get("FECHA"):  # solo para pruebas: simula las 6 am de otro día
    ahora = datetime.fromisoformat(os.environ["FECHA"] + "T06:00:00-04:00")
hoy = ahora.strftime("%Y-%m-%d")
MODO = os.environ.get("MODO", "manana")
DRY = os.environ.get("DRY_RUN") == "1"
FORZAR = os.environ.get("FORZAR") == "1"
MIN_PROB = 80.0
MAX_PICKS = 15
MIN_PICKS = 5
MIN_LIQ = 500  # USD de liquidez mínima en Polymarket para fiarse del precio

# ---------------------------------------------------------------- ligas
F, B, H, A, BB, T, C, CR, R, HB, V = "⚽", "🏀", "🏒", "🏈", "⚾", "🎾", "🥊", "🏏", "🏉", "🤾", "🏐"
LIGAS_PM = {  # código Polymarket: (emoji, nombre que se muestra)
    # fútbol: primeras divisiones, copas y selecciones
    "epl": (F, "Premier League"), "lal": (F, "LaLiga"), "sea": (F, "Serie A"), "bun": (F, "Bundesliga"),
    "fl1": (F, "Ligue 1"), "ere": (F, "Eredivisie"), "por": (F, "Liga Portugal"), "bel1": (F, "Bélgica"),
    "tur": (F, "Superliga Turquía"), "scop": (F, "Escocia"), "elc": (F, "Championship"), "spl": (F, "Liga Saudí"),
    "mls": (F, "MLS"), "mex": (F, "Liga MX"), "bra": (F, "Brasileirão"), "arg": (F, "Liga Argentina"),
    "col1": (F, "Liga BetPlay"), "chi1": (F, "Chile"), "ecu1": (F, "Ecuador"), "uru1": (F, "Uruguay"),
    "par1": (F, "Paraguay"), "per1": (F, "Perú"), "bol1": (F, "Bolivia"), "ven1": (F, "Liga FUTVE"),
    "swe": (F, "Allsvenskan"), "nor": (F, "Eliteserien"), "den": (F, "Dinamarca"), "aut": (F, "Austria"),
    "sui": (F, "Suiza"), "gre1": (F, "Grecia"), "rus": (F, "Rusia"), "ukr1": (F, "Ucrania"), "cze1": (F, "Chequia"),
    "pol": (F, "Polonia"), "hr1": (F, "Croacia"), "srb": (F, "Serbia"), "jap": (F, "J1 League"), "kor": (F, "K League"),
    "aus": (F, "A-League"), "chi": (F, "Superliga China"), "egy1": (F, "Egipto"), "mar1": (F, "Marruecos"),
    "ucl": (F, "Champions League"), "uel": (F, "Europa League"), "col": (F, "Conference League"),
    "lib": (F, "Libertadores"), "sud": (F, "Sudamericana"), "ccc": (F, "Concachampions"), "acle": (F, "Champions de Asia"),
    "cafcl": (F, "Champions de África"), "cwc": (F, "Mundial de Clubes"),
    "efa": (F, "FA Cup"), "efl": (F, "Copa de la Liga (ING)"), "cdr": (F, "Copa del Rey"), "itc": (F, "Coppa Italia"),
    "dfb": (F, "Copa de Alemania"), "cde": (F, "Copa de Francia"), "ptc": (F, "Copa de Portugal"), "nlc": (F, "Copa de Holanda"),
    "scoc": (F, "Copa de Escocia"), "brco": (F, "Copa do Brasil"), "argcopa": (F, "Copa Argentina"),
    "unl": (F, "Nations League"), "fif": (F, "Amistoso de selecciones"), "fifwc": (F, "Mundial"), "copaam": (F, "Copa América"),
    "euc": (F, "Eurocopa"), "ueq": (F, "Eliminatorias Euro"), "ewq": (F, "Eliminatorias UEFA"), "uef": (F, "Eliminatorias UEFA"),
    "con": (F, "Eliminatorias CONMEBOL"), "sawq": (F, "Eliminatorias CONMEBOL"), "cof": (F, "Eliminatorias CONCACAF"),
    "nawq": (F, "Eliminatorias CONCACAF"), "afc": (F, "Eliminatorias Asia"), "aswq": (F, "Eliminatorias Asia"),
    "caf": (F, "Eliminatorias África"), "afwq": (F, "Eliminatorias África"), "icwq": (F, "Repechaje mundialista"),
    "ncag": (F, "Copa Oro"), "acn": (F, "Copa África"),
    # baloncesto
    "nba": (B, "NBA"), "euroleague": (B, "EuroLeague"), "bkeurocup": (B, "EuroCup"), "bkcl": (B, "Basketball Champions League"),
    "bkligend": (B, "Liga ACB"), "bkbsl": (B, "Liga Turca"), "bkgr1": (B, "Liga Griega"), "bkseriea": (B, "Lega Basket"),
    "bkbbl": (B, "BBL Alemania"), "bkfr1": (B, "Liga Francesa"), "bkvtb": (B, "VTB"), "bknbl": (B, "NBL Australia"),
    "bkaba": (B, "Liga ABA"), "bkisrsl": (B, "Liga de Israel"), "bklkl": (B, "LKL Lituania"), "bkcba": (B, "CBA China"),
    "bkjpn": (B, "B.League"), "bkkbl": (B, "KBL Corea"), "bkarg": (B, "Liga Nacional (ARG)"), "bknbb": (B, "NBB Brasil"),
    "bkvensl": (B, "SuperLiga (VEN)"), "bkfibaqeu": (B, "Eliminatorias FIBA"), "bkfibaqam": (B, "Eliminatorias FIBA"),
    "bkfibaqas": (B, "Eliminatorias FIBA"), "bkfibaqaf": (B, "Eliminatorias FIBA"),
    # hockey
    "nhl": (H, "NHL"), "khl": (H, "KHL"), "shl": (H, "SHL Suecia"), "liiga": (H, "Liiga"), "dehl": (H, "DEL Alemania"),
    "snhl": (H, "National League (SUI)"), "cehl": (H, "Extraliga Checa"), "hockeychl": (H, "Champions Hockey League"),
    # fútbol americano y béisbol
    "nfl": (A, "NFL"), "cfl": (A, "CFL"),
    "mlb": (BB, "MLB"), "lvbp": (BB, "LVBP"), "lmp": (BB, "LMP"), "lidom": (BB, "LIDOM"), "npb": (BB, "NPB Japón"), "kbo": (BB, "KBO"),
    # tenis, combate, cricket, rugby, balonmano, voleibol, AFL
    "atp": (T, "ATP"), "wta": (T, "WTA"), "daviscup": (T, "Copa Davis"), "bjkcup": (T, "Billie Jean King Cup"),
    "ufc": (C, "UFC"), "boxing": (C, "Boxeo"),
    "t20": (CR, "T20 internacional"), "odi": (CR, "ODI"), "test": (CR, "Test cricket"), "cricipl": (CR, "IPL"), "ipl": (CR, "IPL"),
    "cricbbl": (CR, "Big Bash"), "abb": (CR, "Big Bash"), "sasa": (CR, "SA20"),
    "rusixnat": (R, "Seis Naciones"), "ruchamp": (R, "Rugby Championship"), "rueuchamp": (R, "Champions Cup rugby"),
    "ruprem": (R, "Premiership Rugby"), "rutopft": (R, "Top 14"), "ruurc": (R, "URC"), "rusrp": (R, "Super Rugby"),
    "rlnrl": (R, "NRL"), "rlsuper": (R, "Super League rugby"),
    "hbehfcl": (HB, "Champions de balonmano"), "hbbundesliga": (HB, "Bundesliga balonmano"),
    "vbcl": (V, "Champions de voleibol"), "vbplusliga": (V, "PlusLiga"), "vbsuperlega": (V, "SuperLega"),
    "afl": ("🏉", "AFL"),
}
TRES_VIAS = {e for e in ("⚽",)}  # deportes con empate posible (el empate pierde)

ESPN = [  # rutas ESPN con cuotas DraftKings (para contrastar)
    "basketball/nba", "hockey/nhl", "football/nfl", "baseball/mlb",
    "soccer/eng.1", "soccer/esp.1", "soccer/ita.1", "soccer/ger.1", "soccer/fra.1", "soccer/ned.1", "soccer/por.1",
    "soccer/tur.1", "soccer/sco.1", "soccer/bel.1", "soccer/eng.2", "soccer/ksa.1", "soccer/usa.1", "soccer/mex.1",
    "soccer/bra.1", "soccer/arg.1", "soccer/col.1", "soccer/chi.1", "soccer/ecu.1",
    "soccer/uefa.champions", "soccer/uefa.europa", "soccer/uefa.europa.conf", "soccer/conmebol.libertadores",
    "soccer/conmebol.sudamericana", "soccer/eng.fa", "soccer/eng.league_cup", "soccer/esp.copa_del_rey",
    "soccer/ita.coppa_italia", "soccer/ger.dfb_pokal", "soccer/fra.coupe_de_france", "soccer/uefa.nations",
    "soccer/fifa.friendly", "soccer/fifa.worldq.uefa", "soccer/fifa.worldq.conmebol", "soccer/fifa.worldq.concacaf",
]
KALSHI = {"nba": "KXNBAGAME", "nhl": "KXNHLGAME", "nfl": "KXNFLGAME", "mlb": "KXMLBGAME"}


# ---------------------------------------------------------------- utilidades
def get_json(url, intentos=3):
    for i in range(intentos):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as e:
            if i == intentos - 1:
                raise
            time.sleep(2 + 3 * i)


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    quitar = {"fc", "cf", "sc", "ac", "afc", "cd", "ud", "sd", "fk", "sk", "bk", "club", "de", "the", "real", "city", "united",
              "deportivo", "atletico", "sporting", "basket", "basketball", "bc", "kk", "hc", "and", "vs", "1", "04", "05", "09"}
    return {w for w in s.split() if len(w) >= 3 and w not in quitar}


def mismo_equipo(a, b):
    na, nb = norm(a), norm(b)
    return bool(na and nb and (na & nb))


def parse_dt(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00").replace(" ", "T")).astimezone(CCS)
    except ValueError:
        return None


def hora_txt(dt):
    return dt.strftime("%I:%M %p").lstrip("0").lower()


def lista(v):
    if isinstance(v, list):
        return v
    try:
        return json.loads(v or "[]")
    except Exception:
        return []


def precio_si(m):
    """Probabilidad del primer resultado de un mercado de Polymarket (punto medio si el libro es estrecho)."""
    try:
        bid, ask = float(m.get("bestBid") or 0), float(m.get("bestAsk") or 0)
    except (TypeError, ValueError):
        bid = ask = 0
    if 0 < bid < ask and ask - bid <= 0.10:
        return (bid + ask) / 2
    p = lista(m.get("outcomePrices"))
    return float(p[0]) if p else None


# ---------------------------------------------------------------- Polymarket
def polymarket_juegos(incluir_cerrados=False):
    deportes = {s["sport"]: s for s in get_json("https://gamma-api.polymarket.com/sports")}
    desde = (ahora - timedelta(days=1)).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    hasta = (ahora + timedelta(days=12)).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    juegos, vistos_series, vistos = [], set(), set()
    for cod, (emoji, liga) in LIGAS_PM.items():
        s = deportes.get(cod)
        if not s or not s.get("series") or s["series"] in vistos_series:
            continue
        vistos_series.add(s["series"])
        estados = ["false", "true"] if incluir_cerrados else ["false"]
        for cerrado in estados:
            for pagina in range(6):
                params = {"series_id": s["series"], "limit": 500, "offset": 500 * pagina, "closed": cerrado,
                          "end_date_min": desde, "end_date_max": hasta}
                try:
                    eventos = get_json("https://gamma-api.polymarket.com/events?" + urllib.parse.urlencode(params))
                except Exception as e:
                    print("  Polymarket sin datos", cod, e)
                    break
                for ev in eventos:
                    j = juego_de_evento(ev, emoji, liga, cod, s.get("ordering") or "home")
                    if j and j["slug"] not in vistos:
                        vistos.add(j["slug"])
                        juegos.append(j)
                if len(eventos) < 500:
                    break
    print(f"Polymarket: {len(juegos)} partidos con mercado de ganador")
    return juegos


def juego_de_evento(ev, emoji, liga, cod, ordering):
    mls = [m for m in ev.get("markets", []) if m.get("sportsMarketType") == "moneyline"]
    if not mls:
        return None
    inicio = parse_dt(ev.get("startTime") or mls[0].get("gameStartTime") or ev.get("endDate"))
    if not inicio:
        return None
    titulo = ev.get("title") or ""
    titulo = re.sub(r"^[A-Za-z]{2,5}:\s*", "", titulo)
    partes = [re.sub(r"^[A-Za-z]{2,5}:\s*", "", p.strip()) for p in re.split(r"\s+vs\.?\s+", titulo, maxsplit=1)]
    if len(partes) != 2:
        return None
    probs, empate = {}, None
    if len(mls) == 1 and len(lista(mls[0].get("outcomes"))) == 2:
        m = mls[0]
        outs = lista(m["outcomes"])
        p0 = precio_si(m)
        if p0 is None:
            return None
        probs = {outs[0]: p0, outs[1]: 1 - p0}
        cerrado = [float(x) for x in lista(m.get("outcomePrices"))] if m.get("closed") else None
        ganador = None
        if cerrado and max(cerrado) >= 0.98:
            ganador = outs[cerrado.index(max(cerrado))]
    else:  # fútbol: un mercado sí/no por resultado
        ganador = None
        for m in mls:
            q = (m.get("question") or "").lower()
            p = precio_si(m)
            if p is None:
                continue
            cerrado = [float(x) for x in lista(m.get("outcomePrices"))] if m.get("closed") else None
            if "draw" in q or "empate" in q:
                empate = p
                if cerrado and cerrado[0] >= 0.98:
                    ganador = "__empate__"
                continue
            eq = next((t for t in partes if t.lower() in q), None) or m.get("groupItemTitle")
            if eq:
                probs[eq] = p
                if cerrado and cerrado[0] >= 0.98:
                    ganador = eq
        if len(probs) != 2:
            return None
    tot = sum(probs.values()) + (empate or 0)
    if tot <= 0:
        return None
    probs = {k: v / tot for k, v in probs.items()}
    equipos = list(probs)
    # orden local/visitante
    if ordering == "away":
        visita, local = partes
    else:
        local, visita = partes
    liq = sum(float(m.get("liquidityNum") or m.get("liquidity") or 0) for m in mls)
    return {
        "emoji": emoji, "liga": liga, "cod": cod, "slug": ev.get("slug"), "inicio": inicio,
        "local": local, "visita": visita, "equipos": equipos, "pm": probs, "empate": empate is not None,
        "liq": liq, "cerrado": bool(ev.get("closed")) or bool(ev.get("ended")) or all(m.get("closed") for m in mls), "ganador": ganador,
        "vivo": bool(ev.get("live")), "marcador": ev.get("score") or "", "periodo": ev.get("period") or "",
        "fuentes": {},
    }


# ---------------------------------------------------------------- ESPN / DraftKings
def american_a_prob(ml):
    try:
        ml = float(str(ml).replace("+", ""))
    except (TypeError, ValueError):
        return None
    if ml == 0:
        return None
    return 100 / (ml + 100) if ml > 0 else -ml / (-ml + 100)


def ml_de(odds, lado):
    v = ((odds.get(f"{lado}TeamOdds") or {}).get("moneyLine"))
    if isinstance(v, dict):
        v = (v.get("close") or v.get("open") or {}).get("odds")
    if v is None:
        s = (odds.get("moneyline") or {}).get(lado) or {}
        for k in ("close", "current", "open"):
            x = (s.get(k) or {}).get("odds")
            if x == "EVEN":
                return 100
            if x not in (None, "", "OFF"):
                return x
    return v


def espn_juegos():
    out = []
    for ruta in ESPN:
        for dia in (ahora - timedelta(days=1), ahora, ahora + timedelta(days=1)):
            try:
                evs = get_json(f"https://site.api.espn.com/apis/site/v2/sports/{ruta}/scoreboard?dates={dia:%Y%m%d}", 2).get("events", [])
            except Exception:
                continue
            for ev in evs:
                c = (ev.get("competitions") or [{}])[0]
                comp = c.get("competitors") or []
                if len(comp) != 2:
                    continue
                st = ((c.get("status") or ev.get("status") or {}).get("type") or {})
                local = next((t for t in comp if t.get("homeAway") == "home"), comp[0])
                visita = next((t for t in comp if t.get("homeAway") == "away"), comp[1])
                j = {"inicio": parse_dt(ev.get("date")), "local": local["team"].get("displayName", ""),
                     "visita": visita["team"].get("displayName", ""),
                     "abrev": {t["team"].get("displayName", ""): {"abbr": t["team"].get("abbreviation", ""),
                                                                   "loc": t["team"].get("location", "")} for t in (local, visita)},
                     "estado": st.get("state"), "terminado": st.get("completed"), "detalle": st.get("shortDetail", ""),
                     "marcador": f"{local.get('score', '')}-{visita.get('score', '')}",
                     "ganador": next((t["team"].get("displayName") for t in comp if t.get("winner")), None),
                     "dk": None, "ruta": ruta}
                od = next((o for o in (c.get("odds") or []) if isinstance(o, dict)), None)
                if od:
                    ph, pa = american_a_prob(ml_de(od, "home")), american_a_prob(ml_de(od, "away"))
                    pd = american_a_prob(((od.get("drawOdds") or {}).get("moneyLine")) or ml_de(od, "draw")) if ruta.startswith("soccer") else 0
                    if ph and pa and (pd or not ruta.startswith("soccer")):
                        tot = ph + pa + (pd or 0)
                        j["dk"] = {j["local"]: ph / tot, j["visita"]: pa / tot}
                out.append(j)
    print(f"ESPN: {len(out)} partidos ({sum(1 for j in out if j['dk'])} con cuota DraftKings)")
    return out


def emparejar_espn(juego, espn):
    for e in espn:
        if not e["inicio"] or abs((e["inicio"] - juego["inicio"]).total_seconds()) > 4 * 3600:
            continue
        if (mismo_equipo(juego["local"], e["local"]) and mismo_equipo(juego["visita"], e["visita"])) or \
           (mismo_equipo(juego["local"], e["visita"]) and mismo_equipo(juego["visita"], e["local"])):
            return e
    return None


# ---------------------------------------------------------------- Kalshi
def kalshi_precios():
    out = {}
    for cod, serie in KALSHI.items():
        cursor = ""
        for _ in range(5):
            try:
                d = get_json(f"https://api.elections.kalshi.com/trade-api/v2/markets?status=open&limit=500&series_ticker={serie}"
                             + (f"&cursor={cursor}" if cursor else ""), 2)
            except Exception as e:
                print("  Kalshi sin datos", serie, e)
                break
            for m in d.get("markets", []):
                try:
                    bid, ask = float(m.get("yes_bid_dollars") or 0), float(m.get("yes_ask_dollars") or 0)
                    p = (bid + ask) / 2 if 0 < bid < ask and ask - bid <= 0.10 else float(m.get("last_price_dollars") or 0)
                except (TypeError, ValueError):
                    continue
                if p <= 0:
                    continue
                ev = m.get("event_ticker", "")
                abrev = m.get("ticker", "").rsplit("-", 1)[-1]
                out[(cod, ev, abrev, m.get("yes_sub_title") or "")] = p
            cursor = d.get("cursor")
            if not cursor:
                break
    print(f"Kalshi: {len(out)} mercados de ganador")
    return out


def precio_kalshi(juego, e, kalshi):
    """Busca el mercado de Kalshi del mismo partido (fecha + abreviatura o ciudad del equipo)."""
    if juego["cod"] not in KALSHI or not e or not e["inicio"]:
        return None
    claves = {(e["inicio"] + timedelta(hours=h)).strftime("%y%b%d").upper() for h in (-6, 0, 6)}
    res = {}
    for (cod, ev, ab, sub), p in kalshi.items():
        if cod != juego["cod"] or not any(c in ev for c in claves):
            continue
        for nombre, info in e["abrev"].items():
            if ab == (info["abbr"] or "").upper() or (sub and info["loc"] and sub.lower() == info["loc"].lower()):
                otro = next(i for n, i in e["abrev"].items() if n != nombre)
                if (otro["abbr"] or "?").upper() in ev.split("-")[-1] or ab in ev.split("-")[-1]:
                    res[nombre] = p
    if len(res) != 2:
        return None
    tot = sum(res.values())
    return {k: v / tot for k, v in res.items()}


# ---------------------------------------------------------------- candidatos
def candidatos(juegos, espn, kalshi, solo_futuros=True):
    lista_c = []
    de_hoy = [j for j in juegos if j["inicio"].strftime("%Y-%m-%d") == hoy]
    print(f"Partidos de hoy en Polymarket: {len(de_hoy)} · por empezar: "
          f"{sum(1 for j in de_hoy if j['inicio'] > ahora and not j['cerrado'])} · con poca liquidez: "
          f"{sum(1 for j in de_hoy if j['liq'] < MIN_LIQ)}")
    for j in sorted(de_hoy, key=lambda j: -max(j["pm"].values()))[:40]:
        print(f"   PM {max(j['pm'].values())*100:5.1f} liq {j['liq']:>9.0f} {j['liga']:<22} {j['local']} vs {j['visita']}")
    for j in juegos:
        if j["inicio"].strftime("%Y-%m-%d") != hoy:
            continue
        if solo_futuros and (j["inicio"] <= ahora or j["cerrado"] or j["vivo"]):
            continue
        if j["liq"] < MIN_LIQ:
            continue
        fav = max(j["pm"], key=j["pm"].get)
        fuentes = {"Polymarket": j["pm"][fav]}
        e = emparejar_espn(j, espn)
        if e and e["dk"]:
            k = next((n for n in e["dk"] if mismo_equipo(n, fav)), None)
            if k:
                fuentes["DraftKings"] = e["dk"][k]
        kp = precio_kalshi(j, e, kalshi)
        if kp:
            k = next((n for n in kp if mismo_equipo(n, fav)), None)
            if k:
                fuentes["Kalshi"] = kp[k]
        # si las fuentes no están de acuerdo (más de 12 puntos), se queda con la más baja
        vals = list(fuentes.values())
        prob = min(vals) if max(vals) - min(vals) > 0.12 else sum(vals) / len(vals)
        nombre_fav, partido = fav, f"{j['local']} vs {j['visita']}"
        if e:  # nombres completos y local/visitante de ESPN si existe
            nombre_fav = next((n for n in (e["local"], e["visita"]) if mismo_equipo(n, fav)), fav)
            partido = f"{e['local']} vs {e['visita']}"
        detalle = " · ".join(f"{k} {v*100:.1f} %" for k, v in fuentes.items())
        lista_c.append({
            "deporte": j["emoji"], "liga": j["liga"], "partido": partido,
            "hora": hora_txt(j["inicio"]), "apuesta": f"Gana {nombre_fav}", "prob": round(prob * 100, 1),
            "nota": detalle + (" · El empate pierde." if j["empate"] else "")
                    + (" · ⚠️ las fuentes no coinciden, uso la más baja" if max(vals) - min(vals) > 0.12 else ""),
            "pm": j["slug"], "pm_eq": fav, "inicio": j["inicio"].isoformat(), "n_fuentes": len(fuentes),
        })
    # ante empate de probabilidad, primero el que tiene más fuentes
    lista_c.sort(key=lambda p: (-p["prob"], -p["n_fuentes"]))
    for p in lista_c:
        p.pop("n_fuentes", None)
    return lista_c


def elegir(cands, ya=()):
    usados = {p["partido"] for p in ya}
    buenos = [p for p in cands if p["prob"] >= MIN_PROB and p["partido"] not in usados][:MAX_PICKS]
    if len(buenos) < MIN_PICKS:
        extra = [dict(p, nota=p["nota"] + " · ⚠️ menos de 80 %") for p in cands
                 if p["prob"] < MIN_PROB and p["partido"] not in usados][:MIN_PICKS - len(buenos)]
        buenos += extra
    return buenos


# ---------------------------------------------------------------- resultados
def resultado(p, por_slug, espn):
    """Devuelve (r, marcador) con r en ok/ko/vivo/None."""
    r = _resultado(p, por_slug, espn)
    return r


def _resultado(p, por_slug, espn):
    j = por_slug.get(p.get("pm"))
    eq = p.get("pm_eq") or p["apuesta"].replace("Gana ", "", 1)
    if not j:  # picks puestos a mano: buscar el partido en Polymarket por nombre y fecha
        for x in por_slug.values():
            if x["inicio"].strftime("%Y-%m-%d") == p.get("_fecha", hoy) and any(mismo_equipo(eq, t) for t in (x["local"], x["visita"])):
                j = x
                eq = next((t for t in x["pm"] if mismo_equipo(t, eq)), eq)
                break
    e = None
    if j:
        e = emparejar_espn(j, espn)
    else:  # picks viejos sin slug: buscar en ESPN por nombre
        nombre = p["apuesta"].replace("Gana ", "", 1)
        for x in espn:
            if x["inicio"] and x["inicio"].strftime("%Y-%m-%d") == p.get("_fecha", hoy) and \
               (mismo_equipo(nombre, x["local"]) or mismo_equipo(nombre, x["visita"])):
                e = x
                break
    if e and e["terminado"]:
        gano = e["ganador"] and mismo_equipo(e["ganador"], p["apuesta"].replace("Gana ", "", 1))
        return ("ok" if gano else "ko"), f"Final {e['marcador']}"
    if j and j["cerrado"] and j["ganador"]:
        gano = j["ganador"] != "__empate__" and mismo_equipo(j["ganador"], eq)
        return ("ok" if gano else "ko"), (f"Final {j['marcador']}" if j["marcador"] else "Final")
    if e and e["estado"] == "in":
        return "vivo", f"En juego · {e['detalle']} {e['marcador']}".strip()
    if j and j["inicio"] <= ahora:
        # Polymarket ya decidido (precio de 97 ¢ o más) después de la duración normal del partido
        dur = {"⚽": 2.1, "🏀": 2.3, "🏒": 2.6, "⚾": 3.2, "🏈": 3.3, "🎾": 2.5}.get(j["emoji"], 3.0)
        pq = next((v for k, v in j["pm"].items() if mismo_equipo(k, eq)), None)
        if pq is not None and ahora >= j["inicio"] + timedelta(hours=dur):
            fin = f"Final {j['marcador']}" if j["marcador"] else "Final (resultado según Polymarket)"
            if pq >= 0.97:
                return "ok", fin
            if pq <= 0.03:
                return "ko", fin
        return "vivo", f"En juego {j['marcador']}".strip() if j["marcador"] else "En juego"
    return None, None


# ---------------------------------------------------------------- página y envío
def leer_pagina():
    html = open("index.html", encoding="utf-8").read()
    m = re.search(r'(<script id="data" type="application/json">)(.*?)(</script>)', html, re.S)
    return html, m, json.loads(m.group(2))


def telegram(texto):
    api = f"https://api.telegram.org/bot{os.environ['TELEGRAM_TOKEN']}"
    data = urllib.parse.urlencode({"chat_id": os.environ["TELEGRAM_CHAT_ID"], "text": texto}).encode()
    print(json.load(urllib.request.urlopen(f"{api}/sendMessage", data=data)))


def publicar(html, m, D, mensaje):
    j = json.dumps(D, ensure_ascii=False, indent=1)
    json.loads(j)
    if DRY:
        print("DRY_RUN: no publico. JSON:\n", j[:6000])
        return
    open("index.html", "w", encoding="utf-8").write(html[:m.start(2)] + j + html[m.end(2):])
    git = ["git", "-c", "user.name=franklinperez20", "-c", "user.email=franklinperez20@users.noreply.github.com"]
    subprocess.run(git + ["commit", "-am", mensaje], check=True)
    for _ in range(4):
        if subprocess.run(["git", "push", "origin", "HEAD:main"]).returncode == 0:
            break
        subprocess.run(git + ["pull", "--rebase", "origin", "main"])
    else:
        raise RuntimeError("no pude hacer push")
    # un push hecho desde Actions no dispara otro workflow: mando el Telegram aquí
    subprocess.run([sys.executable, "scripts/telegram.py"], check=True, env={**os.environ, "COMMIT_MSG": mensaje})


DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
FUENTES_TXT = ("Polymarket (obligatorio: solo entran partidos que están en Polymarket), cuotas DraftKings vía ESPN "
               "sin el margen de la casa, y Kalshi en NBA/NHL/NFL/MLB. La probabilidad es el promedio de las fuentes; "
               "si no coinciden por más de 12 puntos, se usa la más baja.")


def modo_manana():
    html, m, D = leer_pagina()
    if D.get("fecha") == hoy and not FORZAR:
        print("La página ya tiene los picks de hoy; no hago nada.")
        return
    juegos = polymarket_juegos(incluir_cerrados=True)
    espn = espn_juegos()
    kalshi = kalshi_precios()
    cands = candidatos(juegos, espn, kalshi)
    print(f"{len(cands)} candidatos hoy. Mejores:")
    for p in cands[:25]:
        print(f"  {p['prob']:5.1f} {p['liga']:<22} {p['apuesta']:<35} {p['hora']:>9}  {p['nota']}")
    top = elegir(cands)
    if not top:
        raise RuntimeError("no encontré partidos de hoy en Polymarket")

    # historial: los picks anteriores
    if D.get("fecha") != hoy:
        por_slug = {j["slug"]: j for j in juegos}
        nuevos = []
        for p in D.get("picks", []):
            r, marc = (p.get("r"), None) if p.get("r") in ("ok", "ko") else resultado(dict(p, _fecha=D["fecha"]), por_slug, espn)
            nuevos.append({"fecha": D["fecha"], "apuesta": p["apuesta"], "prob": p["prob"], "r": r if r in ("ok", "ko") else "pend"})
        D["historial"] = (nuevos + D.get("historial", []))[:300]

    n90 = sum(p["prob"] >= 90 for p in top); n85 = sum(p["prob"] >= 85 for p in top); n80 = sum(p["prob"] >= 80 for p in top)
    deportes = sorted({p["liga"] for p in top if p["prob"] >= 80})
    D.update({
        "fecha": hoy,
        "fecha_texto": f"{DIAS[ahora.weekday()]} {ahora.day} de {MESES[ahora.month-1]} de {ahora.year}",
        "actualizado": ahora.strftime("%Y-%m-%d %H:%M") + " (hora de Venezuela) · robot automático",
        "resumen": (f"Solo apuestas a ganador que están en Polymarket. Revisé {len(juegos)} partidos de "
                    f"{len({j['cod'] for j in juegos})} ligas de todo el mundo. "
                    + (f"Hoy hay {n80} ganadores de 80 % o más (90 %+: {n90}; 85 %+: {n85}), en: {', '.join(deportes)}. "
                       if n80 else "Hoy NO hay ningún ganador de 80 % o más: la lista muestra los más altos, con cuidado. ")
                    + f"El más alto es {top[0]['apuesta'].replace('Gana ', '')} con {top[0]['prob']} %."),
        "picks": top,
        "fuentes": FUENTES_TXT,
    })
    D.pop("aviso", None)
    publicar(html, m, D, f"Picks del {hoy}")


def modo_actualizar():
    html, m, D = leer_pagina()
    if D.get("fecha") != hoy:
        print("La página no es de hoy; no actualizo.")
        return
    juegos = polymarket_juegos(incluir_cerrados=True)
    espn = espn_juegos()
    por_slug = {j["slug"]: j for j in juegos}
    cambios, lineas, terminados = False, [], 0
    for p in D["picks"]:
        if p.get("r") in ("ok", "ko"):
            continue
        r, marc = resultado(p, por_slug, espn)
        print("  pick:", p["apuesta"], "->", r, marc)
        if r and (r != p.get("r") or marc != p.get("marcador")):
            cambios = True
            if r in ("ok", "ko"):
                terminados += 1
                lineas.append(f"{'✔' if r == 'ok' else '✘'} {p['apuesta']} ({marc})")
            elif p.get("r") != "vivo":
                lineas.append(f"⏳ {p['apuesta']} (en juego)")
            p["r"], p["marcador"] = r, marc
    nuevos = []
    if terminados:
        for p in D["picks"]:
            p.pop("nuevo", None)
        kalshi = kalshi_precios()
        cands = [c for c in candidatos(juegos, espn, kalshi) if c["prob"] >= MIN_PROB]
        usados = {p["partido"] for p in D["picks"]}
        for c in cands:
            if len(nuevos) >= terminados:
                break
            if c["partido"] not in usados:
                c["nuevo"] = True
                nuevos.append(c)
        D["picks"] += nuevos
    if not cambios:
        print("Sin cambios.")
        return
    ok = sum(p.get("r") == "ok" for p in D["picks"]); fin = sum(p.get("r") in ("ok", "ko") for p in D["picks"])
    aviso = [f"🔄 Actualización {hora_txt(ahora)}"] + lineas
    if terminados:
        aviso.append("➕ Nuevos:" if nuevos else "➕ Nuevos: no quedan ganadores de 80 % para hoy")
        aviso += [f"• {c['deporte']} {c['apuesta']} – {c['prob']} % – {c['hora']}" for c in nuevos]
    aviso.append(f"Hoy van {ok} de {fin} acertados.")
    D["aviso"] = "\n".join(aviso)
    D["actualizado"] = ahora.strftime("%Y-%m-%d %H:%M") + " (hora de Venezuela) · actualización automática"
    D["fuentes"] = FUENTES_TXT
    # solo se manda Telegram si algo terminó o hay nuevos; si solo cambió un marcador en vivo, se publica sin aviso
    msg = f"Actualizacion {ahora:%H:%M}" if (terminados or any(l.startswith('⏳') for l in lineas)) else f"Marcadores {ahora:%H:%M}"
    if msg.startswith("Marcadores"):
        D.pop("aviso", None)
    print(D.get("aviso", "(sin aviso)"))
    if msg.startswith("Marcadores"):
        j = json.dumps(D, ensure_ascii=False, indent=1)
        if DRY:
            return
        open("index.html", "w", encoding="utf-8").write(html[:m.start(2)] + j + html[m.end(2):])
        git = ["git", "-c", "user.name=franklinperez20", "-c", "user.email=franklinperez20@users.noreply.github.com"]
        subprocess.run(git + ["commit", "-am", msg], check=True)
        subprocess.run(["git", "push", "origin", "HEAD:main"])
        return
    publicar(html, m, D, msg)


try:
    modo_manana() if MODO == "manana" else modo_actualizar()
except Exception as e:
    import traceback
    traceback.print_exc()
    print("ERROR:", e)
    if not DRY and MODO == "manana":
        telegram(f"⚠️ El robot NO pudo publicar los picks de hoy ({hoy}).\nMotivo: {e}\n"
                 "Abre Claude y escribe: \"bot deportivo, no llegaron los picks de hoy\".")
    sys.exit(1)
