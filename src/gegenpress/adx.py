"""Azure Data Explorer / Fabric Eventhouse backend.

Requires:
    pip install azure-kusto-data azure-kusto-ingest azure-identity

Configuration, by environment variable:
    ADX_CLUSTER   https://<name>.<region>.kusto.windows.net
                  (a free cluster is https://<name>.kusto.windows.net)
    ADX_DATABASE  database name, default "gegenpress"

Auth uses DefaultAzureCredential, so `az login` on a dev box and a managed
identity in Container Apps both work with no code change.
"""

from __future__ import annotations

import json
import os
import pathlib
from typing import Any

from .models import Match
from .season import League
from .store import GroundedMoment

KQL_DIR = pathlib.Path(__file__).resolve().parent.parent.parent / "kql"


class AdxStore:
    def __init__(self, cluster: str, database: str) -> None:
        from azure.kusto.data import KustoClient, KustoConnectionStringBuilder

        self.cluster = cluster
        self.database = database
        kcsb = KustoConnectionStringBuilder.with_az_cli_authentication(cluster)
        self._client = KustoClient(kcsb)
        self._league: League | None = None

    @classmethod
    def from_env(cls) -> "AdxStore":
        cluster = os.environ.get("ADX_CLUSTER")
        if not cluster:
            raise RuntimeError("ADX_CLUSTER is not set")
        return cls(cluster, os.environ.get("ADX_DATABASE", "gegenpress"))

    # -- control plane -------------------------------------------------

    def bootstrap(self) -> None:
        """Create tables, mappings and functions from the .kql files."""
        for name in ("01_schema.kql", "02_functions.kql"):
            path = KQL_DIR / name
            print(f"[adx] applying {name}")
            for command in _split_commands(path.read_text()):
                self._client.execute_mgmt(self.database, command)
        print("[adx] bootstrap complete")

    def ingest_season(self, league: League, matches: list[Match], batch: int = 20000) -> int:
        from azure.kusto.data import KustoConnectionStringBuilder
        from azure.kusto.ingest import IngestionProperties, QueuedIngestClient
        from azure.kusto.data.data_format import DataFormat

        ingest_uri = self.cluster.replace("https://", "https://ingest-")
        client = QueuedIngestClient(
            KustoConnectionStringBuilder.with_az_cli_authentication(ingest_uri)
        )

        def push(table: str, mapping: str, rows: list[dict[str, Any]]) -> None:
            if not rows:
                return
            import io
            props = IngestionProperties(
                database=self.database, table=table,
                data_format=DataFormat.JSON, ingestion_mapping_reference=mapping,
            )
            payload = io.StringIO("\n".join(json.dumps(r) for r in rows))
            client.ingest_from_stream(payload, ingestion_properties=props)

        push("Players", "PlayersJsonMapping", [
            {"player_id": p.player_id, "name": p.name, "club_id": p.club_id,
             "position": p.position, "shirt": p.shirt,
             "attributes": p.attributes.as_dict()}
            for p in league.players
        ])
        push("Clubs", "ClubsJsonMapping", [
            {"club_id": c.club_id, "name": c.name, "short_name": c.short_name,
             "style": round(c.style, 4)}
            for c in league.clubs
        ])

        total, buffer = 0, []
        for match in matches:
            for e in match.events:
                buffer.append(e.as_row())
                if len(buffer) >= batch:
                    push("Events", "EventsJsonMapping", buffer)
                    total += len(buffer)
                    print(f"[adx] {total:,} events", end="\r", flush=True)
                    buffer = []
        push("Events", "EventsJsonMapping", buffer)
        total += len(buffer)
        print(f"[adx] ingested {total:,} events")
        return total

    # -- query plane ---------------------------------------------------

    def _query(self, kql: str) -> list[dict[str, Any]]:
        response = self._client.execute(self.database, kql)
        table = response.primary_results[0]
        return [dict(zip(table.columns_names, row)) for row in table.rows] \
            if hasattr(table, "columns_names") else [r.to_dict() for r in table]

    def load_season(self, league: League, matches: list[Match]) -> None:
        """Season data lives in the cluster; keep the league for names."""
        self._league = league

    def _name(self, player_id: str) -> str:
        if self._league is None:
            return player_id
        try:
            return self._league.player(player_id).name
        except KeyError:
            return player_id

    def top_moments(self, live: Match, min_beats: float = 0.97, limit: int = 20):
        rows = self._query(
            f'TopMoments("{live.match_id}", {min_beats}, {limit})'
        )
        return [
            GroundedMoment(
                event_id=r["event_id"], minute=int(r["minute"]),
                player_id=r["player_id"], player_name=self._name(r["player_id"]),
                team_id=r["team_id"], metric=r["metric"], value=float(r["value"]),
                direction=r["direction"], expected=float(r["expected"]),
                beats=float(r["beats"]), population_n=int(r["population_n"]),
                personal_mean=_opt(r.get("personal_mean")),
                personal_best=_opt(r.get("personal_best")),
                personal_n=int(r.get("personal_n") or 0),
                is_personal_best=bool(r.get("is_personal_best")),
            )
            for r in rows
        ]

    def match_state(self, live: Match, as_of_minute: int = 120, window_minutes: int = 15):
        rows = self._query(
            f'MatchState("{live.match_id}", {as_of_minute}, {window_minutes})'
        )
        return {r.pop("team_id"): r for r in rows}

    def follow_target(self, live: Match, as_of_minute: int = 120):
        rows = self._query(f'FollowTarget("{live.match_id}", {as_of_minute})')
        return [(r["player_id"], float(r["follow_score"])) for r in rows]


def _opt(value: Any) -> float | None:
    return None if value is None or value == "" else float(value)


def _split_commands(text: str) -> list[str]:
    """Split a .kql control file into individual commands.

    Control commands start with '.' at column zero. Fenced blocks (```)
    may contain blank lines and dots, so they are passed through intact.
    """
    commands: list[str] = []
    current: list[str] = []
    in_fence = False
    for line in text.splitlines():
        stripped = line.strip()
        # A fence can open as ```[ and close as ]```, so match anywhere on
        # the line and toggle once per delimiter rather than per line.
        fences = line.count("```")
        if fences:
            if fences % 2:
                in_fence = not in_fence
            current.append(line)
            continue
        if not in_fence and line.startswith(".") and current:
            commands.append("\n".join(current).strip())
            current = [line]
            continue
        if not in_fence and not stripped and not current:
            continue
        if not in_fence and stripped.startswith("//") and not current:
            continue
        current.append(line)
    if current:
        commands.append("\n".join(current).strip())
    return [c for c in commands if c and not c.startswith("//")]
