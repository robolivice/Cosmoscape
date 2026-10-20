import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
FS = os.path.join(REPO, "Cosmoscape-FS")

sep = os.pathsep
cmd = [
    sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir",
    "--name", "cosmoscape-backend",
    "--paths", FS,
    "--add-data", os.path.join(FS, "frontend") + sep + "frontend",
    "--add-data", os.path.join(HERE, "seed") + sep + "seed",
    "--collect-submodules", "uvicorn",
]
for mod in ("numpy", "astropy", "astroquery", "pandas", "scipy", "matplotlib", "tkinter"):
    cmd.append("--exclude-module")
    cmd.append(mod)
for mod in ("cosmoscape_fs", "cosmoscape_fs.app", "cosmoscape_fs.ingest", "cosmoscape_fs.desktop"):
    cmd.append("--hidden-import")
    cmd.append(mod)
cmd.append(os.path.join(HERE, "main.py"))


subprocess.check_call(cmd, cwd=HERE)
