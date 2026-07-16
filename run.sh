#!/bin/bash
set -euo pipefail

# Development-only runner. Binds to localhost and enables Flask debug mode.
# Use the systemd/gunicorn configuration for production deployments.
#
# Usage: ./run.sh [--grew-match [CORPORA_JSON]]
#
# --grew-match also starts a linked grew-match server (frontend :8000,
# backend :8899) and sets LTDB_GREW_MATCH_URL so the navigation bar
# links to it.  Any grew-match already on those ports is stopped first,
# so the new instance serves *our* corpora.  CORPORA_JSON is a corpora
# description produced by scripts/db2grew.py; if omitted, every
# web/db/*-grew/corpora.json export is served (merged into
# web/db/grew_corpora.json when there is more than one), falling back
# to a pre-built web/db/grew_corpora.json installed by a build pipeline
# (see scripts/setup-grew-match.sh and doc/grew-match.md).

cd "$(dirname "$0")"

grew_match=""
grew_corpora=""
while [ $# -gt 0 ]; do
  case "$1" in
    --grew-match)
      grew_match=1
      if [ $# -gt 1 ] && [[ "$2" != -* ]]; then
        grew_corpora="$2"
        shift
      fi
      ;;
    *)
      echo "Unknown option: $1" >&2
      echo "Usage: $0 [--grew-match [CORPORA_JSON]]" >&2
      exit 1
      ;;
  esac
  shift
done

gm_front_port=8000
gm_back_port=8899

gmq_pid=""
flask_pid=""

# Both the grew-match stack and flask run in their own process groups
# (setsid), so Ctrl-C is handled here: the INT/TERM trap turns the
# signal into an exit, and the EXIT trap tears both groups down.
cleanup() {
  if [ -n "$flask_pid" ]; then
    kill -TERM -- "-${flask_pid}" 2>/dev/null || true
  fi
  if [ -n "$gmq_pid" ]; then
    echo "Stopping grew-match"
    kill -TERM -- "-${gmq_pid}" 2>/dev/null || true
  fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# Stop whatever is listening on the grew-match ports (killing the whole
# process group catches the grew_match_quick wrapper along with the
# backend/frontend it spawned), then wait for the ports to be released.
stop_grew_match_servers() {
  local port pids pid pgid own_pgid
  own_pgid=$(ps -o pgid= -p $$ | tr -d ' ')
  for port in "$gm_back_port" "$gm_front_port"; do
    pids=$(lsof -t -i ":${port}" 2>/dev/null || true)
    [ -z "$pids" ] && continue
    echo "Stopping existing server on port ${port}"
    for pid in $pids; do
      pgid=$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d ' ')
      if [ -n "$pgid" ] && [ "$pgid" != "$own_pgid" ]; then
        kill -TERM -- "-${pgid}" 2>/dev/null || true
      else
        kill -TERM "$pid" 2>/dev/null || true
      fi
    done
  done
  for _ in $(seq 20); do
    if [ -z "$(lsof -t -i ":${gm_back_port}" -i ":${gm_front_port}" \
        2>/dev/null)" ]; then
      return 0
    fi
    sleep 1
  done
  echo "Ports ${gm_back_port}/${gm_front_port} are still in use" >&2
  exit 1
}

start_grew_match() {
  if [ -z "$grew_corpora" ]; then
    local candidates=(web/db/*-grew/corpora.json)
    if [ ${#candidates[@]} -eq 0 ] || [ ! -f "${candidates[0]}" ]; then
      # no local exports: fall back to a combined description installed
      # by a build pipeline (e.g. grammary's build-ltdb.sh)
      if [ ! -f web/db/grew_corpora.json ]; then
        echo "No web/db/grew_corpora.json or web/db/*-grew/corpora.json" \
             "export found; run scripts/db2grew.py first" \
             "(see doc/grew-match.md)" >&2
        exit 1
      fi
      grew_corpora="web/db/grew_corpora.json"
    elif [ ${#candidates[@]} -eq 1 ]; then
      grew_corpora="${candidates[0]}"
    else
      # several grammars are exported: serve them all from one instance
      grew_corpora="web/db/grew_corpora.json"
      echo "Merging ${#candidates[@]} grew exports into ${grew_corpora}"
      python3 - "$grew_corpora" "${candidates[@]}" <<'PY'
import json
import sys

merged_path, *corpora_paths = sys.argv[1:]
corpora = []
for path in corpora_paths:
    with open(path) as f:
        corpora.extend(json.load(f))
with open(merged_path, "w") as f:
    json.dump(corpora, f, indent=2)
PY
    fi
  fi
  if [ ! -f "$grew_corpora" ]; then
    echo "No such corpora description: $grew_corpora" >&2
    exit 1
  fi

  # take over the ports: an already-running instance keeps the corpora
  # and LTDB_BASE_URL from its own startup, so serving our corpora means
  # stopping it (grew_match_quick refuses to start on busy ports anyway)
  stop_grew_match_servers

  # grew and dune live in the opam switch, which may not be on PATH
  # (setup-grew-match.sh repeats this for itself; the `grew compile`
  # after startup below runs in this shell and needs it here too)
  if ! command -v dune >/dev/null 2>&1 || ! command -v grew >/dev/null 2>&1; then
    if [ -x "$HOME/.local/bin/opam" ]; then
      eval "$("$HOME/.local/bin/opam" env)"
    elif command -v opam >/dev/null 2>&1; then
      eval "$(opam env)"
    fi
  fi

  # clone/build the grew-match stack (no-op when already set up)
  bash scripts/setup-grew-match.sh

  local gmq_log=grew_match_quick/local_files/gmq.log
  echo "Starting grew-match for ${grew_corpora} (log: ${gmq_log})"
  setsid python3 grew_match_quick/grew_match_quick.py "$grew_corpora" \
      --frontend_port "$gm_front_port" --backend_port "$gm_back_port" \
      </dev/null >"$gmq_log" 2>&1 &
  gmq_pid=$!

  local up=""
  for _ in $(seq 30); do
    if curl -s -m 2 -X POST "http://localhost:${gm_back_port}/ping" \
        >/dev/null 2>&1; then
      up=1
      break
    fi
    sleep 2
  done
  if [ -z "$up" ]; then
    echo "grew-match backend did not come up; see ${gmq_log}" >&2
    exit 1
  fi

  # compile any uncompiled corpora (no-op when up to date) and make the
  # backend re-read the compiled status, or the UI says "Corpus not compiled"
  grew compile -CORPUSBANK grew_match_quick/local_files/corpusbank
  curl -s -X POST "http://localhost:${gm_back_port}/reload" >/dev/null
  echo "grew-match ready on http://localhost:${gm_front_port}"
}

uv sync

port=$(
  uv run python3 - <<'PY'
import socket

for port in range(5000, 5100):
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            continue
        print(port)
        break
else:
    raise SystemExit("No free localhost port found in 5000-5099")
PY
)

if [ -n "$grew_match" ]; then
  # the backend expands relative url metas with this base, so
  # grew-match results link back to the LTDB instance started below
  export LTDB_BASE_URL="http://127.0.0.1:${port}"
  start_grew_match
  export LTDB_GREW_MATCH_URL="http://localhost:${gm_front_port}"
fi

echo "Starting LTDB development server on http://127.0.0.1:${port}"
setsid uv run flask --app wsgi:app run --host 127.0.0.1 --port "${port}" \
    --debug </dev/null &
flask_pid=$!
wait "$flask_pid"
