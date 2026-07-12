from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

APP_ROOT = Path.cwd() / ".VocaVid"


@dataclass
class JobOptions:
    autodelete_finished: bool = False
    shutdown_after_queue: bool = False
