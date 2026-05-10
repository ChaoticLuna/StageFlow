#!/usr/bin/env python3
"""Re-enable StageFlow hooks (convenience wrapper around hooks_off.py --on).

Usage:
    python scripts/hooks_on.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hooks_off import enable_hooks, show_status

if __name__ == "__main__":
    enable_hooks()
    show_status()
