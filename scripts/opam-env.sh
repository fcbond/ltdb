# opam-env.sh — put the opam switch (grew, dune) on PATH if needed.
#
# Source this from a script whose child processes run grew or dune.
# No-op when both are already available; quietly does nothing when opam
# is missing (callers decide whether that is fatal).

if ! command -v dune >/dev/null 2>&1 || ! command -v grew >/dev/null 2>&1; then
  if [ -x "$HOME/.local/bin/opam" ]; then
    eval "$("$HOME/.local/bin/opam" env)"
  elif command -v opam >/dev/null 2>&1; then
    eval "$(opam env)"
  fi
fi
