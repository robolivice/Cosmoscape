"""
desktop.py - the parts that only the desktop build needs.

The web build has no installer and no download host, so it keeps the import
routes as "not implemented". The desktop build copies a bundled seed database
into the user data folder on first launch and can download a newer catalogue.
"""
import gzip
import hashlib
import os
import shutil
import sqlite3
import sys
import threading
import urllib.request

from . import ingest

# Where the prebuilt database is hosted (see package_db.py, step 4b).
DB_URL = os.environ.get("COSMOSCAPE_DB_URL", "https://YOUR-HOST/universe.db.gz")
DB_SHA256 = os.environ.get("COSMOSCAPE_DB_SHA256", "")   # "" skips the check


def seed_dir():
    """Folder with the bundled seed database and notes."""
    if getattr(sys, "frozen", False):
        return ingest.resource_path("seed")
    return os.path.join(ingest.REPO_ROOT, "Cosmoscape-win", "seed")


def _paths():
    """The database and notes folder the running application uses."""
    from . import app as app_module
    return app_module.DB_NAME, app_module.MARKDOWN_DIR


def install_seed():
    """Copy the bundled database into the user data folder on first launch."""
    seed = os.path.join(seed_dir(), "universe.db")
    if not os.path.exists(seed):
        print("seed database not found:", seed)
        return
    db_name, _ = _paths()
    need = True
    if os.path.exists(db_name):
        a = None
        b = None
        try:
            a = sqlite3.connect(db_name)
            b = sqlite3.connect(seed)
            have = a.execute("SELECT COUNT(*) FROM stars").fetchone()[0]
            want = b.execute("SELECT COUNT(*) FROM stars").fetchone()[0]
            if have >= want:
                need = False
        except Exception:
            need = True
        finally:
            if a is not None:
                a.close()
            if b is not None:
                b.close()
    if need:
        for suffix in ("-wal", "-shm"):
            if os.path.exists(db_name + suffix):
                os.remove(db_name + suffix)
        shutil.copyfile(seed, db_name)
        print("seed database installed")


def install_seed_notes():
    """Copy the bundled notes into the user data folder."""
    src_dir = os.path.join(seed_dir(), "database")
    if not os.path.isdir(src_dir):
        return
    _, markdown_dir = _paths()
    os.makedirs(markdown_dir, exist_ok=True)
    for fname in os.listdir(src_dir):
        if not fname.endswith(".md"):
            continue
        dst = os.path.join(markdown_dir, fname)
        copy_it = False
        if not os.path.exists(dst):
            copy_it = True
        else:
            with open(dst, "r", encoding="utf-8") as f:
                if "Stellar Objective" in f.read():
                    copy_it = True
        if copy_it:
            shutil.copyfile(os.path.join(src_dir, fname), dst)


import_state = {"status": "idle", "progress": 0, "message": ""}
import_lock = threading.Lock()


def set_import(status, progress, message):
    import_state["status"] = status
    import_state["progress"] = progress
    import_state["message"] = message


def run_import():
    from . import app as app_module

    db_name = app_module.DB_NAME
    part = db_name + ".part"
    new = db_name + ".new"
    try:
        set_import("running", 0, "Downloading")
        req = urllib.request.Request(DB_URL, headers=ingest.UA)
        resp = urllib.request.urlopen(req, timeout=60)
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        sha = hashlib.sha256()
        with open(part, "wb") as out:
            while True:
                chunk = resp.read(262144)
                if not chunk:
                    break
                out.write(chunk)
                sha.update(chunk)
                done = done + len(chunk)
                if total > 0:
                    set_import("running", int(done * 90 / total), "Downloading")
        resp.close()

        if DB_SHA256 != "":
            if sha.hexdigest() != DB_SHA256:
                raise Exception("Checksum mismatch, download corrupted")

        set_import("running", 92, "Unpacking")
        with gzip.open(part, "rb") as src:
            with open(new, "wb") as dst:
                shutil.copyfileobj(src, dst)

        check = sqlite3.connect(new)
        try:
            n = check.execute("SELECT COUNT(*) FROM stars").fetchone()[0]
        finally:
            check.close()
        if n == 0:
            raise Exception("Downloaded database is empty")

        set_import("running", 97, "Installing")
        # The server keeps read connections open, and Windows refuses to replace
        # a file that is still open.
        app_module.close_db_connections()
        for suffix in ("-wal", "-shm"):
            if os.path.exists(db_name + suffix):
                os.remove(db_name + suffix)
        os.replace(new, db_name)
        app_module.refresh_after_db_swap()
        set_import("done", 100, "Import complete")
    except Exception as e:
        print("import failed:", type(e).__name__, e)
        set_import("error", 0, type(e).__name__ + ": " + str(e))
    finally:
        for p in (part, new):
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass


def register_routes(app):
    @app.post("/api/import-data")
    def import_data():
        with import_lock:
            if import_state["status"] == "running":
                return import_state
            set_import("running", 0, "Starting")
        threading.Thread(target=run_import, daemon=True).start()
        return import_state

    @app.get("/api/import-status")
    def import_status():
        return import_state
