import os
import subprocess
import sys

sep = os.pathsep
cmd = [
    sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir",
    "--name", "cosmoscape-backend",
    "--add-data", os.path.join("..", "frontend") + sep + "frontend",
    "--add-data", "seed" + sep + "seed",
    "--collect-submodules", "uvicorn",
]
for mod in ("numpy", "astropy", "astroquery", "pandas", "scipy", "matplotlib", "tkinter"):
    cmd.append("--exclude-module")
    cmd.append(mod)
cmd.append("main.py")
subprocess.check_call(cmd)