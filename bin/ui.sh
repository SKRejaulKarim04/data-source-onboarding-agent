#!/usr/bin/env bash
# Front-end tasks: install, build, dev server.
#
# Usage: bin/ui.sh [install|build|dev|ensure]
#
#   ensure  build only if dist/ is missing — what serve.sh calls, so the first
#           `npm run serve` on a fresh clone still shows the React UI.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

UI_DIR="$ROOT_DIR/frontend"
DIST="$UI_DIR/dist/index.html"

require_node() {
  if ! command -v npm >/dev/null 2>&1; then
    echo "npm not found. Install Node.js 18+ to build the React front end." >&2
    return 1
  fi
}

ui_install() {
  require_node
  npm --prefix "$UI_DIR" install
}

ui_build() {
  require_node
  [[ -d "$UI_DIR/node_modules" ]] || ui_install
  npm --prefix "$UI_DIR" run build
}

case "${1:-build}" in
  install) ui_install ;;
  build)   ui_build ;;
  dev)
    require_node
    [[ -d "$UI_DIR/node_modules" ]] || ui_install
    npm --prefix "$UI_DIR" run dev
    ;;
  ensure)
    if [[ -f "$DIST" ]]; then
      echo "Front end already built: frontend/dist"
    elif require_node 2>/dev/null; then
      echo "Building the React front end…"
      ui_build
    else
      echo "No React build and no npm — serving the fallback UI." >&2
    fi
    ;;
  *)
    echo "Usage: bin/ui.sh [install|build|dev|ensure]" >&2
    exit 2
    ;;
esac
