#!/bin/zsh
set -e
workspace_root="${0:A:h}"
cd "$workspace_root"
workspace_python="$workspace_root/Saved/Training/v1/python/bin/python"
if [[ ! -x "$workspace_python" ]]; then
  print 'PlayableSketch could not find its local Python environment.'
  exit 1
fi
workspace_port="${PLAYABLESKETCH_PORT:-8772}"
exec env OMP_NUM_THREADS=4 PYTHONDONTWRITEBYTECODE=1 "$workspace_python" "$workspace_root/Scripts/start_runtime.py" --workspace-only --service "http://127.0.0.1:${workspace_port}"
