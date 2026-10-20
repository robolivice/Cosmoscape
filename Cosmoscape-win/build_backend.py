import os
import subprocess
import sys

sep = os.pathsep
cmd = [
    sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir",
    "--name", "cosmoscape-backend",
    "--paths", os.path.join("..", "Cosmoscape-FS"),
    "--add-data", os.path.join("..", "Cosmoscape-FS", "frontend") + sep + "frontend",
    "--add-data", "seed" + sep + "seed",
    "--collect-submodules", "uvicorn",
]
for mod in ("numpy", "astropy", "astroquery", "pandas", "scipy", "matplotlib", "tkinter"):
    cmd.append("--exclude-module")
    cmd.append(mod)
for mod in ("cosmoscape_fs", "cosmoscape_fs.app", "cosmoscape_fs.ingest", "cosmoscape_fs.desktop"):
    cmd.append("--hidden-import")
    cmd.append(mod)
cmd.append("main.py")
subprocess.check_call(cmd)
