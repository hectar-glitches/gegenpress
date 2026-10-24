# The graphics package

This file exists because of a specific failure. Six independent entries in
this hackathon — and the first two versions of this console — converged on
the same interface without anyone copying anyone. That is what happens when
you reach for defaults: the defaults are shared, so the results are too.

Read this before changing anything visual.

---

## 1. The convergent default — do not reach for these

Observed across `the-dugout`, `itg-second-screen`, `playmakers`,
`insidethegame`, `matchpulse` and `beyond-the-scoreline`, and true of this
project until October 2026:

| Aspect | The default everyone hit |
| --- | --- |
| Typeface | `system-ui` / Inter / `-apple-system` |
| Type variation | Weight only — 400/600/700 |
| Micro labels | Uppercase, wide tracking (`.14em`), 9–10px, grey |
| Panels | `border-radius: 11–13px`, `1px solid rgba(...)`, `backdrop-filter: blur()`, long drop shadow |
| Buttons | Pills, uppercase, letterspaced, bordered, filled when active |
| Layout | Floating cards inset from the edges on a right-hand rail |
| Colour | Near-black slate `#0a0e14`, one amber accent `#ffb020` |
| Pitch | Flat green, ~10 wide mow bands, no lighting, no grain |
| Markers | Coloured circles with a shirt number |

**If a change would move the console toward any cell in that table, it is
the wrong change.** This is not a style preference. Every one of those is a
reasonable local decision; the problem is that it is the *same* reasonable
local decision everyone else made, so it carries no information about this
project.

## 2. What current broadcast practice actually does

Researched rather than assumed. Sources at the bottom.

- **Strip the decoration.** |drive| Studio's DiNapoli, on Fox's NFL bug:
  the job is *"letting the game breathe."* Gradients, dimensional
  treatments and ornament have been stripped out across the industry. Blur,
  borders and shadows are not neutral — they are a dated broadcast era
  *and* the current dashboard dialect at the same time.
- **Type carries the brand once decoration is gone.** Fox cut a custom face
  from their logo: *"even just in this minimal form, it was communicating
  our brand in the typography."* This is the largest available lever.
- **Numbers are the priority.** The Premier League commissioned **Premier
  Sans** from Monotype's Toshi Omagari specifically for TV and mobile —
  *"it was essential that numbers be different and distinct"* — with
  condensed cuts for long player names. This project is *about* numbers and
  was setting them in the OS default.
- **Protect the hierarchy at all costs.** Gary Hartley, Fox Sports: decide
  what is read first and second, then design. Motion follows hierarchy.
- **Small and precise beats large.** A smaller bug with exact type is more
  legible than a bigger one.
- **Motion is architecture.** Jacob LaPlante: the bug shrinks, slides and
  reconfigures to make room, then returns to its base state.
- **Avoid the obvious escape hatch.** Oswald is the reflex "sports font"
  and is *"heavily overused in sports and news, so it may not make a brand
  stand out."* Swapping Inter for Oswald is the same mistake in a tracksuit.

## 3. The system

### Typeface — Archivo, and the width axis is the point

`Archivo Variable`, Héctor Gatti / Omnibus Type, SIL OFL, self-hosted in
[`fonts/`](fonts/) so a demo never depends on a font CDN being up.

One family carries everything, because it has a **width axis (62–125%)** as
well as weight (100–900). Everyone else varies weight alone, which is
exactly why everyone else looks alike. Here, width does the work:

| Role | `wght` | `wdth` | Used for |
| --- | --- | --- | --- |
| `.fig` | 800 | **118** | Every number: Form Line, score, tonight/norm, clock |
| `.name` | 650 | **80** | Player names |
| `.meta` | 450 | 88 | Club, minute, metric |
| `.micro` | 700 | **74** | Section and field labels |
| body | 400 | 100 | The claim sentence |

Figures are **expanded**, names and labels are **narrow**. Tabular figures
(`font-feature-settings: 'tnum'`) on anything numeric so digits do not
jitter as the clock runs.

Micro labels stay uppercase — that is genuinely broadcast — but at `wdth
74` and `.075em`, which is narrow-and-tight rather than the default
wide-and-loose.

### Colour — Premier League purple family

The chrome reads as near-black but is unmistakably warm. The league's own
signal colours carry meaning, and **nothing else on screen is allowed to be
coloured.**

| Token | Hex | Role |
| --- | --- | --- |
| `--ink0` | `#0B0010` | Page, behind everything |
| `--ink1` | `#1C0423` | Chrome base — all panels |
| `--ink2` | `#2A0733` | Raised surface — hero block, card headers |
| `--ink3` | `#3A0F46` | Active row |
| `--rule` | `#471A54` | Every hairline. The only border style. |
| `--pl` | `#37003C` | Ink on filled accents |
| `--up` | `#00FF85` | Above his own level. Active state. |
| `--down` | `#E90052` | Below his own level. Live dot. |
| `--data` | `#04F5FF` | Neutral measured values |
| `--soft` | `#C9B4D3` | Secondary text |
| `--dim` | `#8A6E97` | Labels, unfired rows |

