"""Gegenpress CLI.

    python -m gegenpress season --matches 90 --out data/
    python -m gegenpress demo
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

from .baselines import METRICS, build_baselines, ground, rarity
from .calibrate import report, run_checks
from .season import build_league
from .simulate import simulate_match, simulate_season


def cmd_season(args: argparse.Namespace) -> int:
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    league = build_league(seed=args.seed)
    fixtures = league.fixtures[: args.matches] if args.matches else league.fixtures
    print(f"league: {len(league.clubs)} clubs, {len(league.players)} players, {len(fixtures)} fixtures")

    matches = []
    events_path = out / "events.jsonl"
    with events_path.open("w") as fh:
        for i, fixture in enumerate(fixtures, 1):
            match = simulate_match(league, fixture, seed=args.seed)
            matches.append(match)
            for event in match.events:
                fh.write(json.dumps(event.as_row()) + "\n")
            if i % 10 == 0 or i == len(fixtures):
                print(f"  {i}/{len(fixtures)} matches", end="\r", flush=True)
    print()

    total_events = sum(len(m.events) for m in matches)
    total_goals = sum(m.home_goals + m.away_goals for m in matches)

    squads = {
        p.player_id: {"name": p.name, "club_id": p.club_id, "position": p.position,
                      "shirt": p.shirt, "attributes": p.attributes.as_dict()}
        for p in league.players
    }
    (out / "players.json").write_text(json.dumps(squads, indent=2))
    (out / "clubs.json").write_text(
        json.dumps([{"club_id": c.club_id, "name": c.name, "short_name": c.short_name,
                     "style": round(c.style, 3)} for c in league.clubs], indent=2)
    )

    baselines = build_baselines(matches)
    summary = {
        metric: {
            "n": d.n,
            "median": round(d.median, 3),
            "mean": round(d.mean, 3),
            "direction": METRICS[metric][2],
        }
        for metric, d in baselines.population.items()
    }
    (out / "baselines.json").write_text(json.dumps(summary, indent=2))

    elapsed = time.time() - t0
    print(f"\n{len(matches)} matches, {total_events:,} events, {total_goals} goals "
          f"({total_goals / len(matches):.2f}/match) in {elapsed:.1f}s")
    print(f"written to {out.resolve()}/")
    print("\npopulation baselines")
    for metric, s in summary.items():
        print(f"  {metric:<20} n={s['n']:>7,}  median={s['median']:>8.2f}  ({s['direction']})")
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    """Simulate a season, then narrate the standout moments of one live match."""
    league = build_league(seed=args.seed)
    print(f"simulating {len(league.fixtures)} match season ...")
    t0 = time.time()
    season = simulate_season(league, seed=args.seed)
    baselines = build_baselines(season)
    print(f"done in {time.time() - t0:.1f}s "
          f"({sum(len(m.events) for m in season):,} events)\n")

    # The "live" match is a fresh fixture the baselines have not seen.
    live = simulate_match(league, league.fixtures[0], seed=args.seed + 1)
    home = league.club(live.home_club_id).name
    away = league.club(live.away_club_id).name
    print(f"LIVE  {home} {live.home_goals} - {live.away_goals} {away}")
    print(f"      {len(live.events):,} events\n")

    moments = []
    for e in live.events:
        for metric, (etype, key, _d) in METRICS.items():
            if e.type != etype:
                continue
            value = e.detail.get(key)
            if value is None:
                continue
            score = rarity(baselines, metric, float(value))
            moments.append((score, e, metric, float(value)))

    moments.sort(key=lambda m: -m[0])
    print("top moments by rarity against the season\n")
    for score, e, metric, value in moments[: args.top]:
        player = league.player(e.player_id)
        g = ground(baselines, metric, e.player_id, value)
        marker = "*" if g.is_personal_best else " "
        print(f"{marker} {e.minute:>3}'  {metric:<18} {g.headline(player.name)}")
        print(f"       beats {score * 100:.1f}% of the league "
              f"(n={g.population_n:,}) | his own n={g.personal_n}")
    print("\n* = personal season best")
    return 0


def cmd_calibrate(args: argparse.Namespace) -> int:
    league = build_league(seed=args.seed)
    season = simulate_season(league, seed=args.seed)
    checks = run_checks(season)
    print(f"seed={args.seed}  {len(season)} matches\n")
    print(report(checks))
    return 0 if all(c.passed for c in checks) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gegenpress")
    sub = parser.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("season", help="simulate a season and write events + baselines")
    s.add_argument("--matches", type=int, default=0, help="0 = full season")
    s.add_argument("--seed", type=int, default=2026)
    s.add_argument("--out", default="data")
    s.set_defaults(func=cmd_season)

    d = sub.add_parser("demo", help="season + one live match, narrated")
    d.add_argument("--seed", type=int, default=2026)
    d.add_argument("--top", type=int, default=8)
    d.set_defaults(func=cmd_demo)

    c = sub.add_parser("calibrate", help="check the season against football-realistic targets")
    c.add_argument("--seed", type=int, default=2026)
    c.set_defaults(func=cmd_calibrate)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
