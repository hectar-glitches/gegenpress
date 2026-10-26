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
      already up, at **30:29** — not 30:01. The opener picks the twenty
      seconds of the claim's minute that carry the ball nearest a goal, so
      the play beat builds to the left box instead of circulating in
      midfield. That is the opening frame; it should need no clicks
- [ ] Click **Sound** and leave it on — the bed leans toward the box in
      play and a goal gets the full roar, which is worth ten seconds of
      narration. Set system output to the mic mix or record system audio
- [ ] Leave the speed at **1×**. The ball's flight-and-settle rhythm and
      the duels around it are tuned for real time and blur at 4×
- [ ] Close every notification source. A toast over the pitch is a retake

## The script

**Total 112s of runtime, of which about 100s is speech.** That is the real
constraint and it is tighter than it looks: narration you can follow runs
at 150 words per minute, so the whole video is **about 260 words**. The
previous draft of this script was 429 words — 172 seconds — and would have
needed 319 wpm in one section, which is faster than an auctioneer.

Each beat below carries its word budget. If you rewrite a line, recount it
— `wc -w` on the quoted text, and seconds ≈ words ÷ 2.5.

Times are cumulative. Director notes are in italics; the words in quotes
are the only words you say.

### 0:00–0:14 — the claim, and who it is for *(37 words)*

> *Open on the paused frame. Do not touch anything. Read the figures off
> the screen, not off this page — the feed is regenerated per seed.*

"A producer has seconds to decide what goes on screen. Broadcast says that
pass was long. Gegenpress says it was long **for him**. Kowalski tonight:
thirty-seventh percentile for the league, nearly four standard deviations
below his own season."

*Why this works: the differentiator and the user are both delivered before
the viewer has been asked to understand anything. No architecture, no tour.*

### 0:14–0:32 — it is a real match *(37 words)*

> *Press Play. Leave it at 1×. Say nothing for three seconds — let one
> pass travel and settle before you speak over it. Eleven seconds in,
> Kowalski himself plays a thirty-metre ball into the box and his tag
> comes up — the subject of the claim, in the match, on camera. His
> average tonight is 13.8; this one is the exception, which is what an
> average means. You can point at him or let it pass; do not explain it.
> The move ends with the ball in the goalmouth and the keeper on his line,
> right as this beat ends.*

"A simulated season — ten clubs, ninety matches, a hundred and fifty
thousand events. All twenty-two players: the two nearest the ball leave
their shape and go to it, so you get duels, not a formation sliding."

> *Hit `Wide` once, hold two seconds, hit it again. Do not narrate this.*

### 0:32–0:54 — the part that is actually hard *(55 words)*

> *Point at the* **Personal claims allowed — ICC ≥ 0.08** *card, bottom
> right. Do not click a moment: every moment in the rail is a metric the
> gate allows, because a refused metric has no personal norm to diverge
> from. The refusal lives in this card, and the card is the shot.*

"Not every number can carry a personal claim. Recovery time measures how
long a possession lasted — that is the match, not the player who won the
ball back. So we measure between-player variance. Top speed, 0.577:
personal claims allowed. Recovery time, 0.006: league only. That threshold
is Koo and Li's reliability boundary, not taste."

### 0:54–1:10 — the receipts *(38 words)*

> *Hit `Why`.*

"Every number recomputes from the events. The gate is deterministic, so it
is measured, not scored by another model. Three seeds, 373 claims:
precision, integrity, refusal correctness — all 100%. The two misses are
published as a measured zero."

### 1:10–1:32 — hand them the guardrail *(52 words)*

> *Hit `Try it`. The box opens pre-filled with the lie. Press Check and
> say nothing for a beat — let the strikethrough land before you speak.*

"Here is the part I would do myself. Type a claim about him. I have said
his range is 21.4 — his best of the season. Invented. The gate strikes it
out, says nobody measured it, and prints what it will say instead. Same
check an agent gets over MCP. Try it yourself."

*This is the beat they will repeat to each other. Everyone else asks a
judge to believe their guardrail works. This one lets them attack it and
fail, in their own browser, after the video has ended.*

### 1:32–1:52 — Azure, and close *(38 words)*

"Match state and grounding run as KQL on Azure Data Explorer — the gate
computed twice, parity-tested, which caught two real bugs. Broadcast
tells you a press was fast. Gegenpress tells you it was fast **for
him**."

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
