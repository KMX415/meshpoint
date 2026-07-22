"""Cache-busting for the dashboard's static JS/CSS asset URLs.

After a dashboard self-update, browsers can keep executing stale cached
JS against freshly deployed HTML. Features then fail silently until a
hard reload.

The ``/`` (and auth page) routes rewrite every local ``.js``/``.css`` URL
to carry a ``?v=<token>`` query. The token is minted once per process;
every Apply ends in a service restart, so each deploy serves new asset
URLs. External URLs (http/https/protocol-relative) are left untouched.

Free of FastAPI imports so the rewrite logic unit-tests without the
full app stack.

Credit: javastraat/meshpoint ``52b6caf``.
"""

from __future__ import annotations

import re
import time

# Per-process token: hex timestamp, minted at import (= service start).
BOOT_TOKEN = f"{int(time.time()):x}"

# src="..." / href="..." values ending in .js or .css, skipping
# external URLs (http://, https://, //cdn...). Matches relative
# ("js/app.js") and root-relative ("/vendor/xterm/xterm.js") paths.
_ASSET_URL_RE = re.compile(
    r'((?:src|href)=")(?!https?://|//)([^"?]+\.(?:js|css))(")'
)


def bust_asset_urls(html: str, token: str = BOOT_TOKEN) -> str:
    """Append ``?v=<token>`` to every local JS/CSS asset URL in *html*."""
    return _ASSET_URL_RE.sub(rf"\g<1>\g<2>?v={token}\g<3>", html)
