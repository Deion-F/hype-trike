#!/usr/bin/env bash
# Build, then serve the web build to phones on your Wi-Fi (port 8000).
# The phone needs internet: the Python/pygame runtime loads from the pygbag CDN.
set -euo pipefail
cd "$(dirname "$0")/.."
PORT="${PORT:-8000}"
tools/build_web.sh >/dev/null
WSL_IP="$(hostname -I | awk '{print $1}')"
cat <<MSG

== Hype Trike phone server ==
Serving hypetrike/build/web on port $PORT  (Ctrl+C to stop)

If you're on WSL2 (default NAT networking), run this ONCE in an *admin* PowerShell on Windows:

  netsh interface portproxy add v4tov4 listenport=$PORT listenaddress=0.0.0.0 connectport=$PORT connectaddress=$WSL_IP
  New-NetFirewallRule -DisplayName "Hype Trike $PORT" -Direction Inbound -LocalPort $PORT -Protocol TCP -Action Allow

(The WSL IP can change after a reboot; re-run the netsh line with the new IP if the phone stops connecting.
 To undo:  netsh interface portproxy delete v4tov4 listenport=$PORT listenaddress=0.0.0.0
           Remove-NetFirewallRule -DisplayName "Hype Trike $PORT")

Then on your phone (same Wi-Fi) open:   http://<your Windows PC's Wi-Fi IP>:$PORT/
  Find that IP in Windows with:  ipconfig   (look for "Wireless LAN adapter Wi-Fi" -> IPv4 Address)

Tip: in Chrome on Android, use  menu > Add to Home screen  for a full-screen landscape launch.
MSG
cd hypetrike/build/web
exec python3 -m http.server "$PORT" --bind 0.0.0.0
