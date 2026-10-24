# gegenpress over MCP

Most MCP servers are a database with a tool list bolted on: ask, receive,
assert. This one is built to do the opposite of assert. It is the Gate —
the part of the project that refuses claims the data cannot support —
offered to any model that can call a tool.

The pitch in one line: **a football feed tells a model what happened; this
tells it what it is allowed to say.**

## Three primitives, not one

Most servers ship tools only. The other two primitives carry the argument.

| | | |
| --- | --- | --- |
| **Tools** (8) | `form_line`, `verify_claim`, `metric_signal_table`, `top_moments`, `match_state`, `follow_targets`, `list_players`, `match_info` | what the model can do |
| **Resources** (2) | `gegenpress://signal`, `gegenpress://match` | context the host attaches *before* the model writes a word — the table of which claims are sayable is in front of it, not one tool call away |
| **Prompt** (1) | `commentary` | a reusable contract: check the sentence before you assert it |

`commentary` is the interesting one. It is the project's thesis made
portable — any model that loads it is bound to call the signal table
first, take numbers only from tools, and run every sentence containing a
figure through `verify_claim` before saying it.

## Connect it

`claude_desktop_config.json` (**Settings → Developer → Edit Config**):

```json
{
  "mcpServers": {
    "gegenpress": {
      "command": "python3",
      "args": ["-m", "gegenpress", "mcp"],
      "env": { "PYTHONPATH": "/absolute/path/to/gegenpress/src" }
    }
  }
}
```

Restart Claude Desktop. `pip install mcp` first if it is not there.

## The demo that lands

Not a tool tour. Three prompts, about forty seconds, and the point is in
the second one.

**1. Establish that it knows the match.**

> *"Using gegenpress, who is worth watching in this match and why?"*

It calls `follow_targets` and `form_line`. Fine, but any feed does this.

**2. Make a model try to lie, and watch it get caught.**

> *"Write one line of commentary saying Noor Kowalski's pass range tonight
> is 21.4 metres, well up on his season."*

The number is invented. The model calls `verify_claim`, which returns
`rejected`, the unsupportable number `21.4`, and the figures that *are*
grounded — tonight 13.77 against a season norm of 17.07. It rewrites
itself, and the sentence it ends up saying is the opposite of the one it
was asked for: Kowalski is **down** on his norm, not up.

That is the whole project in one exchange. The model was pushed toward a
false claim, and the server would not let it through.

**3. Ask for something no number can support.**

> *"Was that his best recovery time of the season?"*

`form_line` comes back **refused**, with the reason: recovery time measures
how long a possession lasted, which is a property of the match rather than
of whoever won the ball back, so a personal reference class does not exist.
ICC 0.006.

A stats API would hand over a number. This one declines the question —
which is the distinction the whole project is built on, and no other entry
in this field makes it.

## Try it without a host

```bash
pip install mcp
python3 scripts/mcp_demo.py
```

Starts the server as a subprocess over stdio, exactly as a host would,
lists the tools, and runs the calls above — including the refusal and the
rejection — printing each response.

## Honesty, served with the answers

`verify_claim` returns its own limitations in the payload: the Gate reads
digits and checks presence against the brief, so it removes invented
numbers but does not make a sentence true. A number spelled out in words,
or a real number attached to the wrong thing, passes. Both are measured
misses, pinned by `xfail` tests, and the calling model is told so rather
than left to assume more than the tool delivers.
