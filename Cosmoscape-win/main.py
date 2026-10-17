import os, math, sys
import gzip
import shutil
import hashlib
import threading
import sqlite3
import urllib.request
from contextlib import asynccontextmanager, closing
from fastapi import FastAPI, HTTPException
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import ingest

DB_NAME = ingest.DB_NAME
MARKDOWN_DIR = ingest.MARKDOWN_DIR

# Where the prebuilt database is hosted (see package_db.py, step 4b)
DB_URL = "https://YOUR-HOST/universe.db.gz"
DB_SHA256 = ""   # paste the hash printed by package_db.py, "" skips the check


def open_db():
    return closing(sqlite3.connect(DB_NAME))

def install_seed():
    seed = ingest.resource_path(os.path.join("seed", "universe.db"))
    if not os.path.exists(seed):
        print("seed database not found:", seed)
        return
    need = True
    if os.path.exists(DB_NAME):
        a = None
        b = None
        try:
            a = sqlite3.connect(DB_NAME)
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
            if os.path.exists(DB_NAME + suffix):
                os.remove(DB_NAME + suffix)
        shutil.copyfile(seed, DB_NAME)
        print("seed database installed")


def install_seed_notes():
    src_dir = ingest.resource_path(os.path.join("seed", "database"))
    if not os.path.isdir(src_dir):
        return
    os.makedirs(MARKDOWN_DIR, exist_ok=True)
    for fname in os.listdir(src_dir):
        if not fname.endswith(".md"):
            continue
        dst = os.path.join(MARKDOWN_DIR, fname)
        copy_it = False
        if not os.path.exists(dst):
            copy_it = True
        else:
            with open(dst, "r", encoding="utf-8") as f:
                if "Stellar Objective" in f.read():
                    copy_it = True
        if copy_it:
            shutil.copyfile(os.path.join(src_dir, fname), dst)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        install_seed()
        install_seed_notes()
    except Exception as e:
        print("seed install failed:", type(e).__name__, e)
    conn = ingest.connect()
    ingest.init_schema(conn)
    if conn.execute("SELECT COUNT(*) FROM stars").fetchone()[0] == 0:
        ingest.seed_curated(conn)
    conn.close()
    yield

app = FastAPI(lifespan=lifespan)

app.add_middleware(GZipMiddleware, minimum_size=1000)

import_state = {"status": "idle", "progress": 0, "message": ""}
import_lock = threading.Lock()


def set_import(status, progress, message):
    import_state["status"] = status
    import_state["progress"] = progress
    import_state["message"] = message


def run_import():
    part = DB_NAME + ".part"
    new = DB_NAME + ".new"
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
        for suffix in ("-wal", "-shm"):
            if os.path.exists(DB_NAME + suffix):
                os.remove(DB_NAME + suffix)
        os.replace(new, DB_NAME)
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


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/status")
def api_status():
    count = 0
    with open_db() as conn:
        count = conn.execute("SELECT COUNT(*) FROM stars").fetchone()[0]
    return {"stars": count}


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

def to_scene(x, y, z):
    gx, gy, gz = x, z, -y
    r = math.sqrt(gx*gx + gy*gy + gz*gz)
    if r == 0:
        return 0.0, 0.0, 0.0
    if r <= 100:
        k = 15.0
    else:
        k = (1500.0 + 300.0 * math.log10(r / 100.0)) / r
    return gx * k, gy * k, gz * k

GALAXY_FAR_BASE = 5500.0

def galaxy_scene_pos(name, info, c):
    sx, sy, sz = c[0], c[2], -c[1]
    if name == "Milky_Way":
        s = info["display"] / (2.0 * info["radius_ly"])
        return sx * s, sy * s, sz * s
    r = math.sqrt(sx * sx + sy * sy + sz * sz)
    d = GALAXY_FAR_BASE + 600.0 * math.log10(max(r, 1.0) / 100000.0)
    return sx / r * d, sy / r * d, sz / r * d
@app.get("/galaxies/")
def get_galaxies():
    out = []
    with open_db() as conn:
        for name, info in ingest.GALAXY_INFO.items():
            c = ingest.galaxy_center(conn, name)
            if not c:
                continue
            sx, sy, sz = galaxy_scene_pos(name, info, c)
            count = conn.execute("SELECT COUNT(*) FROM stars WHERE galaxy = ? AND kind = 'star'", (name,)).fetchone()[0]
            out.append({
                "name": name, "x": sx, "y": sy, "z": sz,
                "radius_ly": info["radius_ly"], "display": info["display"],
                "tilt": info["tilt"], "texture": info.get("texture"), "count": count,
            })
    return out
