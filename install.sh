#!/usr/bin/env bash
# install.sh - robust single-script installer & runner for the cavemen simulation.
# Works on NixOS (flake.nix/shell.nix available) and plain Linux (local venv fallback).
# Usage: ./install.sh [args passed to the app, e.g. --config config.yaml]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
VENV="$SCRIPT_DIR/.venv"
MIN_PY=3.10

log()  { printf '\033[1;32m[cavemen]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[cavemen]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[cavemen] ERROR: %s\n' "$*" >&2; exit 1; }

# --- Step 1/3: check Python ----------------------------------------------------
command -v python3 >/dev/null || die "python3 not found (need >= $MIN_PY). On NixOS run: nix shell ."
if ! python3 - "$MIN_PY" <<PYEOF
import sys
ok = sys.version_info[:2] >= tuple(int(x) for x in sys.argv[1].split("."))
sys.exit(0 if ok else 1)
PYEOF
then die "Python is older than required $MIN_PY (hint: nix shell .)."; fi
PYVER="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
log "Step 1/3 OK - python3 $PYVER found."
# --- Step 2/3: ensure pygame + pyyaml -------------------------------------------
if python3 -c 'import pygame, yaml' >/dev/null 2>&1; then
  PYTHON=python3
  log "Step 2/3 OK - dependencies already available."
elif [[ -x "$VENV/bin/python" ]] && "$VENV/bin/python" -c 'import pygame, yaml' >/dev/null 2>&1; then
  PYTHON="$VENV/bin/python"
  log "Step 2/3 OK - using existing project venv .venv/."
else
  warn "Dependencies missing - creating virtual environment in .venv/ (NixOS alt: nix run .#cavemen)"
  python3 -m venv "$VENV" || die "Could not create venv. On NixOS use: nix shell . (flake.nix provides deps)."
  PYTHON="$VENV/bin/python"
  "$PYTHON" -m pip install --quiet --upgrade pip || warn "pip upgrade failed, continuing anyway."
  "$PYTHON" -m pip install --quiet pygame pyyaml \
    || die "Dependency installation failed (network?). On NixOS use: nix run .#cavemen"
  log "Step 2/3 OK - venv created with pygame + pyyaml."
fi

# --- Step 3/3: start the simulation --------------------------------------------
log "Step 3/3 - starting simulation with $PYTHON (args: $*)"
exec "$PYTHON" -m cavemen "$@"
