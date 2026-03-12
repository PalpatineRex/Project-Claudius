import urllib.request, json

payload = json.dumps({
    "model": "llama3.2:3b",
    "stream": False,
    "messages": [{"role": "user", "content": "Bonjour, qui es-tu ?"}]
}).encode("utf-8")

req = urllib.request.Request(
    "http://localhost:11434/api/chat",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST"
)
try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
        print("OK:", data["message"]["content"][:100])
except Exception as e:
    import traceback; traceback.print_exc()
