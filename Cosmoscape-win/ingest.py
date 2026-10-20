import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FS_DIR = os.path.join(ROOT, "Cosmoscape-FS")
if not getattr(sys, "frozen", False) and FS_DIR not in sys.path:
    sys.path.insert(0, FS_DIR)

from cosmoscape_fs.ingest import *
from cosmoscape_fs.ingest import main

if __name__ == "__main__":
    main()
