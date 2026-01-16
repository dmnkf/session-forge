#!/usr/bin/env bash
set -euo pipefail

if command -v uv >/dev/null 2>&1; then
  uv tool install session-forge
else
  python3 -m pip install --user --upgrade pip
  python3 -m pip install --user session-forge
  case ":$PATH:" in
    *":$HOME/.local/bin:"*) : ;;
    *) echo 'Add $HOME/.local/bin to PATH to use `sf`:' >&2
       echo '  export PATH="$HOME/.local/bin:$PATH"' >&2 ;;
  esac
fi
