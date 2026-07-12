from __future__ import annotations

from html import escape

from .scripts import SCRIPTS
from .styles import STYLES


def _text(value) -> str:
    return escape(str(value), quote=False)


def _page(title: str, body: str, queue_count: int = 0) -> str:
    browser_title = _browser_title(title, queue_count)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_text(browser_title)}</title>
  <link rel="icon" type="image/x-icon" href="/icon/favicon.ico">
  <style>
{STYLES}
  </style>
  <script>
{SCRIPTS}
  </script>
</head>
<body><main>{body}</main></body>
</html>"""


def _browser_title(title: str, queue_count: int = 0) -> str:
    count = max(0, int(queue_count or 0))
    return f"({count}) {title}" if count else title

__all__ = ["_page", "_browser_title"]
