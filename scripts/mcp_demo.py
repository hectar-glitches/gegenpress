"""Watch the gegenpress MCP server answer, in one command.

    python scripts/mcp_demo.py

Starts the server exactly as an MCP host would (a subprocess speaking
JSON-RPC over stdio), lists its tools, and makes the calls that show what
it is for -- including the two a stats feed cannot make: a refusal, and a
claim being checked.
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

BOLD, DIM, GRN, RED, CYN, END = ("\033[1m", "\033[2m", "\033[32m", "\033[31m",
                                 "\033[36m", "\033[0m")


def show(title: str, payload: str, colour: str = CYN) -> None:
    print(f"\n{BOLD}{colour}▸ {title}{END}")
    try:
        body = json.dumps(json.loads(payload), indent=2)
    except (json.JSONDecodeError, TypeError):
        body = payload
    for line in body.splitlines()[:22]:
        print(f"  {line}")
    if len(body.splitlines()) > 22:
        print(f"  {DIM}…{END}")


async def main() -> int:
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except ImportError:
        print("the MCP SDK is not installed. run:\n  pip install mcp")
        return 2

    params = StdioServerParameters(
        command=sys.executable, args=["-m", "gegenpress", "mcp"],
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")})

    print(f"{DIM}starting: {sys.executable} -m gegenpress mcp  (stdio){END}")
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = await s.list_tools()
            print(f"\n{BOLD}connected — {len(tools.tools)} tools:{END}")
            for t in tools.tools:
                first = (t.description or "").strip().splitlines()
                print(f"  • {t.name}" + (f"  {DIM}{first[0][:70]}{END}" if first else ""))

            async def call(name: str, args: dict) -> str:
                res = await s.call_tool(name, args)
                return res.content[0].text

            show("match_info()", await call("match_info", {}))
            show('form_line("Noor Kowalski", "pass range", as_of_minute=30)',
                 await call("form_line", {"player": "Noor Kowalski",
                                          "metric": "pass range",
                                          "as_of_minute": 30}))
            show('form_line("Noor Kowalski", "recovery time")   ← no signal: refused',
                 await call("form_line", {"player": "Noor Kowalski",
                                          "metric": "recovery time"}), RED)

            fl = json.loads(await call("form_line", {
                "player": "Noor Kowalski", "metric": "pass range", "as_of_minute": 30}))
            true_claim = fl["sayable_claim"]
            show(f'verify_claim("{true_claim[:60]}…")   ← measured: passes',
                 await call("verify_claim", {"text": true_claim,
                                             "player": "Noor Kowalski",
                                             "metric": "pass range",
                                             "as_of_minute": 30}), GRN)
            show('verify_claim("…pass range of 21.4 tonight…")   ← invented: rejected',
                 await call("verify_claim", {
                     "text": "Noor Kowalski is spraying it about, pass range of 21.4 tonight.",
                     "player": "Noor Kowalski", "metric": "pass range",
                     "as_of_minute": 30}), RED)
    print(f"\n{DIM}server stopped.{END}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
