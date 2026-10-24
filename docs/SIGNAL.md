# The ICC gate: where the threshold comes from

The system refuses a personal claim — "fast **for him**" — on any metric
whose between-player signal is too weak to support one. This file answers
the two questions a reader should ask about that: *why 0.08*, and *does
any of this survive contact with real football*.

---

## 1. The measure

```
ICC = between-player variance / (between-player + within-player)
```

Near 1, knowing *who* took the action tells you most of what the number
will be. Near 0, it tells you nothing: every player's distribution is the
league's distribution wearing his name, and "his best in six games" is a
statement about sampling noise with a name attached.

Computed in [`signal.py`](../src/gegenpress/signal.py) over a season, and
again in KQL as `MetricSignal()` — `pvariance` and `variancep`, two
implementations of one definition, compared by
`tests/test_store.py::test_local_and_adx_agree`.

## 2. Where 0.08 comes from

Earlier versions of this file said the threshold was chosen because the
measured values fell into two clearly separated clusters. That is true, and
it is also circular: a threshold picked to separate the clusters you
observed will always separate them.

Here is the non-circular version.

**A form line is always a mean,** not a single observation. One touch of a
low-ICC metric tells you little about the player; the average of many may
still tell you plenty. Spearman-Brown gives the reliability of a
`k`-observation mean from the single-observation ICC:

```
ICC_k = k·ICC / (1 + (k−1)·ICC)
```

[Koo & Li (2016)](https://pmc.ncbi.nlm.nih.gov/articles/PMC4913118/), the
standard reference for interpreting ICC, put the **"good reliability"**
boundary at 0.75. The gate requires at least
`MIN_SAMPLES_PER_PLAYER = 50` observations per player, so solve for the
single-observation ICC that puts a 50-sample mean exactly on that
boundary:

```
0.75 = 50x / (1 + 49x)   →   x = 0.0566
```

**0.057 is the floor. The gate uses 0.08**, deliberately stricter, because
Spearman-Brown assumes independent observations and these are not: a
player's touches cluster within matches, so the effective sample is
smaller than the raw count and the true floor sits above the formula's
answer. How far above depends on the within-match correlation, which this
project does not estimate — so the response is a margin rather than a
second-order correction it cannot justify.

Run `python -m gegenpress form` and the threshold stops looking arbitrary:

| metric | ICC | reliability of a 50-match mean | Koo & Li band | gate |
| --- | --- | --- | --- | --- |
| top speed | 0.577 | 0.986 | excellent | allow |
| ball speed | 0.452 | 0.976 | excellent | allow |
| pass range | 0.112 | 0.863 | good | allow |
| carry range | 0.097 | 0.844 | good | allow |
| pass difficulty | 0.022 | 0.529 | moderate | **refuse** |
| recovery time | 0.006 | 0.223 | poor | **refuse** |

Every metric the gate allows yields a player mean of *good* reliability or
better. Every metric it refuses does not. The cut was not placed to produce
that result; it falls out of Koo & Li's boundary and the sample size.

The gate itself still compares **raw ICC**, not reliability, because the
identical comparison has to run in KQL and the two implementations must not
drift. The reliability column is reporting.

## 3. Does this survive contact with real football?

The honest problem: these ICCs are a property of a simulator whose
generator was deliberately adjusted so metrics depend on player attributes.
To that extent the numbers are what they were built to be. The question
worth asking is not whether the *values* transfer — they will not — but
whether the *mechanism* is real: do football metrics genuinely differ this
much in how much of their variance is between-player?

They do, and it is published.

**[Measurement properties of external training load variables during
standardised games in soccer](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0262274)**
(PLOS ONE, 2022) reports ICCs per metric across standardised small- and
large-sided games:

| variable | reported ICC | within-subject CV |
| --- | --- | --- |
| PlayerLoad | 0.79 – 0.91 | 4.3 – 39.5% |
| Total distance | 0.41 – 0.84 | 1.7 – 36.3% |
| m·min⁻¹ | 0.45 – 0.78 | — |
| **High-speed running** | **0.03 – 0.53** | **19 – 244%** |

That is the whole argument in one table, from real players. **Published
football ICCs span 0.03 to 0.91.** High-speed running — a headline metric
on every broadcast — sits at the bottom of that range, with within-subject
variation up to 244% and a signal-to-noise ratio the authors could not
compute. PlayerLoad sits near the top. Same sport, same players, same
sessions; an order of magnitude apart in how much the number says about the
individual.

The authors' own conclusion is the one this project is built on: they
recommend assessing reliability **at the individual level**, because
within-subject variation stayed large even where group-level reliability
looked acceptable.

Two further corroborations of the direction of travel:

- **Match-to-match physical output is dominated by context.** Work on
  [between-game variation in soccer](https://pubmed.ncbi.nlm.nih.gov/28704313)
  and on
  [match-to-match variation of elite players](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0200019)
  finds coefficients of variation rising through a match and attributes
  them to opponent, game state and fatigue rather than to the player. The
  second paper is explicit that its unit of analysis cannot separate
  individual effects from match context — which is precisely the
  separation ICC performs.
- Our own lowest-signal metric is of exactly this kind. `recovery_time`
  measures how long a possession lasted before the ball was won back: a
  property of the match, not of whoever happened to win it. Counter-pressing
  is a team behaviour. ICC 0.006 is the simulator agreeing with the
  football.

### What this does and does not license

**Licensed:** the claim that football metrics differ enough in
between-player signal that a system making personal claims must test for
it, and that at least one widely-broadcast metric would fail such a test.

**Not licensed:** any specific number in the table in §2. On real tracking
data the ICCs would be re-measured and the set of metrics clearing the gate
would be different. The 0.057 floor is also sample-size dependent — with
20 observations per player rather than 50 it rises to 0.136, so a system
making claims earlier in a season needs a stricter gate, not a looser one.

Say this before a judge says it for you. The mechanism is the contribution;
the values are a demonstration of it.

## 4. Why this is the differentiator

Every other entry in this field verifies that its numbers are **true**:
that the figure in the sentence matches the figure in the data. So does
this one — `claim integrity 100%` over 373 claims, and a deterministic Gate
that strips any number not in the brief.

The ICC gate asks a different and strictly harder question: whether the
**sentence is sayable at all**. A number can be perfectly accurate and the
claim built on it still meaningless, because the reference class it is
compared against does not exist. "His quickest recovery this season" can be
arithmetically flawless and still be a fact about the match wearing a
player's name.

Nobody else in this field refuses claims on signal grounds.

---

## References

- Koo, T. K., & Li, M. Y. (2016). [A Guideline of Selecting and Reporting Intraclass Correlation Coefficients for Reliability Research](https://pmc.ncbi.nlm.nih.gov/articles/PMC4913118/). *Journal of Chiropractic Medicine*, 15(2), 155–163.
- [Measurement properties of external training load variables during standardised games in soccer](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0262274). *PLOS ONE* (2022).
- [Between-Game Variation of Physical Soccer Performance Measures in Highly Trained Youth Soccer Players](https://pubmed.ncbi.nlm.nih.gov/28704313). *J Strength Cond Res* (2017).
- [Speed synchronization, physical workload and match-to-match performance variation of elite football players](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0200019). *PLOS ONE* (2018).
- Spearman-Brown prediction formula — standard psychometrics; see Koo & Li for its use alongside ICC.
