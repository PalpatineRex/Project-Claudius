"""
KinectTranscript.py - Serveur transcript temps reel pour Claudius
Ouvre http://localhost:5005 dans Chrome pour voir la conversation.
Lance en parallele de KinectBridge.
"""
from flask import Flask, Response, send_from_directory, request, jsonify
import os, time

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR = os.environ.get("CLAUDIUS_DATA_DIR", _SCRIPT_DIR)
TRANSCRIPT_FILE = os.path.join(_DATA_DIR, "transcript.txt")
app = Flask(__name__)

HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<title>Claudius — Transcript</title>
<style>
  body { background:#0d0d0d; color:#e0e0e0; font-family:'Segoe UI',monospace; font-size:15px; margin:0; padding:16px; }
  h2 { color:#7ec8e3; margin:0 0 12px; letter-spacing:2px; font-size:13px; text-transform:uppercase; }
  #log { display:flex; flex-direction:column; gap:6px; }
  .david { color:#aad4f5; }
  .claudius { color:#b8f5a0; }
  .ts { color:#555; font-size:12px; margin-right:6px; }
  .name { font-weight:bold; margin-right:4px; }
  #status { position:fixed; top:8px; right:12px; font-size:11px; color:#444; }
</style>
</head>
<body>
<h2>🎙 Claudius — Conversation en direct</h2>
<div id="log"></div>
<div id="status">⏳</div>
<script>
let lastLen = 0;
async function poll() {
  try {
    const r = await fetch('/lines?from=' + lastLen);
    const data = await r.json();
    if (data.lines.length) {
      const log = document.getElementById('log');
      data.lines.forEach(line => {
        const m = line.match(/^\\[(\\d{2}:\\d{2}:\\d{2})\\] (David|Claudius): (.+)$/);
        if (!m) return;
        const [, ts, who, txt] = m;
        const cls = who === 'David' ? 'david' : 'claudius';
        const div = document.createElement('div');
        div.className = cls;
        div.innerHTML = `<span class="ts">${ts}</span><span class="name">${who}</span>${txt}`;
        log.appendChild(div);
        div.scrollIntoView({behavior:'smooth'});
      });
      lastLen = data.total;
    }
    document.getElementById('status').textContent = '● live';
  } catch(e) {
    document.getElementById('status').textContent = '✗ offline';
  }
  setTimeout(poll, 800);
}
poll();
</script>
</body>
</html>"""

@app.route("/")
def index():
    return HTML

@app.route("/lines")
def lines():
    start = int(request.args.get("from", 0))
    try:
        with open(TRANSCRIPT_FILE, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
        new = [l.rstrip() for l in all_lines[start:]]
        return jsonify({"lines": new, "total": len(all_lines)})
    except FileNotFoundError:
        return jsonify({"lines": [], "total": 0})

if __name__ == "__main__":
    print("[TRANSCRIPT] http://localhost:5005")
    app.run(host="0.0.0.0", port=5005, debug=False, use_reloader=False)
