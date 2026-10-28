# Data protection impact assessment — draft

GDPR / UK GDPR Art. 35, for a deployer putting real players' Form Lines
on air. Following the article's structure: (a) what the processing is,
(b) whether it is necessary and proportionate, (c) the risks to the
players, (d) the measures that address them. Each measure links to the
code that implements it and the test that keeps it implemented.

*A draft prepared by the engineering team for the deployer's DPO. It
states what the system does; the legal conclusions are the DPO's and
counsel's to reach.*

## Why a DPIA

The processing evaluates individual people's performance (Art. 4(4)
profiling), systematically, every match, and publishes the result to a
mass audience. That combination makes a DPIA the prudent default even
where a regulator's list does not strictly require one.

## (a) The processing

Match events naming a player are ingested into Azure Data Explorer. For
each metric, the system measures whether players differ enough from one
another for a personal comparison to mean anything (the ICC gate). Where
they do, it compares the player's live match with his own season (the
Form Line). A writer, either a template or an AI model, phrases that as
one sentence. A deterministic gate checks every number in the sentence
against the measurements. The sentence goes to air on screen, as speech
for audio description, and through an MCP server. See the
[record of processing](ROPA.md) for the data categories, recipients and
retention.

## (b) Necessity and proportionality

- **Lawful basis.** Legitimate interests (Art. 6(1)(f)) is the likely
  candidate: sports broadcasting analysis of professional performance in
  public matches. That needs a balancing test; this draft does not supply
  one. Consent is unsuitable in an employment-adjacent setting (FIFPRO and
  the Morgan Lewis analysis below both flag this).
- **Minimisation.** Only event data is used: no wearables, no medical, no
  contracts. Viewers' data is not processed at all.
- **Accuracy is built in, not hoped for.** A claim cannot carry a number
  the data does not support. Gate precision, claim integrity and refusal
  correctness are held at 100% by a build that fails otherwise.
- **Retention** is two seasons: the minimum the comparison needs.

## (c) Risks to the players, and (d) the measures

| # | Risk | Likelihood without measures | Measure | Evidence | Residual |
| --- | --- | --- | --- | --- | --- |
| 1 | **An inaccurate claim goes to air**, harming reputation or market value. | High for any AI writer: models invent plausible numbers. | Deterministic gate on every digit. Template fallback when a model fails it. Per-claim provenance hashes to detect edits after the gate. | `eval` in CI; [`test_browser_gate.py`](../../tests/test_browser_gate.py); `verify-feed` | Low. The gate's two documented misses (spelled-out numbers; a real number attached to the wrong thing) are measured and published. |
| 2 | **An unfair claim**: a player is called slow or poor on a metric that measures the match, not him. | Medium. Recovery time looks personal and is not (ICC 0.006). | ICC gate refuses personal claims below 0.08 (Koo & Li). | [`test_form.py`](../../tests/test_form.py), [`test_agents.py`](../../tests/test_agents.py) | Low |
| 3 | **AI-written text airs without editorial responsibility.** | Medium if a model is enabled. | A model-written sentence is a draft until a named producer approves it. The template airs meanwhile. Decisions go to an append-only log. On screen, any AI-written line says so and names who approved it. | [`test_editorial.py`](../../tests/test_editorial.py), [`test_compliance.py`](../../tests/test_compliance.py) | Low |
| 4 | **Function creep**: Form Lines used for selection, contracts or betting. | Medium. The MCP server makes the data easy to reach. | Purpose stated in the [record of processing](ROPA.md). In production the MCP server and console sit behind Entra ID ([`staticwebapp.config.json`](../staticwebapp.config.json)). | Config written, **not deployed** | Medium until access control is deployed and use is logged |
| 5 | **Health-adjacent data.** Top speed and distance may be read as physical condition. | Low to medium. | Event-derived only, no physiological measures. Distance covered is a display figure from the position model, never a claim. | — | **Open question for counsel** |
| 6 | **The player cannot see or take his data.** | Certain without a tool. | `export` / `export_player_data`: everything held, and everything said about him, in one JSON document. | [`test_privacy.py`](../../tests/test_privacy.py) | Low |
| 7 | **Data kept indefinitely.** | High by default in any event store. | ADX retention 730 days. Two-step purge for erasure. | [`kql/03_retention.kql`](../../kql/03_retention.kql) | Low once applied. **Not applied**: the free cluster rejects policy commands |

## Sign-off

| | Name | Date | Decision |
| --- | --- | --- | --- |
| DPO | | | |
| Product owner | | | |
| Player representative (recommended, given FIFPRO's Charter) | | | |

Sources on player data as personal data:
[Morgan Lewis, July 2026](https://www.morganlewis.com/pubs/2026/07/soccers-big-data-dilemma-who-owns-the-data-behind-the-beautiful-game).
