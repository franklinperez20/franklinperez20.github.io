import json, os, re, sys, urllib.request, urllib.parse

html = open("index.html", encoding="utf-8").read()
m = re.search(r'<script id="data" type="application/json">(.*?)</script>', html, re.S)
D = json.loads(m.group(1))

lines = [f"🤖 *Ganadores de hoy* – {D['fecha_texto']}", "_Solo ganador · todos están en Polymarket_", ""]
for i, p in enumerate(D["picks"], 1):
    marca = "🟢" if p["prob"] >= 80 else "🟡"
    lines.append(f"{i}. {p['deporte']} {p['apuesta']} – *{p['prob']:.1f}%* {marca}")
    lines.append(f"    {p['partido']} · {p['liga']} · {p['hora']}")
H = D.get("historial", [])
ok = sum(1 for h in H if h["r"] == "ok"); ko = sum(1 for h in H if h["r"] == "ko")
if ok + ko:
    lines += ["", f"📊 Historial: {ok} acertados / {ko} fallados ({round(ok*100/(ok+ko))}%)"]
lines += ["", "🔗 https://franklinperez20.github.io",
          "⚠️ Apuestas sencillas y montos pequeños: 80 % no es seguro."]
text = "\n".join(lines)
if os.environ.get("COMMIT_MSG","").startswith("Actualizacion") and D.get("aviso"):
    text = D["aviso"] + "\n\n🔗 https://franklinperez20.github.io"
elif os.environ.get("COMMIT_MSG","").startswith("Actualizacion"):
    sys.exit(0)

token = os.environ["TELEGRAM_TOKEN"]
chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
api = f"https://api.telegram.org/bot{token}"
if not chat:
    upd = json.load(urllib.request.urlopen(f"{api}/getUpdates"))
    chats = [u["message"]["chat"]["id"] for u in upd.get("result", []) if "message" in u]
    if not chats:
        sys.exit("No encuentro tu chat: escríbele /start a tu bot en Telegram y vuelve a ejecutar.")
    chat = str(chats[-1]); print("CHAT_ID detectado:", chat)

data = urllib.parse.urlencode({"chat_id": chat, "text": text, "parse_mode": "Markdown",
                               "disable_web_page_preview": "true"}).encode()
r = json.load(urllib.request.urlopen(f"{api}/sendMessage", data=data))
print("Enviado" if r.get("ok") else r)
