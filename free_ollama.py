import urllib.request, json
req = urllib.request.Request(
    "http://localhost:11434/api/generate",
    json.dumps({"model": "llama3.2:3b", "keep_alive": 0}).encode(),
    {"Content-Type": "application/json"}, "POST"
)
urllib.request.urlopen(req).read()
print("VRAM liberee")