Sources disagree on the league's exact purple (`#37003C`, `#3D195B`,
`#360D3A` all appear); this is a sympathetic palette, not a reproduction.
**No PL lion, wordmark, crest or club badge is used anywhere** — all clubs
and players here are synthetic.

Team colours (`--home #5aa9ff`, `--away #ecA322`) exist only on the pitch.
Because amber appears nowhere in the chrome any more, amber on screen
always means one thing: the away side.

### Shape — hard edges, flush, opaque

- `border-radius: 0` everywhere. No exceptions.
- No `backdrop-filter`. No `box-shadow`. No translucent 1px borders.
- Panels are **opaque planes flush to a screen edge**, not cards floating
  inset. Scorebug to the top-left corner; rail to the right edge, full
  height; lower third full-bleed along the bottom.
- Division is by **solid hairline** in `--rule`, never by gap or shadow.
- Buttons are flat labels separated by hairlines. Active state is a solid
  `--up` fill with `--pl` ink — no border, no radius.
- The on-pitch name tag follows the same language: hard-edged, opaque, with
  a kit-coloured leading rule.

### Hierarchy

The Form Line is the one thing this project exists to say, so it is read
first and sized for it: its own `--ink2` block at the head of the strap, 38px
expanded figures, coloured by direction, with the verdict beneath it.

The old layout put it **last**, in the least-read corner, at the same weight
as two statistics any competitor also shows.

Order on the strap: `band → FORM LINE → name + claim → tonight → league →
his norm`.

### The pitch

Realism is the one place to spend effort without worrying about
distinctiveness — nobody else is drawing people at all. See the camera
section in the [README](../README.md).

- Turf is cooled and slightly desaturated from broadcast green, because the
  chrome around it is aubergine and saturated green fights purple.
- **16** mow bands, not 10. Wide bands read as a graphic device; narrow ones
  read as cut grass.
- Three floodlight pools, clipped to the turf. Real grass is never evenly
  lit.
- The stand beyond the far touchline is tinted toward the chrome's
  aubergine with faint tiers. Flat black above the grass reads as a crop.
- Film grain over the **whole frame**, last. Grain is a property of the
  camera, not the pitch, so it belongs in screen space — and it is most of
  what separates "photographed" from "drawn".

### Responsive

The frame always fills: focal length is clamped so the pitch never floats
in a band of black and the far touchline never leaves frame. On a narrow
window this shows *less pitch* rather than a smaller pitch, which is what a
camera operator would do.

The strap sheds supporting figures as width drops — league at 1180px, all
of them at 960px. The claim and the Form Line are what must survive.

## 4. Before committing a visual change

1. Does it add a radius, a blur, a shadow, or a translucent border? → No.
2. Does it vary weight where it should vary width? → Use the width axis.
3. Does it introduce a colour outside the table above? → No.
4. Does it put anything above the Form Line in reading order? → No.
5. Does it float a panel inset from an edge? → Flush it.
6. Screenshot it at 1440 and 1032 wide and **look at it.** Every real fault
   in this console — pedestal shadows, frozen splay strides, mirrored shirt
   numbers, the collapsing strap — was found by looking, not by reasoning
   about the code.

---

## Sources

- [Designing the Modern Scorebug — SVG](https://www.sportsvideo.org/2026/06/09/designing-the-modern-scorebug-how-broadcast-graphics-teams-are-rethinking-the-most-important-element-on-screen/)
- [Premier League: a brand identity that works hard, plays hard — Monotype](https://www.monotype.com/resources/case-studies/premier-league)
- [Game changers: the designers innovating graphics for sports — It's Nice That](https://www.itsnicethat.com/features/forward-thinking-sports-graphic-design-080124)
- [DixonBaxi, Premier League "Field of Play" — It's Nice That](https://www.itsnicethat.com/news/dixonbaxi-premier-league-field-of-play-120816)
- [Premier League design refresh by Nomad — Creative Review](https://www.creativereview.co.uk/premier-league-branding-nomad/)
- [Oswald Font Guide — FontFYI](https://fontfyi.com/blog/oswald-font-guide/)
- [Best Free Fonts for Sports & Athletics — FontAlternatives](https://fontalternatives.com/best-fonts-for/sports/)
- [Archivo — Wikipedia](https://en.wikipedia.org/wiki/Archivo)
- [Premier League brand colours — ColorFYI](https://colorfyi.com/brands/premier-league/)
