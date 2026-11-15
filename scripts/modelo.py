"""Modelo propio del robot: probabilidad calculada SOLO con resultados reales, sin cuotas de casas de apuestas.

Fuente: resultados de LiveScore (todas las ligas del mundo, día por día).
  * Fútbol: modelo de Poisson (ataque y defensa de cada equipo) -> probabilidad de ganar en los 90 minutos.
  * Baloncesto, hockey, fútbol americano y béisbol: rating por diferencia de puntos (como el "SRS"),
    ajustado por la fuerza de los rivales y la ventaja de local.
  * Tenis: rating Elo de cada jugador con sus partidos recientes.
Los partidos recientes pesan más (vida media de 60 días). Si un equipo tiene muy pocos partidos, no se da número.
"""
import gzip, json, math, os, re, time, unicodedata, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

CCS = timezone(timedelta(hours=-4))
CACHE = os.environ.get("CACHE_MODELO", "cache_modelo")
URL = "https://prod-public-api.livescore.com/v1/api/app/date/{dep}/{dia}/-4?MD=1"
DEPORTE = {"⚽": "soccer", "🏀": "basketball", "🏒": "hockey", "🎾": "tennis", "🏈": "american-football", "⚾": "baseball"}
DIAS = {"soccer": 150, "basketball": 150, "hockey": 150, "tennis": 240, "american-football": 400, "baseball": 400}
VIDA_MEDIA = 60.0
MIN_PARTIDOS = 6
# Parámetros por deporte: tope de diferencia, ridge (partidos ficticios hacia la media) y factor de incertidumbre.
MARGEN = {"basketball": (30, 4.0, 1.0), "hockey": (4, 4.0, 1.0), "american-football": (28, 3.0, 1.0), "baseball": (6, 6.0, 1.0)}
TERMINADO = {"FT", "AET", "AP", "OT", "AOT", "Pen.", "After Pen.", "AW"}


def _get(url, intentos=3):
    for i in range(intentos):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json",
                                                       "Accept-Encoding": "gzip"})
            with urllib.request.urlopen(req, timeout=20) as r:
                b = r.read()
            if b[:2] == b"\x1f\x8b":
                b = gzip.decompress(b)
            return json.loads(b)
        except Exception:
            if i == intentos - 1:
                raise
            time.sleep(1 + 2 * i)


