import json, os, re, urllib.request, urllib.parse
from datetime import datetime, timedelta, timezone

hoy = (datetime.now(timezone.utc) - timedelta(hours=4)).strftime("%Y-%m-%d")  # hora de Caracas
html = open("index.html", encoding="utf-8").read()
m = re.search(r'<script id="data" type="application/json">(.*?)</script>', html, re.S)
fecha = json.loads(m.group(1)).get("fecha")
if fecha == hoy:
    print("OK, la pagina ya tiene los picks de hoy"); raise SystemExit(0)

text = (f"⚠️ El robot NO actualizó los picks de hoy ({hoy}).\n"
        f"La página sigue con los del {fecha}.\n"
        "Abre Claude y escribe: \"bot deportivo, no llegaron los picks de hoy\".")
api = f"https://api.telegram.org/bot{os.environ['TELEGRAM_TOKEN']}"
data = urllib.parse.urlencode({"chat_id": os.environ["TELEGRAM_CHAT_ID"], "text": text}).encode()
print(json.load(urllib.request.urlopen(f"{api}/sendMessage", data=data)))
