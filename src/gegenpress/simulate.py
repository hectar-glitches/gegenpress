"""Match event simulation.

A possession-chain model: the ball moves between players through passes and
carries, defenders apply pressure, chains end in a shot or a turnover.
Outcome probabilities are driven by the acting player's permanent
attributes, so a good passer really does complete more passes -- across the
whole season, not just in one match.

Deterministic for a given (season seed, match_id).
"""

from __future__ import annotations

import math
import random

from .models import PITCH_LENGTH, PITCH_WIDTH, Event, Match, Player
from .season import Fixture, League

SECONDS_PER_PERIOD = 45 * 60


class _Clock:
    def __init__(self) -> None:
        self.period = 1
        self.t = 0.0

    def advance(self, seconds: float) -> bool:
        """Returns False once the match is over."""
        self.t += seconds
        if self.t >= SECONDS_PER_PERIOD:
            if self.period == 2:
                return False
            self.period = 2
            self.t = 0.0
        return True


def _distance(x1: float, y1: float, x2: float, y2: float) -> float:
    return math.hypot(x2 - x1, y2 - y1)


def _pass_difficulty(distance: float, pressure: int, forward: float) -> float:
    """0.0 (trivial) to 1.0 (very hard).

    Long, forward, pressed passes are hard. The weights are deliberately
    simple and documented so the explanation layer can cite them.
    """
    d = min(1.0, distance / 45.0)
    p = min(1.0, pressure / 3.0)
    f = max(0.0, forward)
    raw = 0.45 * d + 0.35 * p + 0.20 * f
    return round(min(1.0, raw), 3)


