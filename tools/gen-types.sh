#!/usr/bin/env bash
# The typed web API client, generated from the FastAPI OpenAPI contract. Contributed by the hidden
# `fastapi-tanstack-start` capability and driven by NX:
# `bunx nx run fastapi-tanstack-start:gen-types` -> `bash tools/gen-types.sh`,
# `fastapi-tanstack-start:gen-types-check` -> `bash tools/gen-types.sh --check`.
#
# `generate` dumps apps/api/openapi.json from the app's routes and regenerates apps/web/src/api/generated.
#
# `--check` is the drift gate: it regenerates both into a scratch copy of the `apps/` layout and fails
# if either differs from what is on disk. It compares against the working tree, not the git index, so
# a correct regeneration that is not staged yet passes locally; CI checks out a clean tree, where the
# two are the same thing. It writes nothing while they match: `bun run check` type-checks the web app
# in parallel, and hey-api empties its output folder before writing it, so regenerating the live client
# made that type-check see it missing. On drift the regenerated files replace the stale ones, so a
# stale client is fixed by the run that reports it.
#
# The scaffold ships no client: it depends on which API capabilities the app selected, and a client
# generated for every capability of the registry made each one that adds a route edit this
# capability. `bun run install-all` runs this script, and the result is the app's to commit. A missing
# client is drift like a stale one, so `--check` generates it and fails.
set -euo pipefail

ROOT="$PWD"
SPEC="apps/api/openapi.json"
CLIENT="apps/web/src/api/generated"

# Its binary is called by path, under node like `bunx` runs it, because `bunx` from a scratch
# directory would download it instead.
OPENAPI_TS="$ROOT/node_modules/.bin/openapi-ts"

# Writes the spec and the client under $1, which is `apps` or a scratch copy of its layout. hey-api
# resolves the config's input, output and `runtimeConfigPath` from the working directory, so running
# it from $1/web generates the same files, relative imports included, wherever $1 is.
generate() {
  local apps="$1"
  if [ ! -x "$OPENAPI_TS" ]; then
    echo "gen-types.sh: $OPENAPI_TS is missing; run \`bun install\` first" >&2
    exit 1
  fi
  mkdir -p "$apps/api" "$apps/web"
  bash tools/uv.sh run --no-sync gen-openapi "$apps/api/openapi.json"
  (cd "$apps/web" && "$OPENAPI_TS" -f "$ROOT/apps/web/openapi-ts.config.ts")
}

# Swaps in the client at $1: staged next to the live one (a dot folder, which the web type-check's
# globs skip) so the live one is missing only between `rm` and `mv`.
replace_client() {
  local staged
  staged="$(dirname "$CLIENT")/.generated.new"
  rm -rf "$staged"
  cp -R "$1" "$staged"
  rm -rf "$CLIENT"
  mv "$staged" "$CLIENT"
}

# The spec and the client are compared and replaced separately: replacing the client briefly removes
# it, so only a client that drifted is replaced.
check() {
  local drift=0 scratch
  scratch="$(mktemp -d)"
  # shellcheck disable=SC2064 # expand now: $scratch is local to this function
  trap "rm -rf '$scratch'" EXIT
  generate "$scratch/apps"
  local spec="$scratch/$SPEC" client="$scratch/$CLIENT"

  if [ ! -d "$CLIENT" ]; then
    echo "$CLIENT is missing" >"$scratch/diff"
    replace_client "$client"
    drift=1
  elif ! diff -ru "$CLIENT" "$client" >"$scratch/diff"; then
    replace_client "$client"
    drift=1
  fi
  # A spec that was never written has nothing to drift from; the client is the contract.
  if [ -f "$SPEC" ] && ! diff -u "$SPEC" "$spec" >>"$scratch/diff"; then
    drift=1
  fi
  cmp -s "$spec" "$SPEC" || cp "$spec" "$SPEC"
  if [ "$drift" = 1 ]; then
    head -n 60 "$scratch/diff"
    echo "The API spec or the generated client did not match the API's routes (first 60 diff lines above)." >&2
    echo "They have been regenerated in place; review the change and commit it:" >&2
    echo "  git add $SPEC $CLIENT" >&2
    exit 1
  fi
  echo "[check] generated API client matches the API"
}

case "${1:-}" in
  "") generate apps ;;
  --check) check ;;
  *)
    echo "usage: gen-types.sh [--check]" >&2
    exit 2
    ;;
esac
