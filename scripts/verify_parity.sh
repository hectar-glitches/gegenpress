#!/usr/bin/env bash
# Prove that the KQL and the Python agree, end to end.
#
#   export ADX_CLUSTER=https://<cluster>.kusto.windows.net
#   bash scripts/verify_parity.sh
#
# The README claims the two implementations are checked against each
# other. This is the command that makes that true. It rebuilds the schema
# and functions, clears the tables, ingests a season plus the live match
# under its own id, waits for QUEUED ingestion to land (a free cluster
# refuses streaming), and then runs the parity test.
#
# Everything is driven from one seed, so the rows in the cluster and the
# fixture the test builds in memory describe the same football.
set -euo pipefail

: "${ADX_CLUSTER:?set ADX_CLUSTER to your cluster URI first}"
export ADX_DATABASE="${ADX_DATABASE:-gegenpress}"
export PYTHONPATH="${PYTHONPATH:-src}"

say() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }

say "Rebuilding schema and functions, clearing tables, ingesting"
python -m gegenpress ingest --bootstrap --reset --load

say "Waiting for queued ingestion"
# .create-merge and queued ingestion both return before the data is
# queryable. Polling beats a fixed sleep: it is usually under a minute,
# but a cold free cluster has taken five.
deadline=$(( SECONDS + 600 ))
last=0
while (( SECONDS < deadline )); do
  n=$(python - <<'PY' 2>/dev/null || echo 0
from gegenpress.adx import AdxStore
try:
    rows = AdxStore.from_env()._query("Events | summarize c=count()")
    print(int(rows[0]["c"]))
except Exception:
    print(0)
PY
)
  printf '    %s events\n' "$n"
  # Settled: a non-trivial count that has stopped climbing.
  if (( n > 100000 && n == last )); then
    say "Ingestion settled at $n events"
    break
  fi
  last=$n
  sleep 15
done

say "Row counts and every KQL function"
python -m gegenpress doctor

say "Parity"
python -m pytest tests/test_store.py::test_local_and_adx_agree -q
