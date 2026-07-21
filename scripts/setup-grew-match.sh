#!/usr/bin/env bash
# setup-grew-match.sh
#
# Clone and build the grew-match stack (grew_match_quick, the grew_match
# frontend and the patched grew_match_dream backend) next to the LTDB
# app, and optionally precompile a corpora description so that
# `run.sh --grew-match` starts quickly.
#
# Usage: scripts/setup-grew-match.sh [CORPORA_JSON]
#   CORPORA_JSON - corpora description (e.g. web/db/grew_corpora.json);
#                  when given it is installed as the grew corpusbank and
#                  compiled with `grew compile` (a no-op when up to date).
#
# Requires grew and dune from an opam switch (see doc/grew-match.md).

set -euo pipefail

corpora="${1:-}"
# resolve the corpora path relative to the caller's cwd before we cd
if [ -n "$corpora" ]; then
  corpora=$(realpath "$corpora")
fi

cd "$(dirname "$0")/.."

# grew and dune live in the opam switch, which may not be on PATH
source scripts/opam-env.sh
if ! command -v dune >/dev/null 2>&1 || ! command -v grew >/dev/null 2>&1; then
  echo "grew/dune not found; install them with opam (see doc/grew-match.md)" >&2
  exit 1
fi

if [ ! -f grew_match_quick/grew_match_quick.py ]; then
  git clone https://github.com/grew-nlp/grew_match_quick
fi
# Clone the frontend ourselves: if only local_files/grew_match/instances
# is pre-created (the workaround grew_match_quick needs), the script
# mistakes the stub for a checkout and never fetches the frontend. We
# apply small branding/UX patches on top (DELPH-IN Grammary links in
# the corpus dropdown and navbar — see doc/grew-match.md).
if [ ! -d grew_match_quick/local_files/grew_match/.git ]; then
  git clone https://github.com/grew-nlp/grew_match.git \
      grew_match_quick/local_files/grew_match
  git -C grew_match_quick/local_files/grew_match \
      apply "$PWD/etc/grew_match.patch"
  git -C grew_match_quick/local_files/grew_match \
      -c user.name="ltdb setup-grew-match.sh" -c user.email="ltdb@localhost" \
      commit -qam "apply ltdb local patches (etc/grew_match.patch)"
fi
mkdir -p grew_match_quick/local_files/grew_match/instances
# serve the LTDB query snippets from the frontend (run.sh points
# config.json's snippets_url here after each start)
ln -sfn ../../../etc/grew_snippets \
    grew_match_quick/local_files/grew_match/snippets
# The backend needs fixes that are not upstream yet (result meta
# encoding, url/code passthrough, LTDB_BASE_URL expansion — see
# doc/grew-match.md), so clone it before grew_match_quick.py does
# and apply them.
if [ ! -d grew_match_quick/local_files/grew_match_dream/.git ]; then
  git clone https://github.com/grew-nlp/grew_match_dream.git \
      grew_match_quick/local_files/grew_match_dream
  git -C grew_match_quick/local_files/grew_match_dream \
      apply "$PWD/etc/grew_match_dream.patch"
  git -C grew_match_quick/local_files/grew_match_dream \
      -c user.name="ltdb setup-grew-match.sh" -c user.email="ltdb@localhost" \
      commit -qam "apply ltdb local patches (etc/grew_match_dream.patch)"
fi

# build the backend if it has not been built yet (grew_match_quick.py
# rebuilds it on every server start, so an existing binary is enough)
if [ ! -x grew_match_quick/local_files/grew_match_dream/_build/default/src/main.exe ]; then
  echo "Building the grew_match_dream backend"
  (cd grew_match_quick/local_files/grew_match_dream && dune build)
fi

if [ -n "$corpora" ]; then
  if [ ! -f "$corpora" ]; then
    echo "No such corpora description: $corpora" >&2
    exit 1
  fi
  # install the corpusbank exactly as grew_match_quick.py would write it,
  # so a later run.sh --grew-match start finds everything compiled
  mkdir -p grew_match_quick/local_files/corpusbank
  cp "$corpora" grew_match_quick/local_files/corpusbank/gmq_corpora.json
  echo "Compiling corpora from ${corpora} (no-op when up to date)"
  grew compile -CORPUSBANK grew_match_quick/local_files/corpusbank
fi
