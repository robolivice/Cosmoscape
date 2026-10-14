import os, math
import sys
import sqlite3
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
import numpy as np
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)
import ingest

DB_NAME = ingest.DB_NAME
MARKDOWN_DIR = ingest.MARKDOWN_DIR

@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = ingest.connect()
    ingest.init_schema(conn)
    if conn.execute("SELECT COUNT(*) FROM stars").fetchone()[0] == 0:
        ingest.seed_curated(conn)
    conn.close()
    yield

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8000", "http://localhost:8000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/sync-real-data/")
def sync_data():
    conn = ingest.connect()
    ingest.init_schema(conn)
    added = ingest.seed_curated(conn)
    conn.close()
    return {"status": "success", "added": added}

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
    with sqlite3.connect(DB_NAME) as conn:
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
def get_galaxy_stars(name: str, limit: int = 40000):
    info = ingest.GALAXY_INFO.get(name)
    if not info:
        raise HTTPException(status_code=404, detail="Unknown galaxy")
    scale = info["display"] / (2.0 * info["radius_ly"])
    cols = "name, x, y, z, mag, teff, curated"
    with sqlite3.connect(DB_NAME) as conn:
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
                "ORDER BY RANDOM() LIMIT ?", (name, room)).fetchall()
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
    with sqlite3.connect(DB_NAME) as conn:
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
    with sqlite3.connect(DB_NAME) as conn:
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
    with sqlite3.connect(DB_NAME) as conn:
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

FRONTEND_DIR = os.path.join(CURRENT_DIR, "frontend")
if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
    @app.get("/")
    def read_index():
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

if __name__ == "__main__":
    import uvicorn
    os.chdir(CURRENT_DIR)
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
