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
from .agents import get_model, run_desk
from .evaluate import report as eval_report
from .evaluate import run as eval_run
from .feed import build_feed, write_feed
from .signal import measure_signal, report as signal_report
from .store import LocalStore, get_store
from .season import build_league
from .simulate import simulate_live, simulate_match, simulate_season


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
    live = simulate_live(league, league.fixtures[0], seed=args.seed)
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


def cmd_state(args: argparse.Namespace) -> int:
    """Season -> store -> live match, through the Store interface."""
    league = build_league(seed=args.seed)
    season = simulate_season(league, seed=args.seed)
    store = get_store(prefer_adx=args.adx)
    store.load_season(league, season)
    print(f"store: {type(store).__name__}\n")

    live = simulate_live(league, league.fixtures[0], seed=args.seed)
    home, away = league.club(live.home_club_id), league.club(live.away_club_id)
    print(f"LIVE  {home.name} {live.home_goals} - {live.away_goals} {away.name}\n")

    print(f"match state, last {args.window} minutes to {args.minute}'")
    for team_id, s in store.match_state(live, args.minute, args.window).items():
        club = league.club(team_id)
        print(f"  {club.short_name}  acc {s['pass_accuracy']:.0%}  "
              f"xg {s['xg']:.2f}  tilt {s['field_tilt']:.0%}  "
              f"recov {s['recoveries']} (hi {s['high_recoveries']})  "
              f"gegenpress {s['gegenpress_idx']}")

    print("\nfollow target, ranked by lift over their own season norm")
    for player_id, score in store.follow_target(live, args.minute)[:5]:
        p = league.player(player_id)
        print(f"  {score:>7.3f}  {p.name:<24} {p.position}  {league.club(p.club_id).short_name}")
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    """Create the ADX schema and load a season into it."""
    try:
        from .adx import AdxStore
        store = AdxStore.from_env()
    except ImportError:
        print("the Azure SDK is not installed. run:\n"
              "  pip install azure-kusto-data azure-kusto-ingest azure-identity")
        return 2
    except RuntimeError as exc:
        print(f"{exc}\n\nset it to your cluster URI, for example:\n"
              "  export ADX_CLUSTER=https://gegenpress.westeurope.kusto.windows.net\n"
              "  export ADX_DATABASE=gegenpress\n\n"
              "a free cluster (no subscription, no card) takes a few minutes:\n"
              "  https://aka.ms/kustofree")
        return 2
    print(f"cluster: {store.cluster}\ndatabase: {store.database}\n")
    if args.bootstrap:
        if store.bootstrap() and not args.load:
            print("\nSome commands failed. Fix those before loading data.")
            return 1
    if args.reset:
        store.reset()
    if args.load:
        league = build_league(seed=args.seed)
        season = simulate_season(league, seed=args.seed)
        live = simulate_live(league, league.fixtures[0], seed=args.seed)
        # The live match goes in too, under its own id, or there is
        # nothing for the query path to read.
        store.ingest_season(league, season + [live])
        print(f"[adx] live match id: {live.match_id}")
    if not (args.bootstrap or args.load or args.reset):
        print("nothing to do: pass --bootstrap and/or --load")
    return 0


def cmd_mcp(args: argparse.Namespace) -> int:
    """Serve the Form Line to any model that speaks MCP."""
    try:
        from .mcp_server import serve
    except ImportError:
        print("the MCP SDK is not installed. run:\n  pip install mcp")
        return 2
    return serve()


def cmd_form(args: argparse.Namespace) -> int:
    """The differentiator, on one screen."""
    league = build_league(seed=args.seed)
    season = simulate_season(league, seed=args.seed)
    store = LocalStore()
    store.load_season(league, season)

    print("which metrics can carry a personal claim\n")
    print(signal_report(measure_signal(season)))

    live = simulate_live(league, league.fixtures[0], seed=args.seed)
    home, away = league.club(live.home_club_id), league.club(live.away_club_id)
    print(f"\n\nLIVE  {home.name} {live.home_goals} - {live.away_goals} {away.name}\n")
    print("form lines: this match against the player's own season\n")
    for f in store.form_lines(live):
        mark = "*" if f.diverges else " "
        print(f" {mark} {f.claim()}")
        print(f"     league percentile {f.league_percentile:.0%}  "
              f"effect {f.effect_vs_league_sd:.2f} SD of league spread")
    print("\n* = strong for him, ordinary league-wide \u2014 the case a league")
    print("    percentile alone cannot tell you about.")
    return 0


