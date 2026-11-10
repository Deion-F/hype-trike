#!/usr/bin/env bash
# Build the browser version into hypetrike/build/web (static site).
set -euo pipefail
cd "$(dirname "$0")/.."
.venv/bin/python -m pygbag --build --title "Hype Trike" --ume_block 0 hypetrike
# Home-screen install: full screen, landscape (Android Chrome).
W=hypetrike/build/web
cat > "$W/manifest.json" <<'JSON'
{"name": "Hype Trike", "short_name": "Hype Trike", "start_url": "./index.html",
 "display": "fullscreen", "orientation": "landscape",
 "background_color": "#18142a", "theme_color": "#18142a",
 "icons": [{"src": "favicon.png", "sizes": "192x192", "type": "image/png"}]}
JSON
if ! grep -q 'rel="manifest"' "$W/index.html"; then
  sed -i '0,/<head>/s//<head>\n<link rel="manifest" href="manifest.json">\n<meta name="mobile-web-app-capable" content="yes">\n<meta name="screen-orientation" content="landscape">/' "$W/index.html"
fi
# Right mouse button is turbo: don't let the browser's context menu steal it.
if ! grep -q 'contextmenu' "$W/index.html"; then
  sed -i '0,/<head>/s//<head>\n<script>document.addEventListener("contextmenu", e => e.preventDefault());<\/script>/' "$W/index.html"
fi
echo "Built: $(pwd)/hypetrike/build/web"
