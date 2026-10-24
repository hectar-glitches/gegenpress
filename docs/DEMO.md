# The two-minute video

Mandatory for submission: under 2 minutes, public YouTube or Vimeo URL.

The judges will watch a lot of these back to back, and most of them will
open at 0–0 with an empty insight panel and spend their first twenty
seconds explaining an architecture diagram. The whole plan here is to say
the one thing nobody else can say, in the first ten seconds, over a picture
that looks like television.

## Before recording

- [ ] `PYTHONPATH=src python -m gegenpress feed` — rebuild `docs/feed.json`
- [ ] `python -m http.server -d docs 8000` — serve locally; do **not** film
      the GitHub Pages copy, a deploy lag mid-record is unrecoverable
- [ ] Browser at **1440×900**, zoom 100%, full screen, no bookmarks bar
- [ ] Hard-reload once and confirm the type is Archivo, not a fallback —
      the figures should be visibly wide. If they are not, the font 404'd
- [ ] Confirm it opens **paused on a diverging Form Line** with the strap
      already up. That is the opening frame; it should need no clicks
- [ ] Click **Sound** and leave it on — the crowd is synthesized and
      reacts to play, and the roar under a goal is worth ten seconds of
      narration. Set system output to the mic mix or record system audio
- [ ] Close every notification source. A toast over the pitch is a retake

## The script

Total 115s, leaving margin. Times are cumulative.

### 0:00–0:12 — the claim, before anything else

> *Open on the paused frame. Do not touch anything.*

"Broadcast tells you a pass was long. This tells you it was long **for
him**. Kwame Ferreira's range tonight is 14.0 — that's forty-second
percentile, utterly ordinary for the league. Against his own season it's
three and a half standard deviations down. He's having a bad night and the
league table can't see it."

*Why this works: the differentiator is spoken and on screen before the
viewer has been asked to understand anything. No architecture, no tour.*

### 0:12–0:35 — it's a real match, not a mock-up

> *Press Play. Let it run at 4×. Say nothing for three seconds.*

"Everything here is a simulated season — twenty clubs, a persistent squad,
a hundred and sixty matches, a hundred and fifty thousand events. The
camera is a main camera forty-two metres back and twenty-eight up, tracking
the ball. Those are all twenty-two players, positioned by a model, not
sprites on a loop."

> *Hit `Wide` once, hold two seconds, hit it again.*

### 0:35–1:00 — the part that is actually hard

> *Click the moment in the rail whose metric is* recovery time *or*
> *pass difficulty — one the gate refuses.*

"Here's the bit I care about. Not every number can carry a personal claim.
Recovery time measures how long a possession lasted — that's a property of
the match, not of whoever won the ball back. So the system measures
between-player variance, and where there isn't any, it **refuses** to make
the claim."

> *Point at the Personal claims allowed card.*

"Intraclass correlation per metric. Above 0.08 a player's own history means
something, below it his distribution is just the league's wearing his name.
Top speed, 0.58 — personal claims allowed. Recovery time, 0.006 — league
only. Every entry in this field verifies its numbers are true. This one
checks whether the sentence is **sayable**."

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

"Match state and grounding both run as KQL on Azure Data Explorer —
eleven functions, including the ICC gate computed again in Kusto. There are
two implementations of one interface, Python and KQL, and the agents don't
know which is behind it. The same KQL runs unchanged on a Fabric
Eventhouse."

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
