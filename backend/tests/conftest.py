from __future__ import annotations

import os
import sys
from pathlib import Path


os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))