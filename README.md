# Gegenpress

**Football's broadcast tells you a press was fast. Gegenpress tells you it was fast *for him*.**

Built for the Microsoft × Premier League *Inside the Game* Developer Hackathon. All clubs, players and matches are synthetic. No real match data is used.

The name is deliberate: *gegenpressing* is the one piece of football tactics defined by a measurement — win the ball back within about five seconds. Recovery time is a first-class metric here, and the name states the thesis.

---

## The five stages

| Stage | Where it lives | What it does |
| --- | --- | --- |
| **Ingest** | [`simulate.py`](src/gegenpress/simulate.py), [`season.py`](src/gegenpress/season.py) | Deterministic possession-chain engine; a season played by a persistent squad |
| **Interpret** | [`kql/02_functions.kql`](kql/02_functions.kql), [`baselines.py`](src/gegenpress/baselines.py) | Rolling match state and two reference classes, computed in KQL on Azure Data Explorer |
| **Explain** | [`form.py`](src/gegenpress/form.py), [`signal.py`](src/gegenpress/signal.py), [`agents.py`](src/gegenpress/agents.py) | Significance measured, not asserted — and refused where it isn't supportable |
| **Render** | [`docs/index.html`](docs/index.html), [`feed.py`](src/gegenpress/feed.py) | Broadcast console — a tracking main camera over the real match — and a timed, machine-readable overlay cue feed |
| **Personalize** | `FollowTarget()`, Analyst/Fan modes | Follow modes bound to a role, not a dropdown |

## Quickstart

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install pytest

PYTHONPATH=src python -m gegenpress form        # the differentiator, on one screen
PYTHONPATH=src python -m gegenpress desk        # Scout -> Why -> Desk -> Gate
PYTHONPATH=src python -m gegenpress calibrate   # realism report
PYTHONPATH=src python -m pytest -q              # 51 tests

PYTHONPATH=src python -m gegenpress feed
python -m http.server -d docs 8000              # the console at localhost:8000
```

---

## The idea: two reference classes

Commentary is comparative, and there is more than one thing to compare against.

```
* Mateo Oyelaran: pass range 15.2 tonight against a season norm of
  13.9 (+1.9 SD over 18 matches).
    league percentile 61%   effect 0.50 SD of league spread
```

Sixty-first percentile is unremarkable. Against his own season it is a big night. That second sentence needs a season of **persistent players** to be sayable at all, and it is the thing this project exists to say.

**The unit is the match, not the event.** A personal best fires about eight times a match and is almost always league-exceptional too, so at the single-event level the second number adds nothing. Match form is where the two separate.

**Form is a z-score, not a percentage.** A player makes ~90 passes a match but ~10 carries, so the same percentage swing is routine in one and extraordinary in the other.

**Statistical significance is not narrative significance.** A tight distribution means a 0.4 m/s drop can clear 2 SD while being invisible to a viewer, so a claim must also move at least 0.25 of the league's spread before it is surfaced.

### The system refuses claims it cannot support

Not every metric can carry a personal claim. `recovery_time` measures how long a possession lasted — a property of the match, not of whoever won the ball back. Counter-pressing is a team behaviour. So the system measures between-player signal and declines the claim where there is none.

| metric | ICC | claims allowed |
| --- | --- | --- |
| top speed | 0.577 | personal + league |
| ball speed | 0.452 | personal + league |
| pass range | 0.112 | personal + league |
| carry range | 0.097 | personal + league |
| pass difficulty | 0.022 | league only |
| recovery time | 0.006 | league only |

ICC is between-player variance over total variance; near zero means every player's distribution is the league's wearing his name. Computed identically in [`signal.py`](src/gegenpress/signal.py) and in KQL as `MetricSignal()`.

**The threshold is derived, not chosen.** A form line is always a mean, and Spearman-Brown gives the reliability of a 50-observation mean from the single-observation ICC. Solving for the value that puts that mean on [Koo & Li's](https://pmc.ncbi.nlm.nih.gov/articles/PMC4913118/) "good reliability" boundary of 0.75 gives 0.057; the gate uses 0.08, stricter, because touches cluster within matches so the effective sample is smaller than the raw count. Every metric the gate allows yields a player mean of *good* reliability or better, and every metric it refuses does not.

**And the mechanism is real, not an artefact of the simulator.** Published football ICCs span **0.03 to 0.91**: [PLOS ONE (2022)](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0262274) measures PlayerLoad at ICC 0.79–0.91 and high-speed running — a headline broadcast metric — at **0.03–0.53**, with within-subject variation up to 244% and a signal-to-noise ratio they could not compute. Same players, same sessions, an order of magnitude apart in how much the number says about the individual. Their own recommendation is to assess reliability at the individual level, which is what this does.

The specific values here would not transfer to real tracking data and are not claimed to. [`docs/SIGNAL.md`](docs/SIGNAL.md) has the derivation, the literature, and an explicit account of what that evidence does and does not license.

Every entry in this field verifies that its numbers are true. This checks whether the **sentence is sayable** — a different and stricter question.

---

## Architecture

```
season generator ──> Azure Data Explorer (KQL) ──> agents ──> console
  persistent          Ground, MatchState,          Scout        overlay cues
  squad, seeded       MetricSignal, FollowTarget   Why          follow modes
                                                   Desk
                                                   Gate
