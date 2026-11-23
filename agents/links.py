"""Add one-tap X links (pre-filled reply, like, follow) to an engagement-queue body, in place.

    python -m agents.links /tmp/queue.md
"""
import sys
from pathlib import Path

from agents.run import add_x_links, drop_preamble

if __name__ == "__main__":
    for name in sys.argv[1:]:
        p = Path(name)
        p.write_text(add_x_links(drop_preamble(p.read_text(encoding="utf-8"))) + "\n", encoding="utf-8")
