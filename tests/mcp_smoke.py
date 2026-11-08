"""Talks to the connector the way the Claude app does (MCP over stdin/stdout).

    python tests/mcp_smoke.py <command to start the connector...>
e.g. python tests/mcp_smoke.py "dist/Human Typer.exe" --mcp
"""
import json
import subprocess
import sys

cmd = sys.argv[1:]
p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding="utf-8")


def send(msg):
    p.stdin.write(json.dumps(msg) + "\n")
    p.stdin.flush()


def reply(want_id):
    while True:
        line = p.stdout.readline()
        if not line:
            raise SystemExit("connector closed without answering")
        msg = json.loads(line)
        if msg.get("id") == want_id:
            return msg


send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
    "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "smoke", "version": "1"}}})
init = reply(1)
print("server:", init["result"]["serverInfo"]["name"])
send({"jsonrpc": "2.0", "method": "notifications/initialized"})
send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
tools = sorted(t["name"] for t in reply(2)["result"]["tools"])
print("tools:", tools)
assert {"type_text", "check_writing", "fix_apa_citations", "apa_reference", "stop_typing", "typing_status"} <= set(tools)
send({"jsonrpc": "2.0", "id": 3, "method": "prompts/list"})
print("prompts:", [x["name"] for x in reply(3)["result"]["prompts"]])
send({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {
    "name": "check_writing", "arguments": {"text": "i went to teh shop and we was tired", "level": 4}}})
out = reply(4)["result"]["content"][0]["text"]
print("check_writing:", out.splitlines()[0], "|", out.splitlines()[-1])
assert "the shop" in out and "were" in out
p.stdin.close()
p.wait(timeout=10)
print("connector ok")
