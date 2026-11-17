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
# Leaving the page (browser Back, tab switch, phone lock) freezes the Python loop, and
# the browser then repeats its last audio buffer: a stuck screech. Suspend the audio
# while the page is hidden and resume it on return.
if ! grep -q 'hype-audio-guard' "$W/index.html"; then
  sed -i '0,/<head>/s//<head>\n<script id="hype-audio-guard">(() => {\n  const ctx = () => (window.Module \&\& Module.SDL2 \&\& Module.SDL2.audioContext) || null;\n  const set = (on) => { const a = ctx(); if (a) (on ? a.resume() : a.suspend()).catch(() => {}); };\n  document.addEventListener("visibilitychange", () => set(!document.hidden));\n  window.addEventListener("pagehide", () => set(false));\n  window.addEventListener("pageshow", () => set(!document.hidden));\n})();<\/script>/' "$W/index.html"
fi
echo "Built: $(pwd)/hypetrike/build/web"