MW_Z_SQUASH = 0.15
MW_REAL_COVERAGE_LY = 10000.0
@app.get("/galaxy/{name}/stars")
def get_galaxy_stars(name: str, limit: int = 40001):
    info = ingest.GALAXY_INFO.get(name)
    if not info:
        raise HTTPException(status_code=404, detail="Unknown galaxy")
    scale = info["display"] / (2.0 * info["radius_ly"])
    cols = "name, x, y, z, mag, teff, curated"
    with open_db() as conn:
        c = ingest.galaxy_center(conn, name)
        if not c:
            raise HTTPException(status_code=404, detail="Galaxy not in database")
        synth_sql = f"SELECT {cols} FROM stars WHERE galaxy = ? AND kind = 'star' AND source = 'synthetic'"
        synth_args = [name]
        if name == "Milky_Way":
            synth_sql += " AND 0"
        rows = conn.execute(synth_sql, synth_args).fetchall()
        rows += conn.execute(
            f"SELECT {cols} FROM stars WHERE galaxy = ? AND kind = 'star' AND source != 'synthetic' AND (curated >= 1 OR has_planets = 1)",
            (name,)).fetchall()
        room = max(limit - len(rows), 0)
        if room:
            rows += conn.execute(
                f"SELECT {cols} FROM stars WHERE galaxy = ? AND kind = 'star' AND source != 'synthetic' AND curated = 0 AND has_planets = 0 "
                "ORDER BY rnd LIMIT ?", (name, room)).fetchall()
    squash = MW_Z_SQUASH if name == "Milky_Way" else 1.0
    stars = []
    for n, x, y, z, mag, teff, cur in rows:
        lx, ly, lz = (x - c[0]) * scale, (y - c[1]) * scale, (z - c[2]) * scale
        stars.append({"name": n, "x": lx, "y": lz * squash, "z": -ly, "mag": mag, "teff": teff, "cur": cur})
    return stars

@app.get("/search/")
def search_stars(q: str, limit: int = 8):
    q = q.strip()
    if len(q) < 2:
        return []
    pat = "%" + q.replace(" ", "_") + "%"
    info = ingest.GALAXY_INFO["Milky_Way"]
    scale = info["display"] / (2.0 * info["radius_ly"])
    c = info["center"]
    with open_db() as conn:
        rows = conn.execute(
            "SELECT s.name, s.x, s.y, s.z, s.mag, s.teff, s.curated FROM stars s "
            "LEFT JOIN aliases a ON a.star_id = s.id "
            "WHERE s.kind = 'star' AND s.galaxy = 'Milky_Way' AND s.source != 'synthetic' "
            "AND (s.name LIKE ? OR a.alias LIKE ?) "
            "GROUP BY s.id ORDER BY (s.curated = 0), s.curated, s.mag LIMIT ?",
            (pat, pat, limit)).fetchall()
    return [{"name": n, "x": (x - c[0]) * scale, "y": (z - c[2]) * scale * MW_Z_SQUASH,
             "z": -(y - c[1]) * scale, "mag": mag, "teff": teff, "cur": cur}
            for n, x, y, z, mag, teff, cur in rows]

@app.get("/objects/")
def get_objects(limit: int = 300):
    with open_db() as conn:
        rows = conn.execute(
            "SELECT name, x, y, z FROM stars "
            "WHERE kind != 'galaxy' AND source != 'synthetic' AND (curated >= 1 OR dist_ly < 50) "
            "ORDER BY curated DESC, dist_ly LIMIT ?", (limit,)
        ).fetchall()
    out = []
    for name, x, y, z in rows:
        sx, sy, sz = to_scene(x, y, z)
        out.append({"name": name, "x": sx, "y": sy, "z": sz})
    return out

@app.get("/api/info/{celestial_body}")
def get_celestial_markdown(celestial_body: str):
    clean_name = "".join(c if c.isalnum() else "_" for c in celestial_body.lower()).strip("_")
    filename = f"{clean_name}.md"
    filepath = os.path.join(MARKDOWN_DIR, filename)
    
    if not os.path.exists(filepath):
        default_template = f"# {celestial_body}\n\nType: Stellar Objective\n\n*Edit `{filename}` to add records.*"
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(default_template)
        
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    return {"name": celestial_body, "content": content}

@app.get("/planets/")
def get_planets():
    out = {}
    with open_db() as conn:
        for star, pname, per, sma, rade in conn.execute(
                "SELECT s.name, p.name, p.period_d, p.sma_au, p.rade FROM planets p JOIN stars s ON s.id = p.star_id"):
            out.setdefault(star, []).append({"name": pname, "period": per, "sma": sma, "rade": rade})
    return out

class MarkdownUpdate(BaseModel):
    content: str

@app.put("/api/info/{celestial_body}")
def save_celestial_markdown(celestial_body: str, update: MarkdownUpdate):
    clean_name = "".join(c if c.isalnum() else "_" for c in celestial_body.lower()).strip("_")
    filepath = os.path.join(MARKDOWN_DIR, f"{clean_name}.md")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(update.content)
    return {"status": "saved", "file": f"{clean_name}.md"}

if getattr(sys, "frozen", False):
    FRONTEND_DIR = ingest.resource_path("frontend")
else:
    FRONTEND_DIR = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")

if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/")
    def read_index():
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

if __name__ == "__main__":
    import argparse
    import uvicorn
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning", log_config=None)
