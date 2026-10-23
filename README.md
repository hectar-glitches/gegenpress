# Gegenpress — the synthetic season

Football's broadcast tells you *what happened*. Gegenpress tells you *how unusual it was* — and then lets you follow unusualness itself.

This repository is stage one of the pipeline: a deterministic synthetic football generator that produces **a season played by a persistent squad**, and a grounding layer that scores every live measurement against two reference classes.

Built for the Microsoft × Premier League *Inside the Game* Developer Hackathon. All clubs, players and matches are invented. No real match data is used.

The name is deliberate: *gegenpressing* is the one piece of football tactics defined by a measurement — win the ball back within roughly five seconds of losing it. `recovery_time_s` is a first-class metric here, and "recovery in 4.2s, expected 6.5s" is exactly the kind of claim this system exists to make.

## The idea in one number

Simulate a full season offline. Now every live event carries an **expected-vs-actual delta**, and that one quantity does three jobs:

| Job | How the delta is used |
| --- | --- |
| Explain | "Recovery in 4.2s — expected 6.5s" |
| Render | Moments are ranked by how far they sit into the good tail |
| Personalize | Follow whoever is beating expectation hardest right now |

## The Form Line

A league percentile tells you a press was fast. The Form Line tells you it was fast **for him**.

```
* Mateo Oyelaran: pass range 15.2 tonight against a season norm of
  13.9 (+1.9 SD over 18 matches).
    league percentile 61%   effect 0.50 SD of league spread
```

Sixty-first percentile is unremarkable. Against his own season it is a big night. That is the sentence a commentator reaches for, and it needs a season of persistent players to be sayable at all.

**The unit is the match, not the event.** A personal best fires about eight times a match and is almost always league-exceptional too, so at the single-event level the second number adds nothing. Match form is where the two separate — and "he's been everywhere tonight" was always a claim about a match.

**Form is a z-score, not a percentage.** A player makes ~90 passes a match but ~10 carries, so the same percentage swing is routine in one and extraordinary in the other. The z-score against that player's own distribution of match means puts every metric on one scale.

**Statistical significance is not narrative significance.** A tight distribution means a 0.4 m/s drop can clear 2 SD while being invisible to a viewer. A claim must also be material — at least 0.25 of the league's spread — before it is surfaced.

### The system refuses claims it cannot support

Not every metric can carry a personal claim. `recovery_time_s` measures how long a possession lasted, which is a property of the match rather than of whoever won the ball back — counter-pressing is a team behaviour. So the system measures between-player signal and refuses the claim when it is absent.

| metric | ICC | claims allowed |
| --- | --- | --- |
| top_speed_ms | 0.577 | personal + league |
| ball_speed_ms | 0.452 | personal + league |
| pass_distance_m | 0.112 | personal + league |
| carry_distance_m | 0.097 | personal + league |
| pass_difficulty | 0.022 | league only |
| recovery_time_s | 0.006 | league only |

ICC is between-player variance over total variance: near zero means every player's distribution is the league's wearing his name.

Every entry in this field verifies that its numbers are true. This checks whether the *sentence is sayable* — a different and stricter question. `python -m gegenpress form` prints the whole thing.

## Two reference classes

Commentary is comparative, but there is more than one thing to compare against:

- **Population** — "beats 99.8% of the league." Statcast's expected-stats framing.
- **Personal** — "his season best; his average is 17.6m." What a commentator actually says.

The second only means anything because players carry **permanent attributes** across the whole season, so match-to-match variation is real variation around a real ability rather than two draws from the same noise. `tests/test_season.py::test_player_attributes_persist_across_the_season` pins that premise, and `test_better_passers_complete_more_passes` proves attributes actually drive outcomes.

## Quickstart

```bash
PYTHONPATH=src python3 -m gegenpress demo          # season + one live match, narrated
PYTHONPATH=src python3 -m gegenpress calibrate     # realism report
PYTHONPATH=src python3 -m gegenpress season --out data   # write events.jsonl + baselines
PYTHONPATH=src python3 -m pytest tests/ -q
```

A 90-match season is ~150,000 events and takes about 2.5 seconds.

## Realism report

The generator is tuned on seed 2026 and checked against widely reported top-flight per-match averages. These are plausibility targets for synthetic output — no real data is ingested.