class MatchSimulator:
    def __init__(self, league: League, fixture: Fixture, seed: int) -> None:
        self.league = league
        self.fixture = fixture
        self.rng = random.Random(f"{seed}:{fixture.match_id}")
        self.home = league.club(fixture.home_club_id)
        self.away = league.club(fixture.away_club_id)
        # Starting XI only: first 11 shirts.
        self.lineups = {
            self.home.club_id: [p for p in league.squad(self.home.club_id) if p.shirt <= 11],
            self.away.club_id: [p for p in league.squad(self.away.club_id) if p.shirt <= 11],
        }
        self._n = 0

    # -- helpers -------------------------------------------------------

    def _next_id(self) -> str:
        self._n += 1
        return f"{self.fixture.match_id}-e{self._n:05d}"

    def _opponent(self, team_id: str) -> str:
        return self.away.club_id if team_id == self.home.club_id else self.home.club_id

    def _pick(self, team_id: str, weights: dict[str, float] | None = None) -> Player:
        squad = self.lineups[team_id]
        if weights is None:
            return self.rng.choice(squad)
        w = [weights.get(p.position, 1.0) for p in squad]
        return self.rng.choices(squad, weights=w, k=1)[0]

    def _pick_presser(self, team_id: str) -> Player:
        """Who wins the ball back, weighted by pressing ability.

        Position alone would give every player the league's recovery
        distribution. Weighting by the pressing attribute is what makes a
        player's own recovery history mean something.
        """
        squad = self.lineups[team_id]
        base = {"DF": 2.0, "MF": 2.0, "FW": 0.8, "GK": 0.3}
        weights = [base.get(p.position, 1.0) * (0.2 + p.attributes.pressing) for p in squad]
        return self.rng.choices(squad, weights=weights, k=1)[0]

    def _pressure_count(self, defending_team: str, x: float, stamina_drain: float) -> int:
        """How many defenders close the ball, driven by their pressing attribute."""
        squad = self.lineups[defending_team]
        press = sum(p.attributes.pressing for p in squad) / len(squad)
        # Pressing fades as the match wears on.
        press *= 1.0 - 0.25 * stamina_drain
        # Teams press harder in their own half.
        zone = 1.0 + 0.4 * (1.0 - x / PITCH_LENGTH)
        lam = max(0.1, press * zone * 1.6)
        return min(4, self.rng.poisson(lam) if hasattr(self.rng, "poisson") else _poisson(self.rng, lam))

    # -- main loop -----------------------------------------------------

    def run(self) -> Match:
        events: list[Event] = []
        clock = _Clock()
        in_possession = self.rng.choice([self.home.club_id, self.away.club_id])
        x, y = PITCH_LENGTH / 2, PITCH_WIDTH / 2
        carrier = self._pick(in_possession, {"MF": 2.0, "DF": 1.5, "FW": 1.0, "GK": 0.2})
        goals = {self.home.club_id: 0, self.away.club_id: 0}
        last_turnover_at: float | None = None

        while True:
            drain = (clock.period - 1 + clock.t / SECONDS_PER_PERIOD) / 2.0
            defending = self._opponent(in_possession)
            pressure = self._pressure_count(defending, x, drain)

            # Record the pressure event itself when it is meaningful.
            if pressure >= 2:
                presser = self._pick(defending, {"FW": 2.0, "MF": 1.8, "DF": 1.0, "GK": 0.05})
                events.append(
                    Event(
                        event_id=self._next_id(),
                        match_id=self.fixture.match_id,
                        period=clock.period,
                        clock=round(clock.t, 1),
                        team_id=defending,
                        player_id=presser.player_id,
                        type="pressure",
                        x=round(PITCH_LENGTH - x, 1),
                        y=round(PITCH_WIDTH - y, 1),
                        detail={"pressure_count": pressure},
                    )
                )

            action = self._choose_action(carrier, x, pressure)

            if action == "shot":
                events.append(self._shot(carrier, in_possession, x, y, clock, pressure))
                scored = events[-1].outcome
                if scored:
                    goals[in_possession] += 1
                in_possession = self._opponent(in_possession)
                x, y = PITCH_LENGTH / 2, PITCH_WIDTH / 2
                carrier = self._pick(in_possession, {"GK": 3.0, "DF": 2.0})
                if not clock.advance(self.rng.uniform(25, 60)):
                    break
                continue

            if action == "carry":
                event, x, y = self._carry(carrier, in_possession, x, y, clock, pressure)
                events.append(event)
                if not clock.advance(self.rng.uniform(1.5, 4.0)):
                    break
                continue

            # Default: a pass.
            event, nx, ny, completed, receiver = self._pass(
                carrier, in_possession, x, y, clock, pressure
            )
            events.append(event)

            # Possession is not only lost by misplacing a pass. Tackles,
            # interceptions, fouls and the ball going out all end chains.
            # Without this, chains run far too long and the recovery-time
            # distribution grows an unrealistic tail.
            presser = self._pick_presser(defending)
            if completed:
                tackler_odds = (0.03 + 0.03 * pressure) * (0.4 + 1.6 * presser.attributes.pressing)
                if self.rng.random() < tackler_odds:
                    completed = False

            if completed:
                x, y, carrier = nx, ny, receiver
            else:
                # Turnover. The winning side records a recovery, and we
                # measure how long they took to get the ball back.
                now = (clock.period - 1) * SECONDS_PER_PERIOD + clock.t
                recovery_time = None if last_turnover_at is None else round(now - last_turnover_at, 1)
                last_turnover_at = now

                winner = presser
                events.append(
                    Event(
                        event_id=self._next_id(),
                        match_id=self.fixture.match_id,
                        period=clock.period,
                        clock=round(clock.t, 1),
                        team_id=defending,
                        player_id=winner.player_id,
                        type="recovery",
                        x=round(PITCH_LENGTH - nx, 1),
                        y=round(PITCH_WIDTH - ny, 1),
                        outcome=True,
                        detail={
                            "pressure_count": pressure,
                            "recovery_time_s": recovery_time,
                            "in_final_third": bool((PITCH_LENGTH - nx) > PITCH_LENGTH * 2 / 3),
                        },
                    )
                )
                in_possession = defending
                x, y = PITCH_LENGTH - nx, PITCH_WIDTH - ny
                carrier = winner

            if not clock.advance(self.rng.uniform(1.5, 6.5)):
                break

        return Match(
            match_id=self.fixture.match_id,
            matchday=self.fixture.matchday,
            home_club_id=self.home.club_id,
            away_club_id=self.away.club_id,
            events=events,
            home_goals=goals[self.home.club_id],
            away_goals=goals[self.away.club_id],
        )

    # -- actions -------------------------------------------------------

    def _choose_action(self, carrier: Player, x: float, pressure: int) -> str:
        in_box = x > PITCH_LENGTH - 18
        shot_w = 0.0
        if in_box:
            shot_w = 1.35 * (0.4 + carrier.attributes.finishing)
        elif x > PITCH_LENGTH - 30:
            shot_w = 0.18 * carrier.attributes.finishing
        carry_w = 2.5 * carrier.attributes.pace * (1.0 - 0.25 * pressure)
        pass_w = 10.0
        return self.rng.choices(
            ["shot", "carry", "pass"], weights=[max(0.0, shot_w), max(0.1, carry_w), pass_w], k=1
        )[0]

    def _pass(self, carrier, team_id, x, y, clock, pressure):
        club = self.league.club(team_id)
        # Possession sides play shorter; counter sides go longer.
        # Club style sets the team's shape; the passer's own ability moves
        # it. Without the second term every player's distribution is the
        # league's, and the personal reference class carries no signal.
        base = 20.0 - 8.0 * club.style + 18.0 * (carrier.attributes.passing - 0.5)
        distance = max(4.0, self.rng.gauss(base, 5.5))
        angle = self.rng.gauss(0.0, 1.5)
        nx = min(PITCH_LENGTH - 1, max(1.0, x + distance * math.cos(angle)))
        ny = min(PITCH_WIDTH - 1, max(1.0, y + distance * math.sin(angle)))
        actual = _distance(x, y, nx, ny)
        forward = (nx - x) / max(1.0, actual)
        difficulty = _pass_difficulty(actual, pressure, forward)

        skill = carrier.attributes.passing
        # Calibrated so that a median-difficulty pass by an average passer
        # completes about 82% of the time, matching reported top-flight
        # pass accuracy. See calibrate.py.
        p_complete = min(0.985, max(0.12, 0.96 - difficulty * (0.62 - 0.45 * skill)))
        completed = self.rng.random() < p_complete

        receiver = self._pick(team_id)
        ball_speed = round(max(6.0, self.rng.gauss(
            9.0 + 0.16 * actual + 9.0 * carrier.attributes.passing, 1.6)), 1)

        event = Event(
            event_id=self._next_id(),
            match_id=self.fixture.match_id,
            period=clock.period,
            clock=round(clock.t, 1),
            team_id=team_id,
            player_id=carrier.player_id,
            type="pass",
            x=round(x, 1),
            y=round(y, 1),
            end_x=round(nx, 1),
            end_y=round(ny, 1),
            outcome=completed,
            detail={
                "pass_distance_m": round(actual, 1),
                "pass_difficulty": difficulty,
                "ball_speed_ms": ball_speed,
                "pressure_count": pressure,
                "receiver_id": receiver.player_id if completed else None,
                "progressive": bool(nx - x > 10.0),
            },
        )
        return event, nx, ny, completed, receiver

    def _carry(self, carrier, team_id, x, y, clock, pressure):
        gain = max(1.0, self.rng.gauss(4.0 + 11.0 * carrier.attributes.pace, 2.2))
        nx = min(PITCH_LENGTH - 1, x + gain)
        ny = min(PITCH_WIDTH - 1, max(1.0, y + self.rng.gauss(0, 4)))
        speed = round(max(2.0, self.rng.gauss(4.0 + 5.5 * carrier.attributes.pace, 0.7)), 2)
        event = Event(
            event_id=self._next_id(),
            match_id=self.fixture.match_id,
            period=clock.period,
            clock=round(clock.t, 1),
            team_id=team_id,
            player_id=carrier.player_id,
            type="carry",
            x=round(x, 1),
            y=round(y, 1),
            end_x=round(nx, 1),
            end_y=round(ny, 1),
            outcome=True,
            detail={
                "carry_distance_m": round(nx - x, 1),
                "top_speed_ms": speed,
                "pressure_count": pressure,
            },
        )
        return event, nx, ny

    def _shot(self, carrier, team_id, x, y, clock, pressure):
        goal_x, goal_y = PITCH_LENGTH, PITCH_WIDTH / 2
        distance = _distance(x, y, goal_x, goal_y)
        # A transparent, citable xG: distance and angle, damped by pressure.
        angle = abs(math.atan2(abs(y - goal_y), max(1.0, goal_x - x)))
        xg = 1.45 * math.exp(-0.095 * distance) * math.exp(-1.0 * angle)
        xg *= 1.0 - 0.12 * pressure
        xg = round(min(0.95, max(0.01, xg * (0.6 + 0.8 * carrier.attributes.finishing))), 3)
        scored = self.rng.random() < xg
        return Event(
            event_id=self._next_id(),
            match_id=self.fixture.match_id,
            period=clock.period,
            clock=round(clock.t, 1),
            team_id=team_id,
            player_id=carrier.player_id,
            type="shot",
            x=round(x, 1),
            y=round(y, 1),
            end_x=goal_x,
            end_y=round(goal_y, 1),
            outcome=scored,
            detail={
                "xg": xg,
                "shot_distance_m": round(distance, 1),
                "shot_speed_ms": round(max(12.0, self.rng.gauss(24.0, 4.0)), 1),
                "pressure_count": pressure,
            },
        )


def _poisson(rng: random.Random, lam: float) -> int:
    """Knuth's method; random.Random has no poisson."""
    limit = math.exp(-lam)
    k, p = 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1
        if k > 20:
            return k


def simulate_match(league: League, fixture: Fixture, seed: int = 2026) -> Match:
    return MatchSimulator(league, fixture, seed).run()


def simulate_season(league: League, seed: int = 2026) -> list[Match]:
    return [simulate_match(league, f, seed) for f in league.fixtures]
