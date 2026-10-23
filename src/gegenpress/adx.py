"""Azure Data Explorer / Fabric Eventhouse backend.

Requires:
    pip install azure-kusto-data azure-kusto-ingest azure-identity

Configuration, by environment variable:
    ADX_CLUSTER   the cluster URI, copied from the ADX web UI
    ADX_DATABASE  database name, default "gegenpress"
    ADX_AUTH      "interactive" (default), "device", or "cli"

Auth note: a FREE cluster has no Azure subscription behind it, so
`az login` is not a reliable route -- the Azure CLI wants a subscription
and a free cluster lives outside one. Interactive login opens a browser
and signs in with the plain Microsoft account that owns the cluster,
which is what a free cluster actually needs. Device-code login is there
for shells with no browser.
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
    def __init__(self, cluster: str, database: str, auth: str = "interactive") -> None:
        from azure.kusto.data import KustoClient

        self.cluster = cluster
        self.database = database
        self.auth = auth
        self._client = KustoClient(self._kcsb(cluster, auth))
        self._league: League | None = None

    @staticmethod
    def _kcsb(cluster: str, auth: str):
        from azure.kusto.data import KustoConnectionStringBuilder

        if auth == "cli":
            return KustoConnectionStringBuilder.with_az_cli_authentication(cluster)
        if auth == "device":
            # Prints a URL and a code; sign in on any device.
            return KustoConnectionStringBuilder.with_aad_device_authentication(cluster)
        return KustoConnectionStringBuilder.with_interactive_login(cluster)

    @classmethod
    def from_env(cls) -> "AdxStore":
        cluster = os.environ.get("ADX_CLUSTER")
        if not cluster:
            raise RuntimeError("ADX_CLUSTER is not set")
        return cls(
            cluster,
            os.environ.get("ADX_DATABASE", "gegenpress"),
            os.environ.get("ADX_AUTH", "interactive"),
        )

    # -- control plane -------------------------------------------------

    def bootstrap(self, strict: bool = False) -> int:
        """Create tables, mappings and functions from the .kql files.

        Reports each command rather than aborting on the first failure:
        some policy commands are unavailable on a free cluster, and one
        unsupported policy should not stop the tables and functions from
        being created. Returns the number of failures.
        """
        failures = 0
        for name in ("01_schema.kql", "02_functions.kql"):
            path = KQL_DIR / name
            print(f"\n[adx] {name}")
            for command in _split_commands(path.read_text()):
                label = command.splitlines()[0][:62]
                try:
                    self._client.execute_mgmt(self.database, command)
                    print(f"  ok    {label}")
                except Exception as exc:
                    failures += 1
                    detail = str(exc).replace("\n", " ")[:150]
                    print(f"  FAIL  {label}")
                    print(f"        {detail}")
                    if strict:
                        raise
        print(f"\n[adx] bootstrap finished, {failures} failure(s)")
        return failures

    def reset(self) -> None:
        """Clear table data before a reload.

        `.create-merge table` creates but never clears, so a second
        --load appends rather than replaces. Duplicated rows leave the
        percentile maths roughly intact but the counts wrong, and the
        parity test fails in a way that looks like a KQL bug.
        """
        for table in ("Events", "Players", "Clubs"):
            try:
                self._client.execute_mgmt(self.database, f".clear table {table} data")
                print(f"[adx] cleared {table}")
            except Exception as exc:
                print(f"[adx] could not clear {table}: {str(exc)[:90]}")

    def ingest_season(self, league: League, matches: list[Match], batch: int = 50000) -> int:
        """Stream a season in.

        Queued, not streaming: a free cluster refuses
        `.alter table ... policy streamingingestion enable`, but it does
        expose an ingest- endpoint. Queued ingestion batches server-side,
        so rows appear a minute or two after this returns.
        """
        import io

        from azure.kusto.data.data_format import DataFormat
        from azure.kusto.ingest import IngestionProperties, QueuedIngestClient

        ingest_uri = self.cluster.replace("https://", "https://ingest-")
        client = QueuedIngestClient(self._kcsb(ingest_uri, self.auth))

        def push(table: str, mapping: str, rows: list[dict[str, Any]]) -> None:
            if not rows:
                return
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

    def doctor(self, live_match_id: str) -> int:
        """Row counts and a smoke test of every function. Returns failures."""
        failures = 0
        empty = False
        print(f"cluster  {self.cluster}\ndatabase {self.database}\n")

        # Queued ingestion is asynchronous: a failed batch reports here,
        # not at the call site. Without this, "still landing" and
        # "silently rejected" look identical.
        try:
            fails = self._query(
                ".show ingestion failures "
                "| where FailedOn > ago(2h) "
                "| project FailedOn, Table, Details "
                "| order by FailedOn desc | take 5")
            if fails:
                print(f"ingestion failures in the last 2h: {len(fails)}")
                for f in fails:
                    print(f"  {f.get('Table')}: {str(f.get('Details'))[:110]}")
                print()
                failures += len(fails)
            else:
                print("ingestion failures in the last 2h: none\n")
        except Exception as exc:
            print(f"could not read ingestion failures: {str(exc)[:80]}\n")

        print("tables")
        for table in ("Events", "Players", "Clubs"):
            try:
                rows = self._query(f"{table} | count")
                n = list(rows[0].values())[0] if rows else 0
                flag = "" if n else "   <-- EMPTY"
                print(f"  {table:<10} {n:>10,}{flag}")
                if not n:
                    failures += 1
                    empty = True
            except Exception as exc:
                failures += 1
                print(f"  {table:<10} FAIL  {str(exc)[:90]}")

        try:
            rows = self._query(
                "Events | summarize n=count() by match_id "
                "| order by match_id asc | take 3")
            print("\n  sample match ids: " +
                  ", ".join(f"{r['match_id']} ({r['n']})" for r in rows))
            live = self._query(
                f'Events | where match_id == "{live_match_id}" | count')
            n = list(live[0].values())[0] if live else 0
            print(f"  live match {live_match_id}: {n:,} events"
                  + ("   <-- MISSING" if not n else ""))
            if not n:
                failures += 1
        except Exception as exc:
            print(f"  match id probe FAIL: {str(exc)[:90]}")

        print("\nfunctions")
        probes = [
            ("MetricSpecs", "MetricSpecs() | count"),
            ("MetricValues", "MetricValues() | take 1"),
            ("PopulationBaselines", 'PopulationBaselines("") | take 1'),
            ("PlayerBaselines", 'PlayerBaselines("") | take 1'),
            ("MetricSignal", 'MetricSignal("") | count'),
            ("Ground", f'Ground("{live_match_id}") | take 1'),
            ("TopMoments", f'TopMoments("{live_match_id}", 0.9, 3) | count'),
            ("MatchState", f'MatchState("{live_match_id}", 90, 90)'),
            ("MomentumShift", f'MomentumShift("{live_match_id}") | count'),
            ("FollowTarget", f'FollowTarget("{live_match_id}", 90) | count'),
        ]
        for name, kql in probes:
            try:
                rows = self._query(kql)
                print(f"  ok    {name:<20} {len(rows)} row(s)")
            except Exception as exc:
                failures += 1
                print(f"  FAIL  {name:<20} {str(exc).splitlines()[0][:100]}")
        if empty:
            print("\nTables are empty but no ingestion failures were reported.")
            print("Queued ingestion batches server-side and takes a few minutes.")
            print("Wait, then run doctor again. If it stays empty for more than")
            print("ten minutes, the batches were rejected rather than delayed.")
        print(f"\n{failures} problem(s)")
        return failures

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
                personal_claim_allowed=bool(r.get("personal_claim_allowed")),
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
    return [t for t in (_trim(c) for c in commands) if t and not t.startswith("//")]


def _trim(command: str) -> str:
    """Drop trailing blank and comment-only lines.

    Each command accumulates the NEXT command's comment header, and ADX
    refuses a control command with anything after its closing brace --
    every function but the last one failed to parse because of this.
    """
    lines = command.splitlines()
    while lines and (not lines[-1].strip() or lines[-1].lstrip().startswith("//")):
        lines.pop()
    return "\n".join(lines).strip()
