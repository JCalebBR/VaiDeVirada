#!/usr/bin/env bash
# Push the current data/extension-analysis.json to origin/main without touching the
# working tree, the index or the local branch: the commit is built on a scratch index.
set -euo pipefail

repo=$(cd "$(dirname "$0")/.." && pwd)
file=data/extension-analysis.json
cd "$repo"

python3 -I -c 'import json, sys; json.load(open(sys.argv[1]))' "$file"

for attempt in 1 2 3; do
  git fetch --quiet origin main
  base=$(git rev-parse origin/main)
  index=$(mktemp)
  trap 'rm -f "$index"' EXIT
  GIT_INDEX_FILE=$index git read-tree "$base"
  blob=$(git hash-object -w "$file")
  GIT_INDEX_FILE=$index git update-index --add --cacheinfo "100644,$blob,$file"
  tree=$(GIT_INDEX_FILE=$index git write-tree)
  rm -f "$index"
  if [ "$tree" = "$(git rev-parse "$base^{tree}")" ]; then
    echo "unchanged"
    exit 0
  fi
  commit=$(git commit-tree "$tree" -p "$base" -m 'data: update urn log collection snapshot')
  # The Pages workflow also pushes to main; a rejected push means it got there first.
  if git push --quiet origin "$commit:refs/heads/main"; then
    echo "pushed $commit"
    break
  fi
  if [ "$attempt" = 3 ]; then
    echo "push rejected 3 times" >&2
    exit 1
  fi
  sleep $((attempt * 10))
done

state=$(python3 -I -c 'import json, sys; print(json.load(open(sys.argv[1]))["progress"]["state"])' "$file")
if [ "$state" = complete ] && command -v systemctl >/dev/null; then
  systemctl --user disable --now vaidevirada-publish.timer || true
fi
