"""
Thin wrapper around the shared catalog loader.

The real implementation lives in `Cosmoscape-FS/cosmoscape_fs/ingest.py` at the
repository root, so there is only one copy of it. This file keeps the old
commands working:

    python ingest.py --all
    python ingest.py --curated --galaxies
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FS_DIR = os.path.join(ROOT, "Cosmoscape-FS")
if not getattr(sys, "frozen", False) and FS_DIR not in sys.path:
    sys.path.insert(0, FS_DIR)

from cosmoscape_fs.ingest import *  # noqa: F401,F403,E402  (keeps `import ingest` working)
from cosmoscape_fs.ingest import main  # noqa: E402

if __name__ == "__main__":
    main()
