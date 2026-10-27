# Gegenpress

**Football's broadcast tells you a press was fast. Gegenpress tells you it was fast *for him*.**

[![ci](https://github.com/hectar-glitches/gegenpress/actions/workflows/ci.yml/badge.svg)](https://github.com/hectar-glitches/gegenpress/actions/workflows/ci.yml)

Built for the Microsoft × Premier League *Inside the Game* Developer Hackathon. **Category: Best Enterprise Solution.**

One deterministic gate decides what is allowed on screen, what gets spoken aloud, what an agent may say and what a Call it question may reveal. It refuses any number the data does not support, and any personal claim on a metric that measures the match rather than the man.

| | |
| --- | --- |
| **Live console** | **https://hectar-glitches.github.io/gegenpress/**. Opens paused on a diverging Form Line. No install, no key, no sign-in. |
| **Two-minute video** | _paste URL before submitting_ |
| **Try to make it lie** | Write a claim in the console's box and watch the gate strike out the number nobody measured. [More below.](#try-to-make-it-lie) |
| **For fans** | Every player's stats move as the match plays. *Call it*: guess above or below his own level before the reveal. Audio description of the whole match, in five languages. [More below.](#for-fans) |
| **Rules and regulations** | EU AI Act transparency with producer sign-off on any AI-written sentence. GDPR accuracy, fairness, access, portability, objection and retention. ePrivacy. The European Accessibility Act. WCAG 2.2 AA (axe-core: 0 violations in six states, run in CI). [Each one mapped to the control and the test that enforces it](docs/COMPLIANCE.md), with a [record of processing](docs/privacy/ROPA.md) and a [DPIA draft](docs/privacy/DPIA.md). |
| **Azure** | Azure Data Explorer on a live cluster: 11 KQL functions, with the ICC gate computed again in Kusto and held to the Python by a parity test. |
| **Agents** | Scout, Why, Desk and Gate share one closed `Brief`, with Desk on Microsoft Agent Framework. An MCP server exposes 9 tools, and `verify_claim` checks a sentence *before* a model says it. |
| **Data** | Synthetic: 10 clubs, 90 matches, 151,435 events. No real Premier League data. |

### Try to make it lie

The console has a text box. Type a sentence about the player on screen — *"his pass range is 21.4 tonight, the best of his season"* — and press Check. The console strikes `21.4` through, marks it **not measured**, and prints the sentence it will say instead: *pass range 13.77 tonight, against a season norm of 17.07*.

Every other system in this field asks you to believe its guardrail works. This one hands you the guardrail and invites you to beat it.

It is the same gate, not a demo of one. The numbers a claim may contain ship with each moment straight from the `Brief` the Python gate reads, the tolerance ships with the feed, and the page only finds digits and compares — so there is no second rule to drift. [Two tests run the page's own `gateMarks()` in Node against `Gate.unsupported()` in Python](tests/test_browser_gate.py) across every moment and insist they reach the same verdict, the same way the KQL is held to the Python. A sentence with no numbers in it is told *nothing to check — the gate reads numbers, not sentences*, because claiming otherwise would be the one dishonest thing on the page.

### For fans

**The match is live, and so are the players.** Every player's numbers move as the match does. The man on the ball carries a tag with his pass count, won-back count or shots, whichever his last touch moved, lit in his kit as it ticks, and his distance run, read off his own figure's path. A pass length rises off whoever played it. The claim's subject gains a *now* figure once a touch lands after his claim. All of this depends on the picture agreeing with the event log about who had the ball, and at first it didn't: the named passer was the nearest man only 13% of the time, a median 20 m away. Players now see their own next touch a few seconds out, and the named man is nearest on 90% of touches and within 3 m on 83% of passes, [tested off the shipped feed](tests/test_alignment.py) with no player above 9 m/s and the keeper kept at home. A figure only rises off a man the picture actually has on the ball; on the other 10% the count still ticks and nothing is credited to the wrong player. A goal is named only when the log and the picture agree on the scorer; otherwise it goes to the club. [The page's own scoreboard tally is held to the Python state block in Node](tests/test_live_tally.py).

**Call it.** Before each Form Line is revealed, the fan calls it: *Beaumont, ball speed tonight 16.16. Above or below his own level? The league sees nothing unusual.* Tap, or press ↑ / ↓. Then the answer, the gate's sentence and a running score. It turns the one question only his own season can answer into a game. The question shows the number tonight and nothing that gives the answer away, and [a test checks every question in every language against the gate](tests/test_audio_description.py).

**Accessibility.** An **Access** panel with audio description (off, key moments, or full radio-style commentary: the man on the ball, the long pass and its length, the ball won back, the shot, the goal and the score, the claim), in all five languages. Three ways to hear it: an **Azure AI Speech** neural voice, the browser's own voice, or the fan's own screen reader through a live region. Also captions synced to the speech, larger text, reduce motion, and the Call it switch, all usable from the keyboard. Sky launched live audio description for the Premier League on 19 Oct 2026, covering about 109 matches a season. Here it covers every match, from the same data. [Every number the describer could ever say is checked in Node](tests/test_audio_description.py) against the event row, the score and the clock, across the whole match in every language. Claims are spoken exactly as the gate passed them.

**Reach.** English, Spanish, French and Arabic (right-to-left), plus a plain-English register for someone who has never watched a match. Every claim in every language passes the same gate.

### The one thing nothing else here does

Every entry in this field verifies that its numbers are **true**. This one decides whether a sentence is **sayable**.

It measures between-player variance per metric and refuses a personal claim where there isn't any. Recovery time has an ICC of 0.006 — it measures how long a possession lasted, which is a property of the match rather than of whoever won the ball back — so *"fast for him"* is not a sentence this system will produce, about anyone, however it is asked. [Top speed is 0.577, so there it will.](#the-system-refuses-claims-it-cannot-support)

Gate precision **100%**, claim integrity **100%**, refusal correctness **100%** across 373 claims and three seeds. The gate is deterministic, so that is measured rather than scored by another model — and [the two things it cannot catch are published as a measured zero](#evidence).

### Why this is an enterprise solution

> *Category: **Best Enterprise Solution** — "strongest readiness for enterprise deployment and long-term business impact... balancing innovation with the reliability, transparency, and controls required for use in production environments."*

**The controls.** In sport the figures are expected to be right, and a receipt proving 13.77 equals 13.77 impresses nobody. A broadcaster's risk is not that a number is wrong. It is that a claim goes to air which the data cannot support, in front of a rights-holder, a regulator and the player's club. The gate is deterministic, so the same inputs give the same verdict every time and it can be **audited** rather than re-sampled. So the receipt is not about the number; it is about the sentence built on it. The console's **Why** panel is ordered by what is actually in dispute: his own reference class first, then the verdict, then whether this metric is entitled to carry a personal claim at all — ICC 0.112 for pass range, 0.006 for recovery time — then the league's view, and only then the measurement, which nobody was questioning. It lives in the data layer, as KQL alongside the events it governs, not in a prompt that can be edited away. And its limits are published as measured numbers rather than described: the two corruption classes it cannot catch are `xfail` tests scoring a hard zero, which is the form an audit can actually read.

**The claim is enforced, not asserted.** `python -m gegenpress eval` exits non-zero if gate precision, claim integrity or refusal correctness falls below 100%, and [it runs on every push](.github/workflows/ci.yml) — alongside the 159 tests and a live start of the MCP server over stdio. The three figures above are not a number somebody typed into a README once. If they ever stop being true, the build goes red. That is the difference between a metric and a control, and it is the whole of what an enterprise is buying here.

**Language is a residency property, not a feature.** The console ships in four languages and a plain-English register, and switching is a re-render rather than a request: every translated claim is already in the feed, already checked by the same gate. Nothing is sent to a translation service, so a claim never leaves the region that computed it. And because the gate reads digits rather than prose, one control covers every locale — a model-based fact-checker needs retraining, re-thresholding and re-evaluating per language, which is why most ship one. [Pinned by 14 tests](tests/test_i18n.py), including that the figures on screen are identical in all five.

**The adoption path.** Match state sits behind one interface with two implementations — `LocalStore` in Python and `AdxStore` in KQL — held to the same answers by a parity test. That is what makes this deployable rather than demoable: the KQL is plain Kusto and runs unchanged on a Fabric Eventhouse, so adopting it is a connection string rather than a rewrite, and the parity test is the evidence that the move does not change a single verdict. The gate is exposed over MCP, so studio graphics, auto-recaps and a commentary assistant inherit one control instead of each re-implementing a different one. Being deterministic, it adds no per-call model cost and no nondeterminism to the audit trail.

**It fails the way production needs it to, and you can watch it.** Three dependencies can die and all three have somewhere to go: Azure Data Explorer falls over to the local store *per call* rather than only at startup, so a cluster that answers at kickoff and times out at 60' no longer takes the broadcast with it; Foundry falls back to deterministic templates; and a sentence carrying a number nobody measured is rejected by the gate and replaced. `python -m gegenpress chaos` breaks each one in turn against a healthy baseline and prints what reached the viewer:

```
broken            degrades to                        claims  same numbers  failovers
none (baseline)   —                                       6           yes          0
adx               local store                             6           yes          2
foundry           deterministic templates                 6           yes          0
model             gate rejects, template replaces         6           yes          0
```

The wording degrades. **The numbers do not move.** That property is only available because every stage is deterministic — there is a correct answer to fall back *to* — and it is [pinned by 10 tests](tests/test_resilience.py), including one that checks the injected outage actually fired, so the suite cannot pass by breaking nothing.

**It ships as a container.** [`Dockerfile`](Dockerfile) builds the pipeline, the gate and the MCP server on `python:3.12-slim` with no compiled dependencies and no native extensions, running as a non-root user, with the gate's own evaluation as the `HEALTHCHECK` — a container whose gate has stopped refusing unsupportable claims is not healthy, whatever its process table says. CI builds the image on a clean runner every push and runs the gate and the chaos matrix *inside it*, so this is something that happened rather than something claimed.

**It knows which rules it is under.** A broadcaster deploying this answers to the EU AI Act's transparency duties (in force since 2 Aug 2026), GDPR (player performance data is personal data), ePrivacy and the European Accessibility Act. [`COMPLIANCE.md`](docs/COMPLIANCE.md) maps each one to the control in the code and the test that fails the build if it stops working. What that looks like in practice:

- **A model never puts words on air by itself.** A model-written sentence is a draft until a named producer approves it; the template airs in the meantime. Every claim on screen says who wrote it and who approved it.
- **Edits after the gate are detectable.** Every claim carries machine-readable provenance: who wrote it, its review status, and fingerprints of the brief and the text. `verify-feed` catches any change.
- **A player can get, and take, his data.** `export --player` gives everything held about him and everything said about him on air. One line in an objection list keeps him out of personal claims altogether.
- **No data about viewers.** The browser itself blocks any third-party request, through a Content-Security-Policy. No cookies; the only browser storage is the viewer's own settings.
- **Accessible, and audited.** 0 WCAG AA violations across six screen states, in a CI job that fails on any. The first run found 41.

It also lists what is *not* done, because those steps need a person, a contract or a subscription rather than code: the lawful-basis decision and DPIA sign-off, a data licence, deploying the Entra ID sign-in config and the retention policy, sessions with blind fans (the plan is written), and a signing key.

**What production would still need**, stated here rather than left for a judge to find: multi-tenancy, which does not exist — one deployment serves one league today. Authentication is narrower than it sounds: the data path already authenticates to Azure AD ([`adx.py`](src/gegenpress/adx.py) uses `az` CLI or device-code auth, and the Foundry adapter uses `DefaultAzureCredential`, so managed identity in Container Apps works unchanged), and the console is public and read-only on purpose — it is a demo, not a tenant. What is missing is per-user auth in front of a hosted console, which only exists once there is a console to host. And a paid ADX tier or an Eventhouse, because the free tier refuses `streamingingestion`, so events are queryable after a minute or two rather than instantly. The architecture is right for live play. The free tier is not.

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
PYTHONPATH=src python -m pytest -q              # 159 tests

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
| **Azure Data Explorer** | Event store; all match-state and grounding queries | **Verified on a live free cluster** — 153,041 events, every function green, **Python/KQL parity passing** |
| Azure AI Speech | Neural voices for audio description (en-GB, es-ES, fr-FR, ar-SA) | Called from the local server ([`speech.py`](src/gegenpress/speech.py), [`serve.py`](scripts/serve.py)), so **the key never reaches the browser**. SSML is escaped and lines are cached on disk, so a replayed match costs nothing against the 0.5M-character free tier. [Tested](tests/test_audio_description.py) against a mocked REST endpoint: URL, headers, voice per language and the cache. The live call needs a Speech key (`AZURE_SPEECH_KEY`, `AZURE_SPEECH_REGION`) and **has not been made**: no Azure subscription was available to this project. Without a key the page uses the browser voice, and in Microsoft Edge that is Microsoft's own neural voice ("Microsoft Ryan Online (Natural)"), which the console prefers when the browser offers it ([tested](tests/test_audio_description.py)). The panel names the voice that will speak |
| Microsoft Foundry | Model for the Desk agent, via the Agent Framework | Adapter written ([`agents.py`](src/gegenpress/agents.py)) and **tested against `agent-framework` 1.23.0** ([8 tests](tests/test_foundry_adapter.py)): imports resolve, both constructor call sites bind, selection and fallback behave, and the response stringifies to the sentence rather than a repr. The live call needs a provisioned resource; everything before it is pinned. Falls back to deterministic templates when unconfigured |

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

### The Form Line as a service (MCP)

```bash
pip install mcp
PYTHONPATH=src python -m gegenpress mcp     # stdio; plugs into Claude Desktop, VS Code, Copilot, Foundry agents
```

**Three MCP primitives, not one.** Eight tools over the same Store the console reads, so the numbers agree to the digit — plus two **resources** (`gegenpress://signal`, `gegenpress://match`), so the table of which claims are sayable is in front of a model before it writes a word rather than one tool call away, and a **prompt** (`commentary`) that is this project's thesis made portable: any model that loads it is bound to check the signal table first and run every sentence containing a figure through the Gate before saying it. [`docs/MCP.md`](docs/MCP.md) has the demo that lands it in forty seconds. Most are what you would expect — `form_line`, `top_moments`, `match_state`, `follow_targets`, `metric_signal_table` (the ICC gate as data). The one a stats feed does not have is **`verify_claim`**: hand it any sentence about a player's night and it runs the deterministic Gate against the measured brief — which numbers are unsupportable, what the allowed set was, and whether a personal claim is even *sayable* for that metric. The refusal semantics are in the service, not just the UI: ask for `form_line("...", "recovery time")` and you get the refusal and the reason, not a number.

```json
{"mcpServers": {"gegenpress": {"command": "python",
  "args": ["-m", "gegenpress", "mcp"],
  "env": {"PYTHONPATH": "src"}}}}
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

**Status: green, end to end, on a live cluster (24 Oct 2026)** — 153,041 events, 0 bootstrap failures, all functions compiling, and the two backends returning the same ranked moments: same events in the same order, values to the digit, `beats` within one rounding unit, and the ICC gate's allow/refuse decision identical on every one.

Getting there is the better evidence. The first live run found that `MetricSignal()`, the KQL half of the ICC gate, **had never compiled** — `between` is a KQL range operator — and that `Ground()`, failing with it, kept serving a *stale* definition from an earlier bootstrap while doctor reported it ok. The second run, against working KQL, found the two backends **ranking moments differently**: KQL scored rarity by counting which of 101 `percentiles_array()` cut points a value cleared — a T-Digest estimate so coarse that above 0.98 only three values were possible — so which moments the broadcast surfaced depended on which backend was running. A looser tolerance would have passed; instead KQL now computes the identical quantity (the exact share of the league strictly below the value, via a union, sort and `row_cumsum` — checked against Python's `bisect_left` on 3,415 live measurements before it was written, 0 mismatches), ties break on `event_id` on both sides, and the test's tolerance dropped from 0.02 to one rounding unit. Bootstrap failures now exit non-zero and the script refuses to test against a cluster doctor hasn't cleared. Not asserted, and said so in the test: the league median, which KQL estimates and Python computes exactly — a display value, not one that decides what surfaces.

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
  mcp_server.py  the Form Line as MCP tools; verify_claim is the Gate as a service
  calibrate.py   realism checks
kql/             schema and eleven KQL functions
docs/            the studio console (served by GitHub Pages)
```
