"""Core data contracts for Gegenpress.

Everything downstream -- KQL ingestion, the agent layer, the overlay feed --
reads these shapes. Keep them boring, typed and stable.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Literal

# Pitch is modelled in metres, origin at the defending-left corner of the
# team in possession. 105x68 is the standard Premier League pitch.
PITCH_LENGTH = 105.0
PITCH_WIDTH = 68.0

Position = Literal["GK", "DF", "MF", "FW"]

EventType = Literal[
    "pass",
    "carry",
    "shot",
    "tackle",
    "pressure",
    "recovery",
    "duel",
    "turnover",
]


@dataclass(frozen=True, slots=True)
class Attributes:
    """A player's stable, season-long ability profile.

    These never change within a season. Match-to-match variation in a
    player's output is sampling noise around these values -- which is the
    whole reason "his best press in six games" is a meaningful claim rather
    than a comparison of two random draws.

    Every attribute is 0.0-1.0.
    """

    pace: float
    passing: float
    pressing: float
    finishing: float
    tackling: float
    stamina: float

    def as_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class Player:
    player_id: str
    name: str
    club_id: str
    shirt: int
    position: Position
    attributes: Attributes


@dataclass(frozen=True, slots=True)
class Club:
    club_id: str
    name: str
    short_name: str
    # 0.0 = deep block and counter, 1.0 = sustained high possession.
    style: float
    # Baseline defensive line height in metres from own goal.
    line_height: float


@dataclass(frozen=True, slots=True)
class Event:
    """One atomic match event.

    `period` is 1 or 2; `clock` is seconds elapsed within the period, so a
    78th-minute event in the second half has clock == (78-45)*60.
    """

    event_id: str
    match_id: str
    period: int
    clock: float
    team_id: str
    player_id: str
    type: EventType
    x: float
    y: float
    end_x: float | None = None
    end_y: float | None = None
    outcome: bool | None = None
    # Type-specific measurements: pass_distance_m, ball_speed_ms,
    # recovery_time_s, pressure_count, shot_speed_ms, difficulty ...
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def minute(self) -> int:
        return int((self.period - 1) * 45 + self.clock // 60)

    def as_row(self) -> dict[str, Any]:
        """Flat dict, ready for KQL streaming ingestion."""
        row = asdict(self)
        row["minute"] = self.minute
        return row


@dataclass(frozen=True, slots=True)
class Match:
    match_id: str
    matchday: int
    home_club_id: str
    away_club_id: str
    events: list[Event]
    home_goals: int
    away_goals: int
