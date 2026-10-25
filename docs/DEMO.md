# The two-minute video

Mandatory for submission: under 2 minutes, public YouTube or Vimeo URL.

The judges will watch a lot of these back to back, and most of them will
open at 0–0 with an empty insight panel and spend their first twenty
seconds explaining an architecture diagram. The whole plan here is to say
the one thing nobody else can say, in the first ten seconds, over a picture
that looks like television.

## Before recording

- [ ] `python3 scripts/serve.py` — serves `docs/` with caching off, so a
      reload is always the current build. Do **not** film the GitHub Pages
      copy: a deploy lag mid-record is unrecoverable
- [ ] Only rebuild the feed if you changed Python
      (`PYTHONPATH=src python -m gegenpress feed`) — and if you do, re-read
      the numbers below off the screen, because they will move
- [ ] Browser at **1440×900**, zoom 100%, full screen, no bookmarks bar
- [ ] Hard-reload once, open the console and run
      `document.fonts.check('700 16px Archivo')` — it must print `true`.
      Do not eyeball this: Archivo at `wdth 125` measures *narrower* than
      some system fallbacks, so "the figures look wide" is not a test
- [ ] Confirm it opens **paused on a diverging Form Line** with the strap
      already up. That is the opening frame; it should need no clicks
- [ ] Click **Sound** and leave it on — the bed leans toward the box in
      play and a goal gets the full roar, which is worth ten seconds of
      narration. Set system output to the mic mix or record system audio
- [ ] Leave the speed at **1×**. The ball's flight-and-settle rhythm and
      the duels around it are tuned for real time and blur at 4×
- [ ] Close every notification source. A toast over the pitch is a retake

## The script

Total 115s, leaving margin. Times are cumulative.

### 0:00–0:12 — the claim, before anything else

> *Open on the paused frame. Do not touch anything.*

> *Verified against the current feed — but read the screen, not this page.*

"Broadcast tells you a pass was long. This tells you it was long **for
him**. Noor Kowalski's range tonight is 13.8 — that's thirty-seventh
percentile, utterly ordinary for the league. Against his own season it's
nearly four standard deviations down. He's having a bad night and the
league table can't see it."

*Why this works: the differentiator is spoken and on screen before the
viewer has been asked to understand anything. No architecture, no tour.*

### 0:12–0:35 — it's a real match, not a mock-up

> *Press Play. Leave it at 1×. Say nothing for three seconds — let a
> pass travel and settle before you speak over it.*

"Everything here is a simulated season — ten clubs, a persistent squad,
ninety matches, a hundred and fifty thousand events. The camera is a main
camera forty-two metres back and twenty-eight up, tracking the ball. Those
are all twenty-two players, positioned by a model — the two nearest the
ball leave their shape and go to it, which is why there are duels rather
than a formation sliding about."

> *Hit `Wide` once, hold two seconds, hit it again.*

### 0:35–1:00 — the part that is actually hard

> *Point at the* **Personal claims allowed — ICC ≥ 0.08** *card, bottom
> right. Do not click a moment: every moment in the rail is a metric the
> gate allows, because a refused metric has no personal norm to diverge
> from. The refusal lives in this card, and the card is the shot.*

"Here's the bit I care about. Not every number can carry a personal claim.
Recovery time measures how long a possession lasted — that's a property of
the match, not of whoever won the ball back. So the system measures
between-player variance, and where there isn't any, it **refuses** to make
the claim."

> *Read down the column. The numbers are on screen — read them, don't
> recite these.*

"That's intraclass correlation, per metric, measured off the season. Top
speed, 0.577 — a player's own history means something, so personal claims
are allowed. Recovery time, 0.006 — that's league only, and the system will
not say 'fast for him' about it no matter who asks. The threshold isn't
taste: 0.08 is the value that puts a fifty-match mean on Koo and Li's
reliability boundary. Every entry in this field verifies its numbers are
true. This one checks whether the sentence is **sayable**."

### 1:00–1:25 — the receipts

> *Hit `Why`.*

"Measured, league, his season, verdict, gate. Every number on screen
recomputes from the events — and the gate is deterministic, so it's
measured deterministically rather than scored by another model. Three
hundred and seventy-three claims, three seeds: gate precision 100%, claim
integrity 100%, refusal correctness 100%."

"Two things it can't catch, both published as a measured zero: a number
spelled out in words, and a real number attached to the wrong thing. Those
are `xfail` tests, so fixing one gets noticed."

### 1:25–1:50 — where Azure actually is

"Match state and grounding both run as KQL on Azure Data Explorer — eleven
functions, including the ICC gate computed again in Kusto. Two
implementations of one interface, and a parity test that holds them to the
same answers. It caught two real bugs before it passed: a function that had
never compiled, and the two backends ranking moments differently. It's
green now. And the whole thing is callable over MCP — including a tool that
checks a sentence before a model says it."

### 1:50–1:55 — close

"Football's broadcast tells you a press was fast. Gegenpress tells you it
was fast for him."

## Rules for the recording

- **Never say "as you can see".** Say the number.
- **Do not tour the UI.** No "and over here on the right we have…". The
  rail gets pointed at once, for the ICC table, because that is evidence.
- **Do not apologise** for synthetic data. It is in the brief. Say
  "simulated season" once, in a confident tone, and move on.
- **Let the pitch play under the voice.** Dead air over motion is fine;
  a static screen under narration is not.
- **One take per section**, cut together. Do not attempt 115 seconds live.
- If a number on screen differs from the script, **read the screen**. The
  feed is regenerated per seed and the script was written from one run.

## After

- [ ] Watch it once at 1.5× with the sound off. If the first frame doesn't
      carry a player name and a Form Line, recut the opening
- [ ] Upload **public** (not unlisted, unless the rules permit unlisted —
      check the entry form wording)
- [ ] Paste the URL into the entry form, with the repo link
- [ ] Confirm the Pages site loads from a browser you have never opened it
      in — a cached asset can hide a 404 for the font or the feed