def _num(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def _compactar(d):
    out = []
    for st in d.get("Stages", []):
        for e in st.get("Events", []):
            t1, t2 = e.get("T1") or [], e.get("T2") or []
            if len(t1) != 1 or len(t2) != 1:
                continue  # dobles de tenis y datos raros fuera
            out.append({"c": st.get("Cnm", ""), "s": st.get("Snm", ""), "t": str(e.get("Esd", "")),
                        "h": str(t1[0].get("ID")), "hn": t1[0].get("Nm", ""), "a": str(t2[0].get("ID")),
                        "an": t2[0].get("Nm", ""), "e": e.get("Eps", ""), "g1": _num(e.get("Tr1")), "g2": _num(e.get("Tr2"))})
    return out


def dia(dep, fecha, hoy):
    """Partidos de un deporte en una fecha (AAAAMMDD). Los días ya cerrados quedan guardados en caché."""
    ruta = os.path.join(CACHE, dep, fecha + ".json")
    cerrado = fecha < (datetime.strptime(hoy, "%Y%m%d") - timedelta(days=1)).strftime("%Y%m%d")
    if cerrado and os.path.exists(ruta):
        with open(ruta) as f:
            return json.load(f)
    evs = _compactar(_get(URL.format(dep=dep, dia=fecha)))
    if cerrado:
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        with open(ruta, "w") as f:
            json.dump(evs, f, separators=(",", ":"))
    return evs


def historia(dep, hoy, dias=None, limite=None):
    """Lista de (fecha, evento) de los últimos días, en paralelo, sin pasar del límite de tiempo."""
    dias = dias or DIAS[dep]
    base = datetime.strptime(hoy, "%Y%m%d")
    fechas = [(base - timedelta(days=i)).strftime("%Y%m%d") for i in range(0, dias + 1)]
    t0 = time.time()

    def uno(f):
        if limite and time.time() - t0 > limite:
            return f, []
        try:
            return f, dia(dep, f, hoy)
        except Exception as e:
            print(f"  modelo: sin datos {dep} {f}: {e}", flush=True)
            return f, []
    with ThreadPoolExecutor(12) as ex:
        res = list(ex.map(uno, fechas))
    return {f: evs for f, evs in res}


def _terminados(eventos_por_dia, antes_de, dep):
    """Partidos terminados antes de una fecha, con su antigüedad en días."""
    lim = datetime.strptime(antes_de, "%Y%m%d")
    out = []
    for f, evs in eventos_por_dia.items():
        if f >= antes_de:
            continue
        edad = (lim - datetime.strptime(f, "%Y%m%d")).days
        for e in evs:
            if e["g1"] is None or e["g2"] is None or e["e"] not in TERMINADO:
                continue
            if dep == "soccer" and e["e"] != "FT":
                continue  # en fútbol solo sirven los 90 minutos limpios
            out.append((edad, f, e))
    return out


# ---------------------------------------------------------------- modelos
class Modelo:
    def __init__(self, dep, partidos):
        self.dep, self.n = dep, {}
        for _, _, e in partidos:
            self.n[e["h"]] = self.n.get(e["h"], 0) + 1
            self.n[e["a"]] = self.n.get(e["a"], 0) + 1
        if dep == "soccer":
            self._poisson(partidos)
        elif dep == "tennis":
            self._elo(partidos)
        else:
            self._margen(partidos)

    def _margen(self, partidos):
        tope, ridge, _ = MARGEN[self.dep]
        g = [(0.5 ** (edad / VIDA_MEDIA), e["h"], e["a"], max(-tope, min(tope, e["g1"] - e["g2"]))) for edad, _, e in partidos]
        sw = sum(w for w, *_ in g) or 1
        H = sum(w * m for w, _, _, m in g) / sw
        r = {}
        for _ in range(40):
            num, den = {}, {}
            for w, h, a, m in g:
                num[h] = num.get(h, 0) + w * (m - H + r.get(a, 0))
                den[h] = den.get(h, 0) + w
                num[a] = num.get(a, 0) + w * (-(m - H) + r.get(h, 0))
                den[a] = den.get(a, 0) + w
            r = {t: num[t] / (den[t] + ridge) for t in num}
            H = sum(w * (m - r[h] + r[a]) for w, h, a, m in g) / sw
        res = sum(w * (m - H - r[h] + r[a]) ** 2 for w, h, a, m in g) / sw
        self.H, self.r, self.sigma = H, r, math.sqrt(res)

    def _poisson(self, partidos):
        g = [(0.5 ** (edad / VIDA_MEDIA), e["h"], e["a"], min(e["g1"], 8), min(e["g2"], 8)) for edad, _, e in partidos]
        sw = sum(x[0] for x in g) or 1
        bh = sum(w * x for w, _, _, x, _ in g) / sw
        ba = sum(w * y for w, _, _, _, y in g) / sw
        A, D, P = {}, {}, 3.0  # P = partidos ficticios de un equipo promedio (encoge hacia la media)
        for _ in range(30):
            na, da, nd, dd = {}, {}, {}, {}
            for w, h, a, x, y in g:
                eh = bh * A.get(h, 1) * D.get(a, 1)
                ea = ba * A.get(a, 1) * D.get(h, 1)
                na[h] = na.get(h, 0) + w * x; da[h] = da.get(h, 0) + w * eh / A.get(h, 1)
                na[a] = na.get(a, 0) + w * y; da[a] = da.get(a, 0) + w * ea / A.get(a, 1)
                nd[a] = nd.get(a, 0) + w * x; dd[a] = dd.get(a, 0) + w * eh / D.get(a, 1)
                nd[h] = nd.get(h, 0) + w * y; dd[h] = dd.get(h, 0) + w * ea / D.get(h, 1)
            pm = P * (bh + ba) / 2
            A = {t: (na[t] + pm) / (da[t] + pm) for t in na}
            D = {t: (nd[t] + pm) / (dd[t] + pm) for t in nd}
            sh = sum(w * A.get(h, 1) * D.get(a, 1) for w, h, a, _, _ in g)
            sa = sum(w * A.get(a, 1) * D.get(h, 1) for w, h, a, _, _ in g)
            bh = sum(w * x for w, _, _, x, _ in g) / (sh or 1)
            ba = sum(w * y for w, _, _, _, y in g) / (sa or 1)
        self.A, self.D, self.bh, self.ba = A, D, bh, ba

    def _elo(self, partidos):
        R, N = {}, {}
        for edad, f, e in sorted(partidos, key=lambda x: (x[1], x[2]["t"])):
            h, a = e["h"], e["a"]
            if e["g1"] == e["g2"]:
                continue
            rh, ra = R.get(h, 1500.0), R.get(a, 1500.0)
            p = 1 / (1 + 10 ** ((ra - rh) / 400))
            s = 1.0 if e["g1"] > e["g2"] else 0.0
            kh = 250 / (N.get(h, 0) + 5) ** 0.4
            ka = 250 / (N.get(a, 0) + 5) ** 0.4
            R[h], R[a] = rh + kh * (s - p), ra - ka * (s - p)
            N[h], N[a] = N.get(h, 0) + 1, N.get(a, 0) + 1
        self.R = R

    def prob(self, h, a, k=1.0, empate=1.0):
        """(prob gana local, prob empate, prob gana visitante), o None si faltan datos."""
        minimo = 8 if self.dep == "tennis" else MIN_PARTIDOS
        if self.n.get(h, 0) < minimo or self.n.get(a, 0) < minimo:
            return None
        if self.dep == "tennis":
            p = 1 / (1 + 10 ** ((self.R.get(a, 1500) - self.R.get(h, 1500)) / (400 * k)))
            return p, 0.0, 1 - p
        if self.dep == "soccer":
            lh = self.bh * self.A.get(h, 1) * self.D.get(a, 1)
            la = self.ba * self.A.get(a, 1) * self.D.get(h, 1)
            ph = [math.exp(-lh) * lh ** i / math.factorial(i) for i in range(11)]
            pa = [math.exp(-la) * la ** i / math.factorial(i) for i in range(11)]
            w = sum(ph[i] * pa[j] for i in range(11) for j in range(i))
            d = sum(ph[i] * pa[i] for i in range(11)) * empate
            l = sum(ph[i] * pa[j] for j in range(11) for i in range(j))
            t = w + d + l
            return w / t, d / t, l / t
        mu = self.H + self.r.get(h, 0) - self.r.get(a, 0)
        z = mu / (self.sigma * k * MARGEN[self.dep][2])
        p = 0.5 * (1 + math.erf(z / math.sqrt(2)))
        return p, 0.0, 1 - p


# ---------------------------------------------------------------- emparejar picks con LiveScore
QUITAR = {"fc", "cf", "sc", "ac", "afc", "cd", "ud", "sd", "fk", "sk", "bk", "club", "de", "the", "city", "united",
          "basket", "basketball", "bc", "kk", "hc", "and", "vs", "cb", "bb", "ssd", "pallacanestro", "basquet", "baskets"}


def _tok(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return {w for w in re.sub(r"[^a-z0-9 ]", " ", s).split() if len(w) >= 3 and w not in QUITAR}


def _sim(a, b):
    ta, tb = _tok(a), _tok(b)
    if not ta or not tb:
        return 0.0
    comun = len(ta & tb)
    if not comun:  # prefijos ("Zalgiris" / "Zalgiris Kaunas" ya cuentan; "Barca" / "Barcelona" también)
        comun = sum(1 for x in ta for y in tb if len(x) >= 4 and len(y) >= 4 and (x.startswith(y) or y.startswith(x)))
    return comun / min(len(ta), len(tb))


def _hora(t):
    try:
        return datetime.strptime(t[:12], "%Y%m%d%H%M").replace(tzinfo=CCS)
    except ValueError:
        return None


class Propio:
    """Responde la probabilidad de nuestro modelo para cada pick. Cada deporte se arma la primera vez que se pide."""

    def __init__(self, hoy_iso, limite=240):
        self.hoy = hoy_iso.replace("-", "")
        self.mod, self.hoy_evs, self.fallidos = {}, {}, set()
        self.t0, self.limite = time.time(), limite

    def asegurar(self, dep):
        if dep in self.mod or dep in self.fallidos:
            return self.mod.get(dep)
        resto = self.limite - (time.time() - self.t0)
        if resto < 20:
            print(f"  modelo: sin tiempo para {dep}", flush=True)
            self.fallidos.add(dep)
            return None
        try:
            hist = historia(dep, self.hoy, limite=resto)
            ma = (datetime.strptime(self.hoy, "%Y%m%d") + timedelta(days=1)).strftime("%Y%m%d")
            try:
                manana = dia(dep, ma, self.hoy)
            except Exception:
                manana = []
            self.hoy_evs[dep] = hist.get(self.hoy, []) + manana
            partidos = _terminados(hist, self.hoy, dep)
            if len(partidos) < 200:
                raise RuntimeError(f"muy pocos partidos ({len(partidos)})")
            self.mod[dep] = Modelo(dep, partidos)
            print(f"  modelo {dep}: {len(partidos)} partidos jugados, {len(self.mod[dep].n)} equipos "
                  f"({time.time() - self.t0:.0f}s)", flush=True)
        except Exception as e:
            print(f"  modelo: falló {dep}: {e}", flush=True)
            self.fallidos.add(dep)
        return self.mod.get(dep)

    def evento(self, dep, local, visita, inicio):
        mejor, puntos = None, 0.0
        for e in self.hoy_evs.get(dep, []):
            t = _hora(e["t"])
            if inicio and t and abs((t - inicio).total_seconds()) > 3 * 3600:
                continue
            for inv in (False, True):
                hn, an = (e["an"], e["hn"]) if inv else (e["hn"], e["an"])
                s1, s2 = _sim(local, hn), _sim(visita, an)
                if not (s1 and s2):
                    continue
                p = s1 + s2 - (0.01 * abs((t - inicio).total_seconds()) / 3600 if t and inicio else 0)
                if p > puntos:
                    mejor, puntos = (e, inv), p
        return mejor

    def calcular(self, pick, local, visita, inicio):
        """Devuelve (prob en %, texto) para el equipo del pick, o (None, motivo)."""
        dep = DEPORTE.get(pick.get("deporte"))
        if not dep or dep == "baseball":
            return None, "sin datos propios para este deporte"
        if dep in SIN_NUMERO:
            return None, SIN_NUMERO[dep]
        mod = self.asegurar(dep)
        if not mod:
            return None, "sin datos del modelo hoy"
        hallado = self.evento(dep, local, visita, inicio)
        if not hallado:
            return None, "partido no encontrado en LiveScore"
        e, inv = hallado
        fav = pick["apuesta"].replace("Gana ", "", 1)
        lado_local = _sim(fav, e["hn"]) >= _sim(fav, e["an"])
        p = mod.prob(e["h"], e["a"], **AJUSTE.get(dep, {}))
        if not p:
            return None, f"pocos partidos ({mod.n.get(e['h'], 0)} y {mod.n.get(e['a'], 0)})"
        pw = p[0] if lado_local else p[2]
        return round(pw * 100, 1), f"{mod.n.get(e['h'], 0)} y {mod.n.get(e['a'], 0)} partidos"


# Ajustes de calibración por deporte (se fijan con la prueba contra partidos ya jugados: scripts/prueba_modelo.py)
AJUSTE = {"basketball": {"k": 1.0}, "soccer": {"k": 1.0, "empate": 1.0}, "hockey": {"k": 1.2},
          "american-football": {"k": 1.3}}
# Tenis: en la prueba del 15-nov-2026 el Elo con datos de LiveScore no fue confiable -> no se muestra número.
SIN_NUMERO = {"tennis": "en tenis nuestro modelo aún no es confiable"}