def cmd_desk(args: argparse.Namespace) -> int:
    """Scout -> Why -> Desk -> Gate over one match."""
    league = build_league(seed=args.seed)
    season = simulate_season(league, seed=args.seed)
    store = LocalStore()
    store.load_season(league, season)
    live = simulate_live(league, league.fixtures[0], seed=args.seed)

    model = get_model(prefer_foundry=args.foundry or None)
    print(f"model: {model.name}\n")
    home, away = league.club(live.home_club_id), league.club(live.away_club_id)
    print(f"LIVE  {home.name} {live.home_goals} - {live.away_goals} {away.name}\n")

    segments = run_desk(store, league, live, model=model, limit=args.limit)
    grounded = sum(1 for s in segments if s.verdict.passed)
    for seg in segments:
        mark = "*" if seg.brief.diverges else " "
        state = "" if seg.verdict.passed else "  [fell back to template]"
        print(f" {mark} {seg.verdict.text}{state}")
    print(f"\n{grounded}/{len(segments)} passed the gate without falling back")
    print("* = strong for him, ordinary league-wide")
    return 0


def cmd_feed(args: argparse.Namespace) -> int:
    """Build the broadcast feed the console and overlay render."""
    import pathlib

    league = build_league(seed=args.seed)
    season = simulate_season(league, seed=args.seed)
    store = LocalStore()
    store.load_season(league, season)
    live = simulate_live(league, league.fixtures[0], seed=args.seed)

    model = get_model(prefer_foundry=args.foundry or None)
    feed = build_feed(store, league, live, season, model=model,
                      limit=args.limit, span=args.span)

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    write_feed(str(out), feed)

    m = feed["match"]
    print(f"model: {model.name}")
    print(f"{m['home']['name']} {m['home']['goals']} - "
          f"{m['away']['goals']} {m['away']['name']}")
    w = feed["window"]
    print(f"{len(feed['moments'])} moments, "
          f"{sum(1 for x in feed['moments'] if x['diverges'])} diverging")
    print(f"{feed['frames']['n']} position frames at {feed['frames']['dt']}s, "
          f"{len(feed['stream'])} events")
    print(f"showcase window around {w['centre_minute']}'")
    print(f"written to {out}")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    """Check what actually landed in the cluster."""
    try:
        from .adx import AdxStore
        store = AdxStore.from_env()
    except Exception as exc:
        print(f"{exc}")
        return 2
    league = build_league(seed=args.seed)
    live = simulate_live(league, league.fixtures[0], seed=args.seed)
    return 0 if store.doctor(live.match_id) == 0 else 1


def cmd_eval(args: argparse.Namespace) -> int:
    """Measure the Gate, claim integrity and refusal correctness."""
    seeds = tuple(int(s) for s in args.seeds.split(","))
    print(f"seeds {seeds}, {args.matches} matches each\n")
    r = eval_run(seeds=seeds, matches_per_seed=args.matches)
    print(eval_report(r))
    ok = (r.precision == 1.0 and r.integrity_failed == 0
          and r.refusals_violated == 0)
    return 0 if ok else 1


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

    st = sub.add_parser("state", help="rolling match state and follow targets")
    st.add_argument("--seed", type=int, default=2026)
    st.add_argument("--minute", type=int, default=75)
    st.add_argument("--window", type=int, default=15)
    st.add_argument("--adx", action="store_true", help="force the ADX backend")
    st.set_defaults(func=cmd_state)

    ing = sub.add_parser("ingest", help="create ADX schema and load a season")
    ing.add_argument("--bootstrap", action="store_true", help="create tables and functions")
    ing.add_argument("--load", action="store_true", help="simulate and ingest a season")
    ing.add_argument("--reset", action="store_true",
                     help="clear table data first (use when re-loading)")
    ing.add_argument("--seed", type=int, default=2026)
    ing.set_defaults(func=cmd_ingest)

    fm = sub.add_parser("form", help="signal report + form lines for one match")
    fm.add_argument("--seed", type=int, default=2026)
    fm.set_defaults(func=cmd_form)

    mc = sub.add_parser("mcp", help="serve the Form Line as MCP tools over stdio")
    mc.set_defaults(func=cmd_mcp)

    dk = sub.add_parser("desk", help="run the agent layer over one match")
    dk.add_argument("--seed", type=int, default=2026)
    dk.add_argument("--limit", type=int, default=6)
    dk.add_argument("--foundry", action="store_true", help="force the Foundry model")
    dk.set_defaults(func=cmd_desk)

    fd = sub.add_parser("feed", help="build the broadcast feed JSON")
    fd.add_argument("--seed", type=int, default=2026)
    fd.add_argument("--limit", type=int, default=8)
    fd.add_argument("--out", default="docs/feed.json")
    fd.add_argument("--span", type=int, default=240,
                    help="showcase window length in match seconds")
    fd.add_argument("--foundry", action="store_true")
    fd.set_defaults(func=cmd_feed)

    doc = sub.add_parser("doctor", help="check the ADX cluster's data and functions")
    doc.add_argument("--seed", type=int, default=2026)
    doc.set_defaults(func=cmd_doctor)

    ev = sub.add_parser("eval", help="gate, integrity and refusal evaluation")
    ev.add_argument("--seeds", default="2026,7,404")
    ev.add_argument("--matches", type=int, default=4)
    ev.set_defaults(func=cmd_eval)

    c = sub.add_parser("calibrate", help="check the season against football-realistic targets")
    c.add_argument("--seed", type=int, default=2026)
    c.set_defaults(func=cmd_calibrate)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
