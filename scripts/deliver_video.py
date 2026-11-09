#!/usr/bin/env python3
"""Register a reviewed ChatCut or Remotion final; preserves the legacy entry point."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.deliver_chatcut import main

if __name__ == '__main__':
    main()
