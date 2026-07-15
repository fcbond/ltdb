#!/bin/bash
set -euo pipefail

# Development-only runner. Binds to localhost and enables Flask debug mode.
# Use the systemd/gunicorn configuration for production deployments.
#
# Usage: ./run.sh [--grew-match [CORPORA_JSON]]
#
# --grew-match also starts a linked grew-match server (frontend :8000,
# backend :8899) and sets LTDB_GREW_MATCH_URL so the navigation bar
# links to it.  CORPORA_JSON is a corpora description produced by
# scripts/db2grew.py; if omitted, the single web/db/*-grew/corpora.json
# export is used.  See doc/grew-match.md for details.

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

start_grew_match() {
  if [ -z "$grew_corpora" ]; then
    local candidates=(web/db/*-grew/corpora.json)
    if [ ${#candidates[@]} -eq 0 ] || [ ! -f "${candidates[0]}" ]; then
      echo "No web/db/*-grew/corpora.json export found;" \
           "run scripts/db2grew.py first (see doc/grew-match.md)" >&2
      exit 1
    fi
    if [ ${#candidates[@]} -gt 1 ]; then
      echo "Several grew exports found, pass one explicitly:" >&2
      printf '  ./run.sh --grew-match "%s"\n' "${candidates[@]}" >&2
      exit 1
    fi
    grew_corpora="${candidates[0]}"
  fi
  if [ ! -f "$grew_corpora" ]; then
    echo "No such corpora description: $grew_corpora" >&2
    exit 1
  fi

  # reuse an instance that is already running (leave its lifecycle alone)
  if curl -s -m 2 -X POST "http://localhost:${gm_back_port}/ping" \
      >/dev/null 2>&1; then
    echo "Reusing the grew-match server already on port ${gm_back_port}"
    return
  fi

  # grew and dune live in the opam switch, which may not be on PATH
  if ! command -v dune >/dev/null 2>&1 || ! command -v grew >/dev/null 2>&1; then
    if [ -x "$HOME/.local/bin/opam" ]; then
      eval "$("$HOME/.local/bin/opam" env)"
    elif command -v opam >/dev/null 2>&1; then
      eval "$(opam env)"
    fi
  fi
  if ! command -v dune >/dev/null 2>&1 || ! command -v grew >/dev/null 2>&1; then
    echo "grew/dune not found; install them with opam (see doc/grew-match.md)" >&2
    exit 1
  fi

  if [ ! -f grew_match_quick/grew_match_quick.py ]; then
    git clone https://github.com/grew-nlp/grew_match_quick
  fi
  # Clone the frontend ourselves: if only local_files/grew_match/instances
  # is pre-created (the workaround grew_match_quick needs), the script
  # mistakes the stub for a checkout and never fetches the frontend.
  if [ ! -d grew_match_quick/local_files/grew_match/.git ]; then
    git clone https://github.com/grew-nlp/grew_match.git \
        grew_match_quick/local_files/grew_match
  fi
  mkdir -p grew_match_quick/local_files/grew_match/instances

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

if [ -n "$grew_match" ]; then
  start_grew_match
  export LTDB_GREW_MATCH_URL="http://localhost:${gm_front_port}"
fi

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
echo "Starting LTDB development server on http://127.0.0.1:${port}"
setsid uv run flask --app wsgi:app run --host 127.0.0.1 --port "${port}" \
    --debug </dev/null &
flask_pid=$!
wait "$flask_pid"
