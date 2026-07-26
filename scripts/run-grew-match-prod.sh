#!/usr/bin/env bash
# run-grew-match-prod.sh — production runner for grew-match, meant to
# be the ExecStart of a systemd unit (see grew-match.service.example
# and grew-match-apache.conf.example at the repo root, and "Production
# deployment" in doc/grew-match.md).
#
# grew_match_quick.py rewrites grew_match/config.json and
# instances/gmq_instance.json on every start, always keying
# config.json's "instances" map by "localhost:<frontend_port>" — it
# has no notion of a public domain. The frontend's own JS looks itself
# up by `instances[window.location.host]`, so a browser visiting the
# public URL needs a matching entry with a *publicly reachable* backend
# URL, or it just breaks (undefined lookup). So: start grew_match_quick
# in the background, wait for its backend to answer, then patch
# config.json to add that entry (and the same DELPH-IN Grammary
# branding run.sh applies for local dev — see doc/grew-match.md if
# rebranding for a different deployment), then wait on grew_match_quick
# itself so systemd tracks the whole thing as one unit.
#
# Required environment (set these in the systemd unit; see the
# .example file):
#   GREW_CORPORA             path to the merged corpora.json to serve
#   GREW_PUBLIC_HOST          public hostname the frontend is served at
#                             — must equal window.location.host exactly:
#                             no scheme, and a port only if non-default
#   GREW_PUBLIC_BACKEND_URL   publicly reachable backend URL (e.g.
#                             behind an Apache proxy at /grew-match-api/)
#   LTDB_BASE_URL             public LTDB base URL. Read directly by
#                             the patched grew_match_dream backend
#                             itself (see etc/grew_match_dream.patch)
#                             to expand the relative sentence/grammar
#                             links it embeds in search results — this
#                             is not just cosmetic branding, omitting
#                             it leaves every link in results broken
#
# Optional: GREW_FRONTEND_PORT (default 8000), GREW_BACKEND_PORT
# (default 8899).
set -euo pipefail

cd "$(dirname "$0")/.."
source scripts/opam-env.sh

: "${GREW_CORPORA:?set GREW_CORPORA to a merged corpora.json path}"
: "${GREW_PUBLIC_HOST:?set GREW_PUBLIC_HOST to the public hostname}"
: "${GREW_PUBLIC_BACKEND_URL:?set GREW_PUBLIC_BACKEND_URL to the public backend URL}"
: "${LTDB_BASE_URL:?set LTDB_BASE_URL to the public LTDB base URL}"
FRONTEND_PORT="${GREW_FRONTEND_PORT:-8000}"
BACKEND_PORT="${GREW_BACKEND_PORT:-8899}"

sleep infinity | uv run python3 grew_match_quick/grew_match_quick.py "$GREW_CORPORA" \
    --frontend_port "$FRONTEND_PORT" --backend_port "$BACKEND_PORT" &
GMQ_PID=$!

echo "Waiting for grew-match backend on :${BACKEND_PORT}..."
up=""
for _ in $(seq 30); do
  # "localhost", not 127.0.0.1: some hosts bind the backend to the
  # IPv6 loopback (::1) only, and a hardcoded IPv4 address then always
  # fails to connect even once the backend is genuinely ready
  if curl -s -m 2 -X POST "http://localhost:${BACKEND_PORT}/ping" >/dev/null 2>&1; then
    up=1
    break
  fi
  sleep 2
done
if [ -z "$up" ]; then
  echo "grew-match backend did not come up in time" >&2
  kill "$GMQ_PID" 2>/dev/null || true
  exit 1
fi

echo "Patching grew_match/config.json for the public host..."
python3 - "$GREW_PUBLIC_HOST" "$GREW_PUBLIC_BACKEND_URL" "$LTDB_BASE_URL" <<'PY'
import json
import sys

public_host, public_backend_url, ltdb_base_url = sys.argv[1], sys.argv[2], sys.argv[3]
frontend_dir = "grew_match_quick/local_files/grew_match"

config_path = f"{frontend_dir}/config.json"
with open(config_path) as f:
    cfg = json.load(f)
cfg["snippets_url"] = "snippets/"
cfg.setdefault("instances", {})[public_host] = {
    "backend": public_backend_url,
    "instance": "gmq_instance.json",
}
for instance_cfg in cfg["instances"].values():
    instance_cfg["top_project"] = {
        "website": "https://delph-in.github.io/docs/home/Home/",
        "logo": "https://github.com/delph-in.png",
        "ltdb_url": ltdb_base_url,
    }
with open(config_path, "w") as f:
    json.dump(cfg, f, indent=2)

instance_path = f"{frontend_dir}/instances/gmq_instance.json"
with open(instance_path) as f:
    groups = json.load(f)
for group in groups:
    group["id"] = "DELPH-IN Grammary Corpora"
with open(instance_path, "w") as f:
    json.dump(groups, f, indent=2)
PY

echo "grew-match ready: frontend :${FRONTEND_PORT}, backend :${BACKEND_PORT}"
wait "$GMQ_PID"
