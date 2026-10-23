"""Build a persistent league: clubs, squads, fixtures.

The squad is generated once per season seed and never changes. That
persistence is what makes a per-player reference class ("his best press in
six games") a real claim instead of a comparison of two random draws.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from .models import Attributes, Club, Player, Position
from .names import CLUBS, FIRST_NAMES, SURNAMES

# 4-3-3. Index order is stable so shirt numbers stay sensible.
FORMATION: list[Position] = (
    ["GK"] + ["DF"] * 4 + ["MF"] * 3 + ["FW"] * 3
)
SQUAD_SIZE = 16  # XI plus five on the bench

# Position priors: the mean of each attribute before per-player noise.
# A centre-back is a better tackler than a striker, on average.
POSITION_PRIORS: dict[Position, dict[str, float]] = {
    "GK": dict(pace=0.35, passing=0.50, pressing=0.20, finishing=0.05, tackling=0.30, stamina=0.45),
    "DF": dict(pace=0.52, passing=0.55, pressing=0.58, finishing=0.22, tackling=0.72, stamina=0.65),
    "MF": dict(pace=0.56, passing=0.72, pressing=0.68, finishing=0.45, tackling=0.58, stamina=0.78),
    "FW": dict(pace=0.72, passing=0.58, pressing=0.62, finishing=0.74, tackling=0.30, stamina=0.66),
}

ATTRIBUTE_NAMES = ("pace", "passing", "pressing", "finishing", "tackling", "stamina")


@dataclass(frozen=True, slots=True)
class Fixture:
    match_id: str
    matchday: int
    home_club_id: str
    away_club_id: str


@dataclass(frozen=True, slots=True)
class League:
    clubs: list[Club]
    players: list[Player]
    fixtures: list[Fixture]

    def squad(self, club_id: str) -> list[Player]:
        return [p for p in self.players if p.club_id == club_id]

    def player(self, player_id: str) -> Player:
        for p in self.players:
            if p.player_id == player_id:
                return p
        raise KeyError(player_id)

    def club(self, club_id: str) -> Club:
        for c in self.clubs:
            if c.club_id == club_id:
                return c
        raise KeyError(club_id)


def _clamp(value: float, low: float = 0.05, high: float = 0.98) -> float:
    return max(low, min(high, value))


def _make_attributes(rng: random.Random, position: Position, quality: float) -> Attributes:
    """Draw a player's permanent ability profile.

    `quality` shifts the whole profile -- a top club's players are better
    across the board -- while per-attribute noise gives each player a shape
    (a quick, poor-passing full-back; a slow, excellent passer).
    """
    priors = POSITION_PRIORS[position]
    drawn = {
        name: _clamp(priors[name] + (quality - 0.5) * 0.30 + rng.gauss(0.0, 0.12))
        for name in ATTRIBUTE_NAMES
    }
    return Attributes(**drawn)


def build_league(seed: int = 2026, num_clubs: int = 10) -> League:
    """Deterministic league construction. Same seed, same league, always."""
    rng = random.Random(seed)
    clubs: list[Club] = []
    players: list[Player] = []

    chosen = CLUBS[:num_clubs]
    for index, (name, short) in enumerate(chosen):
        club_id = short.lower()
        # Club quality is spread evenly then jittered, so the league has a
        # top end and a bottom end rather than twenty identical sides.
        quality = _clamp(0.30 + 0.45 * (index / max(1, num_clubs - 1)) + rng.gauss(0, 0.05), 0.2, 0.9)
        clubs.append(
            Club(
                club_id=club_id,
                name=name,
                short_name=short,
                style=_clamp(rng.uniform(0.25, 0.85), 0.1, 0.95),
                line_height=rng.uniform(28.0, 46.0),
            )
        )

        used_names: set[str] = set()
        for shirt in range(1, SQUAD_SIZE + 1):
            position = FORMATION[shirt - 1] if shirt <= len(FORMATION) else rng.choice(["DF", "MF", "FW"])
            while True:
                full = f"{rng.choice(FIRST_NAMES)} {rng.choice(SURNAMES)}"
                if full not in used_names:
                    used_names.add(full)
                    break
            players.append(
                Player(
                    player_id=f"{club_id}-{shirt:02d}",
                    name=full,
                    club_id=club_id,
                    shirt=shirt,
                    position=position,
                    attributes=_make_attributes(rng, position, quality),
                )
            )

    return League(clubs=clubs, players=players, fixtures=build_fixtures(chosen_ids=[c.club_id for c in clubs]))


def build_fixtures(chosen_ids: list[str]) -> list[Fixture]:
    """Single round-robin, home and away, by the circle method."""
    ids = list(chosen_ids)
    if len(ids) % 2:
        ids.append("__bye__")
    rounds = len(ids) - 1
    half = len(ids) // 2

    fixtures: list[Fixture] = []
    matchday = 0
    for leg in range(2):
        rotation = list(ids)
        for _ in range(rounds):
            matchday += 1
            for i in range(half):
                home, away = rotation[i], rotation[-1 - i]
                if "__bye__" in (home, away):
                    continue
                if leg == 1:
                    home, away = away, home
                fixtures.append(
                    Fixture(
                        match_id=f"m{matchday:02d}-{home}-{away}",
                        matchday=matchday,
                        home_club_id=home,
                        away_club_id=away,
                    )
                )
            rotation = [rotation[0]] + [rotation[-1]] + rotation[1:-1]
    return fixtures