```

Match state sits behind one interface with two implementations — `LocalStore` in Python and `AdxStore` running the KQL. The agent layer talks to the interface and does not know which is behind it, so the pipeline is never blocked on a cloud resource.

### Azure services actually in the request path

| Service | Role | Status |
| --- | --- | --- |
| **Azure Data Explorer** | Event store; all match-state and grounding queries | **Verified on a live free cluster** — 153,041 events, 10/10 functions |
| Microsoft Foundry | Model for the Desk agent | Adapter written ([`agents.py`](src/gegenpress/agents.py)); falls back to deterministic templates when unconfigured |

The KQL is plain Kusto and runs unchanged on a Fabric Eventhouse; only the connection string differs.

**Known limitation, stated rather than hidden:** a free ADX cluster refuses `.alter table ... policy streamingingestion enable`, so ingestion is queued and events are queryable after a minute or two rather than instantly. The architecture is right for live play; the free tier isn't. On a paid cluster or an Eventhouse, enable streaming in [`kql/01_schema.kql`](kql/01_schema.kql).

### Running it against Azure

```bash
pip install azure-kusto-data azure-kusto-ingest
export ADX_CLUSTER="https://<cluster>.kusto.windows.net"
export ADX_DATABASE="gegenpress"

PYTHONPATH=src python -m gegenpress ingest --bootstrap --reset --load
PYTHONPATH=src python -m gegenpress doctor      # row counts + every function
PYTHONPATH=src python -m gegenpress state --adx
```

---

## Evidence

**Realism.** The generator is tuned on seed 2026 and checked against reported top-flight per-match averages. These are plausibility targets for synthetic output; no real data is ingested.

| metric | observed | target | tolerance |
| --- | --- | --- | --- |
| goals per match | 2.53 | 2.80 | 0.60 |
| shots per match | 26.7 | 25.0 | 7.0 |
| passes per match | 997 | 900 | 180 |
| pass accuracy | 0.83 | 0.82 | 0.06 |
| mean shot xG | 0.10 | 0.10 | 0.04 |
| recoveries per match | 240 | 210 | 70 |

**7/7, and the suite re-runs the whole check on seeds 7, 404 and 11111 — seeds the generator was never tuned against.** Calibration that only holds on its own tuning seed is not calibration.

**Parity.** `tests/test_store.py::test_local_and_adx_agree` compares the Python implementation's ranked moments against the KQL's — event for event, value for value, and the ICC gate itself, since `variancep` in KQL and `pvariance` in Python are two implementations of one definition and two implementations drift. It skips when `ADX_CLUSTER` is unset so CI stays green without Azure.

```bash
export ADX_CLUSTER="https://<cluster>.kusto.windows.net"
bash scripts/verify_parity.sh     # rebuild, ingest, wait for queued ingestion, assert parity
```

**Status: not yet green end to end.** The KQL layer is verified on a live cluster (row counts and all eleven functions, above), but this specific test has not been run against one since the schema and the live match id last changed. It is listed here as the check that exists, not as a result that has been obtained — stating that is cheaper than the alternative, in a project whose argument is that claims should be refused when they cannot be supported.

**The load-bearing test.** `test_form_lines_diverge_from_league_percentile`, across three seeds, asserts that moments exist which are strong for the player but ordinary league-wide. If that ever stops being true the Form Line is decoration and the project has no differentiator — which was literally true of an earlier version of the model.

**Evaluation.** Microsoft's built-in Groundedness evaluator scores 1–5 with a model as judge and Groundedness Pro needs the Content Safety service. Neither is used here, because the Gate is deterministic and can therefore be measured deterministically — the result is a fact rather than another model's opinion. `python -m gegenpress eval` runs 373 claims across three seeds and twelve matches:

| check | result | |
| --- | --- | --- |
| gate precision | **100.0%** | 373/373 valid claims passed — a false reject silences a true statement |
| claim integrity | **100.0%** | every asserted number recomputes from the events |
| refusal correctness | **100.0%** | no personal claim on a metric without between-player signal |

Gate recall, by how the claim was corrupted:

| corruption | caught | |
| --- | --- | --- |
| invented number | **100.0%** | 373/373 |
| inflated number | **99.2%** | 370/373 |
| fabricated scoreline | **100.0%** | 373/373 |
| number spelled as words | **0.0%** | known miss — the Gate reads digits |
| misattached number | **0.0%** | known miss — presence is checked, not attachment |
| **digit-based** | **99.7%** | what the Gate claims to catch |
| **overall** | **59.8%** | including both documented misses |

The three missed inflations are not ordinary failures: in each case the corrupted value coincidentally equalled a *different* number already in the brief, so presence-checking cannot see it. That is the same structural limit as a misattached number, and it is why the honest claim is *the Gate removes invented numbers*, not *the Gate makes the sentence true*.

Publishing 0.0% twice is deliberate. A measured zero on a known weakness is worth more than prose describing it, and `tests/test_evaluate.py` pins both so that fixing one is noticed.

**The graphics package.** Six independent entries in this field converged on the same interface — system-ui, rounded blurred cards, pill buttons, amber on slate — without anyone copying anyone, and so did the first two versions of this console. [`docs/DESIGN.md`](docs/DESIGN.md) records that convergent default as a list of things not to reach for, the broadcast research that replaced it, and the system built from it: Archivo's **width** axis rather than weight alone (expanded figures, narrow names), the league's purple family with its signal colours carrying the claim, and hard-edged opaque planes flush to the screen edges.

**The camera.** The console is not a tactics board seen from above. It is a tracking main camera in the stand — 42m back, 28m up, 21° of depression — that dollies along the touchline with the ball, and all 22 players are drawn as figures with height, shadow, gait and facing rather than as markers. The choice is forced by arithmetic, not taste: framing the whole pitch at 1440px puts a 1.85m player at 8 pixels, which no amount of detail rescues. Holding ~70m of pitch in frame puts him at 29–53px, which is enough for a kit, a stride and a number. `Wide` pulls out to the full pitch when the shape matters more than the people.

**The surface and the sound.** Grass is a texture, not a fill: two-tone mow bands, a faint cross-cut, wear at the goalmouths and down the central channel, mottle and blade grain, baked once in pitch coordinates and drawn through the camera as exact per-row strips (the camera has no roll, so every pitch row maps to one screen row — mode-7, but exact). The crowd is a **real one**: the bed and the goal roar are edited from openly licensed stadium recordings ([credits](docs/audio/CREDITS.md), Pixabay Content License), after five rounds of synthesis proved that ears beat DSP -- the full granular synthesizer survives in [`scripts/make_crowd.py`](scripts/make_crowd.py), which still renders the shot swell and documents the journey. The reactive layer is unchanged: the bed's level and brightness lean toward whichever box the ball is near, a chance gets a vocal swell, a goal gets the roar, driven by the same event stream as everything else on screen.

Nothing in the view is invented to make it look better. Positions come from [`positions.py`](src/gegenpress/positions.py), and the ball is rebuilt in the client from the event stream itself: football reads as football because the ball has two speeds, so each pass is a flight at a plausible ball speed — lofted long balls drawn at real height under the projection, shadow staying on the turf — followed by a dwell at the receiver's feet until the next on-ball event. Restarts cut rather than travel, because broadcast never shows the ball streaking back to the centre spot. Stride length and run speeds are the ones [`calibrate.py`](src/gegenpress/calibrate.py) checks.

**Documented holes.** Two `xfail` tests in [`tests/test_agents.py`](tests/test_agents.py) pin what the Gate *cannot* do: it reads digits rather than words, and it checks that a number is present in the brief rather than correctly attached to the right thing. It removes invented numbers; it does not make the sentence true. Those are different claims and only the first is made.

---

## Layout

```
src/gegenpress/
  models.py      typed event contract; what KQL ingests
  season.py      persistent league, squads, fixtures
  simulate.py    possession-chain match simulation
  baselines.py   population and personal reference classes
  signal.py      per-metric ICC; which claims are supportable
  form.py        the Form Line
  agents.py      Scout, Why, Desk, Gate
  store.py       Store interface + LocalStore
  adx.py         Azure Data Explorer backend, ingestion, doctor
  feed.py        broadcast feed and overlay cues
  calibrate.py   realism checks
kql/             schema and eleven KQL functions
docs/            the studio console (served by GitHub Pages)
```