| metric | observed | target | tolerance | result |
| --- | --- | --- | --- | --- |
| goals_per_match | 2.53 | 2.80 | 0.60 | pass |
| shots_per_match | 26.74 | 25.00 | 7.00 | pass |
| passes_per_match | 996.68 | 900.00 | 180.00 | pass |
| pass_accuracy | 0.83 | 0.82 | 0.06 | pass |
| mean_shot_xg | 0.10 | 0.10 | 0.04 | pass |
| recoveries_per_match | 240.03 | 210.00 | 70.00 | pass |
| events_per_match | 1662.29 | 2000.00 | 900.00 | pass |

**7/7 passing, and the suite re-runs the whole check on seeds 7, 404 and 11111 — seeds the generator was never tuned against.** Calibration that only holds on its own tuning seed is not calibration.

## The match state layer

Match state lives behind one interface with two implementations:

| | Backend | Needs Azure |
| --- | --- | --- |
| `LocalStore` | pure Python, mirrors the KQL | no |
| `AdxStore` | Azure Data Explorer / Fabric Eventhouse | yes |

```bash
python -m gegenpress state                      # local, always works
export ADX_CLUSTER=https://<you>.kusto.windows.net
python -m gegenpress ingest --bootstrap --load  # create schema, load a season
python -m gegenpress state --adx                # same output, served by KQL
```

The agent layer talks to the interface and does not know which is behind it. That is deliberate: the pipeline is never blocked on a cloud resource, and the demo has a working fallback if a quota bites on the day.

The real analytics are in [`kql/02_functions.kql`](kql/02_functions.kql) — `Ground()` scores a live value against both reference classes using 101 percentile cut points, `MatchState()` computes rolling team state including the namesake `gegenpress_idx`, and `FollowTarget()` makes "follow whoever is beating expectation hardest right now" a query rather than a dropdown. All of it is plain KQL and runs unchanged on a Fabric Eventhouse; only the connection string differs.

Two implementations of the same semantics will drift, so `tests/test_store.py::test_local_and_adx_agree` checks they return the same ranked moments. It skips when `ADX_CLUSTER` is unset, so CI stays green without Azure. **The KQL is unverified until it has run against a real cluster** — the parity test is how that gets confirmed, not an assumption.

## Layout

```
src/gegenpress/
  models.py      typed event contract; what KQL ingests
  names.py       invented clubs and players
  season.py      persistent league, squads, fixtures
  simulate.py    possession-chain match simulation
  baselines.py   the two reference classes, and grounding
  calibrate.py   realism checks against football-realistic targets
  store.py       Store interface + LocalStore
  adx.py         Azure Data Explorer backend and season ingestion
  cli.py         season / demo / state / ingest / calibrate
kql/
  01_schema.kql     tables, mappings, streaming ingestion policy
  02_functions.kql  Ground, TopMoments, MatchState, FollowTarget
```

## Event contract

Every event is flat and ready for streaming ingestion:

```json
{
  "event_id": "m01-ash-jar-e00412", "match_id": "m01-ash-jar",
  "period": 1, "clock": 1287.4, "minute": 21,
  "team_id": "ash", "player_id": "ash-08", "type": "pass",
  "x": 44.2, "y": 31.8, "end_x": 61.9, "end_y": 24.1, "outcome": true,
  "detail": {
    "pass_distance_m": 21.4, "pass_difficulty": 0.512,
    "ball_speed_ms": 17.9, "pressure_count": 2,
    "receiver_id": "ash-11", "progressive": true
  }
}
```

`pass_difficulty` is a documented weighted function of distance, pressure and forwardness — deliberately transparent so the explanation layer can cite how it was derived rather than asserting it.

## Design notes

- **Deterministic.** Same seed, same league, same events, always. Tests pin it.
- **Attributes drive outcomes.** Pass completion is a function of difficulty and the passer's permanent `passing` rating; shot conversion of a distance-and-angle xG and the shooter's `finishing`.
- **Possession ends realistically.** Chains end on misplaced passes *and* on tackles, interceptions and the ball going out — without the second, recovery times grow an unrealistic tail. A test caught this.
- **Direction matters.** Low recovery time is good; high pass difficulty is good. `rarity()` knows which tail is remarkable per metric.

## Next

1. ~~Stream events into Azure Data Explorer; port the rolling-window metrics to KQL.~~ Written; needs a cluster to verify.
2. Agent layer on Microsoft Agent Framework + Foundry: Scout, Why, Desk, Gate.
3. Expose match state over MCP.
4. Studio console, overlay feed, role-bound follow modes.
