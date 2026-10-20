import argparse
import csv
import glob
import gzip
import io
import json
import math
import os
import re
import sqlite3
import sys
import time
import unicodedata
import urllib.parse
import urllib.request

try:
    import numpy as np
except ImportError:
    np = None
from platformdirs import user_data_dir

APP_NAME = "Cosmoscape"


FS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(FS_DIR)


def get_data_dir():
    d = os.environ.get("COSMOSCAPE_DATA")
    if not d:
        d = user_data_dir(APP_NAME, appauthor=False)
    os.makedirs(d, exist_ok=True)
    return d


def resource_path(rel):
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS
    else:
        base = REPO_ROOT
    return os.path.join(base, rel)


DATA_DIR = get_data_dir()
DB_NAME = os.environ.get("COSMOSCAPE_DB") or os.path.join(DATA_DIR, "universe.db")
MARKDOWN_DIR = os.environ.get("COSMOSCAPE_MARKDOWN") or os.path.join(DATA_DIR, "database")
CACHE_DIR = os.environ.get("COSMOSCAPE_CACHE") or os.path.join(DATA_DIR, "data")
LY_PER_PC = 3.26156
CELL = 0.02
UA = {"User-Agent": "UniverseNavigator/1.0 (personal project)"}


A_G = (
    (-0.0548755604162154, -0.8734370902348850, -0.4838350155487132),
    (+0.4941094278755837, -0.4448296299600112, +0.7469822444972189),
    (-0.8676661490190047, -0.1980763734312015, +0.4559837761750669),
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS stars (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    kind TEXT DEFAULT 'star',          -- star | nebula | cluster | galaxy | blackhole
    ra REAL, dec REAL, dist_ly REAL,
    x REAL, y REAL, z REAL,            -- galactic, light-years
    mag REAL, teff REAL, spect TEXT,
    source TEXT, ext_id TEXT,
    curated INTEGER DEFAULT 0,         -- 1 = hand-picked, 2 = named/landmark from a catalog
    has_planets INTEGER DEFAULT 0,
    galaxy TEXT DEFAULT 'Milky_Way'
);
CREATE INDEX IF NOT EXISTS idx_stars_mag ON stars(mag);
CREATE INDEX IF NOT EXISTS idx_stars_galaxy ON stars(galaxy);
CREATE INDEX IF NOT EXISTS idx_stars_mag ON stars(mag);
CREATE INDEX IF NOT EXISTS idx_stars_curated ON stars(curated);
CREATE INDEX IF NOT EXISTS idx_stars_x ON stars(x);
CREATE INDEX IF NOT EXISTS idx_stars_y ON stars(y);
CREATE INDEX IF NOT EXISTS idx_stars_z ON stars(z);
CREATE TABLE IF NOT EXISTS planets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    star_id INTEGER NOT NULL,
    name TEXT UNIQUE,
    period_d REAL, sma_au REAL, rade REAL
);
CREATE INDEX IF NOT EXISTS idx_planets_star ON planets(star_id);
CREATE TABLE IF NOT EXISTS aliases (alias TEXT COLLATE NOCASE, star_id INTEGER);
CREATE INDEX IF NOT EXISTS idx_alias ON aliases(alias);
"""


CURATED = [
    ("Sol", 0.0, 0.0, 0.0, -26.74, 5772, "G2V", ["Sun"]),
    ("Alpha_Centauri", 219.9021, -60.8340, 4.37, -0.27, 5790, "G2V+K1V", ["Alpha Centauri", "Rigil Kentaurus", "Toliman", "Alpha Cen"]),
    ("Proxima_Centauri", 217.4289, -62.6795, 4.24, 11.13, 3042, "M5.5Ve", ["Proxima Centauri", "Proxima Cen", "Alpha Centauri C"]),
    ("Sirius", 101.2871, -16.7161, 8.60, -1.46, 9940, "A1V", ["Alpha Canis Majoris"]),
    ("Barnards_Star", 269.4521, 4.6934, 5.96, 9.51, 3134, "M4V", ["Barnard's Star"]),
    ("Vega", 279.2347, 38.7837, 25.0, 0.03, 9602, "A0V", ["Alpha Lyrae"]),
    ("Altair", 297.6958, 8.8683, 16.7, 0.76, 7550, "A7V", ["Alpha Aquilae"]),
    ("Wolf_359", 164.1203, 7.0146, 7.86, 13.5, 2800, "M6V", ["Wolf 359"]),
    ("Lalande_21185", 165.8344, 35.9699, 8.31, 7.5, 3600, "M2V", ["Lalande 21185", "Gliese 411"]),
    ("Epsilon_Eridani", 53.2327, -9.4583, 10.5, 3.73, 5084, "K2V", ["Eps Eri"]),
    ("Procyon", 114.8255, 5.2250, 11.46, 0.34, 6530, "F5IV-V", ["Alpha Canis Minoris"]),
    ("Tau_Ceti", 26.0170, -15.9375, 11.9, 3.5, 5344, "G8V", ["Tau Cet"]),
    ("Fomalhaut", 344.4128, -29.6222, 25.1, 1.16, 8590, "A3V", ["Alpha Piscis Austrini"]),
    ("Arcturus", 213.9153, 19.1824, 36.7, -0.05, 4286, "K1.5III", ["Alpha Bootis"]),
    ("Capella", 79.1723, 45.9980, 42.9, 0.08, 4970, "G8III", ["Alpha Aurigae"]),
]


LANDMARKS = [
    ("Betelgeuse", "star", 88.7929, 7.4071, 550, 0.5, 3600, "M1-2Ia-ab", ["Alpha Orionis"], "Betelgeuse"),
    ("Rigel", "star", 78.6345, -8.2016, 860, 0.13, 12100, "B8Ia", ["Beta Orionis"], "Rigel"),
    ("Polaris", "star", 37.9546, 89.2641, 433, 1.98, 6000, "F7Ib", ["North Star", "Alpha Ursae Minoris"], "Polaris"),
    ("Antares", "star", 247.3519, -26.4320, 550, 1.06, 3600, "M1.5Iab", ["Alpha Scorpii"], "Antares"),
    ("Eta_Carinae", "star", 161.2650, -59.6845, 7500, 4.3, 30000, "LBV", ["Eta Car"], "Eta Carinae"),
    ("Cygnus_X-1", "blackhole", 299.5903, 35.2016, 7200, 99, None, "Black hole", ["Cyg X-1"], "Cyg X-1"),
    ("Sagittarius_A_Star", "blackhole", 266.4168, -29.0078, 26700, 99, None, "Supermassive black hole", ["Sgr A*", "Galactic Center"], "Sgr A*"),
    ("Orion_Nebula", "nebula", 83.8221, -5.3911, 1344, 99, None, "HII region", ["M42", "Messier 42", "NGC 1976"], "M 42"),
    ("Crab_Nebula", "nebula", 83.6331, 22.0145, 6500, 99, None, "Supernova remnant", ["M1", "Messier 1"], "M 1"),
    ("Ring_Nebula", "nebula", 283.3962, 33.0286, 2300, 99, None, "Planetary nebula", ["M57", "Messier 57"], "M 57"),
    ("Eagle_Nebula", "nebula", 274.7000, -13.8070, 7000, 99, None, "HII region", ["M16", "Messier 16"], "M 16"),
    ("Helix_Nebula", "nebula", 337.4108, -20.8372, 650, 99, None, "Planetary nebula", ["NGC 7293"], "NGC 7293"),
    ("Pleiades", "cluster", 56.8500, 24.1167, 444, 99, None, "Open cluster", ["M45", "Messier 45", "Seven Sisters"], "M 45"),
    ("Hyades", "cluster", 66.7500, 15.8700, 153, 99, None, "Open cluster", ["Melotte 25"], "Hyades"),
    ("Omega_Centauri", "cluster", 201.6970, -47.4795, 17000, 99, None, "Globular cluster", ["NGC 5139"], "NGC 5139"),
    ("Messier_13", "cluster", 250.4235, 36.4613, 22200, 99, None, "Globular cluster", ["M13", "Hercules Cluster"], "M 13"),
    ("Large_Magellanic_Cloud", "galaxy", 80.8940, -69.7560, 160000, 99, None, "Dwarf galaxy", ["LMC"], "LMC"),
    ("Small_Magellanic_Cloud", "galaxy", 13.1870, -72.8290, 200000, 99, None, "Dwarf galaxy", ["SMC"], "SMC"),
    ("Andromeda_Galaxy", "galaxy", 10.6847, 41.2687, 2537000, 99, None, "Spiral galaxy", ["M31", "Messier 31", "NGC 224"], "M 31"),
    ("Triangulum_Galaxy", "galaxy", 23.4621, 30.6599, 2730000, 99, None, "Spiral galaxy", ["M33", "Messier 33"], "M 33"),
]


GALAXY_INFO = {
    "Milky_Way":              {"radius_ly": 50000,  "display": 6000, "tilt": 0.35, "center": (26700.0, 0.0, 0.0),
                               "texture": "/static/textures/galaxy_top.jpg"},
    "Andromeda_Galaxy":       {"radius_ly": 110000, "display": 4000, "tilt": 0.8, "texture": "/static/textures/Andromeda2.jpg"},
    "Triangulum_Galaxy":      {"radius_ly": 30000,  "display": 900,  "tilt": 0.3},
    "Large_Magellanic_Cloud": {"radius_ly": 14000,  "display": 700,  "tilt": 0.5},
    "Small_Magellanic_Cloud": {"radius_ly": 9000,   "display": 550,  "tilt": 0.2},
}

GALAXY_LAYOUT_GAP = 1.12

def layout_galaxy_scene(entries):
    order = sorted(entries, key=lambda g: (g["name"] != "Milky_Way", -g["display"]))
    placed = []
    for g in order:
        px, py, pz = g["x"], g["y"], g["z"]
        for _ in range(16 * len(entries)):
            moved = False
            for other in placed:
                need = (max(g["display"], 0.0) + max(other["display"], 0.0)) * 0.5 * GALAXY_LAYOUT_GAP
                dx, dy, dz = px - other["x"], py - other["y"], pz - other["z"]
                dist = math.sqrt(dx * dx + dy * dy + dz * dz)
                if dist >= need:
                    continue
                if dist < 1e-6:
                    dx, dy, dz = px, py, pz
                    dist = math.sqrt(dx * dx + dy * dy + dz * dz)
                    if dist < 1e-6:
                        dx, dy, dz, dist = 0.0, 0.0, 1.0, 1.0
                push = (need - dist) / dist
                px += dx * push
                py += dy * push
                pz += dz * push
                moved = True
            if not moved:
                break
        g["x"], g["y"], g["z"] = px, py, pz
        placed.append(g)
    return entries

SPEC_TEFF = {"O": 38000, "B": 18000, "A": 9000, "F": 6800, "G": 5600, "K": 4500, "M": 3200, "L": 2000, "T": 1000}
WIKI_TITLES = {"Sol": "Sun", "Barnards_Star": "Barnard's_Star", "Sagittarius_A_Star": "Sagittarius_A*"}

def to_gal(ra_deg, dec_deg, dist_ly):
    ra = math.radians(ra_deg)
    dec = math.radians(dec_deg)
    e0 = math.cos(dec) * math.cos(ra)
    e1 = math.cos(dec) * math.sin(ra)
    e2 = math.sin(dec)
    out = []
    for row in A_G:
        out.append((row[0] * e0 + row[1] * e1 + row[2] * e2) * dist_ly)
    return out[0], out[1], out[2]


def to_gal_arrays(ra_deg, dec_deg, dist_ly):
    ra, dec = np.radians(ra_deg), np.radians(dec_deg)
    eq = np.vstack([np.cos(dec) * np.cos(ra), np.cos(dec) * np.sin(ra), np.sin(dec)])
    g = np.array(A_G) @ eq
    return g[0] * dist_ly, g[1] * dist_ly, g[2] * dist_ly


def teff_from_bv(bv):
    bv = min(max(bv, -0.4), 2.0)
    return 4600.0 * (1.0 / (0.92 * bv + 1.7) + 1.0 / (0.92 * bv + 0.62))


def teff_from_spect(sp):
    for ch in str(sp or ""):
        if ch in SPEC_TEFF:
            return float(SPEC_TEFF[ch])
    return None


def norm_name(raw):
    s = str(raw).replace("*", " ").replace("NAME", " ")
    s = re.sub(r"[^\w\-\+\.]+", " ", s).strip()
    return "_".join(s.split())


def fnum(v):
    try:
        if v is None or np.ma.is_masked(v):
            return None
        x = float(v)
        return None if math.isnan(x) else x
    except (TypeError, ValueError):
        return None


RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL"}
RESERVED_NAMES |= {f"COM{i}" for i in range(1, 10)}
RESERVED_NAMES |= {f"LPT{i}" for i in range(1, 10)}


def note_stem(name):
    clean = "".join(
        ch if ch.isalnum() else "_"
        for ch in unicodedata.normalize("NFC", str(name)).lower()
    ).strip("_")
    if not clean:
        clean = "unnamed"
    if clean.upper() in RESERVED_NAMES:
        clean = "_" + clean
    return clean


def note_filename(name):
    return f"{note_stem(name)}.md"


def md_path(name):
    return os.path.join(MARKDOWN_DIR, note_filename(name))


def connect():
    conn = sqlite3.connect(DB_NAME)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_schema(conn):
    conn.executescript(SCHEMA)
    try:
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS stars_rt USING rtree(id, minx, maxx, miny, maxy, minz, maxz)")
    except sqlite3.OperationalError as e:
        print("note: SQLite R*Tree not available, using plain indexes instead:", e)
    conn.commit()
    cols = []
    for row in conn.execute("PRAGMA table_info(stars)").fetchall():
        cols.append(row[1])
    if "rnd" not in cols:
        conn.execute("ALTER TABLE stars ADD COLUMN rnd REAL")
    conn.execute("UPDATE stars SET rnd = ((id * 2654435761) % 4294967296) / 4294967296.0 WHERE rnd IS NULL")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_stars_galaxy_rnd ON stars(galaxy, rnd)")
    conn.commit()
    os.makedirs(MARKDOWN_DIR, exist_ok=True)


def rebuild_index(conn):
    try:
        conn.execute("DELETE FROM stars_rt")
        conn.execute("INSERT INTO stars_rt SELECT id, x, x, y, y, z, z FROM stars")
        conn.commit()
    except sqlite3.OperationalError:
        pass


class SkyIndex:

    def __init__(self, conn):
        self.cells = {}
        for sid, ra, dec, d in conn.execute("SELECT id, ra, dec, dist_ly FROM stars WHERE ra IS NOT NULL"):
            self.put(sid, ra, dec, d)

    @staticmethod
    def key(ra, dec):
        return int(ra // CELL), int((dec + 90.0) // CELL)

    def put(self, sid, ra, dec, d):
        self.cells.setdefault(self.key(ra, dec), []).append((sid, ra, dec, d))

    def find(self, ra, dec, dist=None, tol_arcsec=20.0):
        kx, ky = self.key(ra, dec)
        cosd = max(math.cos(math.radians(dec)), 1e-3)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for sid, r2, d2, dist2 in self.cells.get((kx + dx, ky + dy), ()):
                    dra = ((ra - r2 + 180.0) % 360.0 - 180.0) * cosd
                    if math.hypot(dra, dec - d2) * 3600.0 < tol_arcsec:
                        if dist is None or dist2 is None or abs(dist - dist2) / max(dist, dist2, 1e-6) < 0.5:
                            return sid
        return None


def add_alias(conn, sid, alias):
    alias = str(alias or "").strip()
    if alias:
        conn.execute("INSERT INTO aliases (alias, star_id) VALUES (?, ?)", (alias, sid))


def insert_star(conn, idx, name, ra, dec, dist_ly, mag=None, teff=None, spect=None, kind="star",
                source="", ext_id=None, curated=0, aliases=(), rename=False, galaxy="Milky_Way"):
    if not name:
        return None, False
    dup = idx.find(ra, dec, dist_ly if kind == "star" else None)
    if dup is not None:
        if curated == 1:
            conn.execute("UPDATE stars SET curated = 1 WHERE id = ?", (dup,))
            if rename:
                try:
                    conn.execute("UPDATE stars SET name = ? WHERE id = ?", (name, dup))
                except sqlite3.IntegrityError:
                    pass
        elif curated == 2:
            conn.execute("UPDATE stars SET curated = 2 WHERE id = ? AND curated = 0", (dup,))
        for a in aliases:
            add_alias(conn, dup, a)
        return dup, False
    x, y, z = to_gal(ra, dec, dist_ly)
    if mag is None:
        mag = 99.0 if kind != "star" else 15.0
    cur = conn.execute(
        "INSERT OR IGNORE INTO stars (name, kind, ra, dec, dist_ly, x, y, z, mag, teff, spect, source, ext_id, curated, galaxy) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (name, kind, ra, dec, dist_ly, x, y, z, mag, teff, spect, source, ext_id, curated, galaxy))
    if cur.rowcount == 0:
        row = conn.execute("SELECT id FROM stars WHERE name = ?", (name,)).fetchone()
        return (row[0] if row else None), False
    sid = cur.lastrowid
    idx.put(sid, ra, dec, dist_ly)
    for a in aliases:
        add_alias(conn, sid, a)
    return sid, True


def seed_curated(conn):
    idx = SkyIndex(conn)
    n = 0
    for name, ra, dec, dist, mag, teff, spect, aliases in CURATED:
        _, created = insert_star(conn, idx, name, ra, dec, dist, mag, teff, spect, "star", "curated",
                                 curated=1, aliases=aliases, rename=True)
        n += created
    for name, kind, ra, dec, dist, mag, teff, spect, aliases, _q in LANDMARKS:
        _, created = insert_star(conn, idx, name, ra, dec, dist, mag, teff, spect, kind, "curated",
                                 curated=1, aliases=aliases, rename=True,
                                 galaxy=name if kind == "galaxy" else "Milky_Way")
        n += created
    conn.commit()
    rebuild_index(conn)
    return n


def build_markdown(conn, name, extract=None, url=None, title=None):
    row = conn.execute(
        "SELECT id, kind, dist_ly, mag, spect, teff, source FROM stars WHERE name = ? COLLATE NOCASE", (name,)).fetchone()
    lines = [f"# {(title or name).replace('_', ' ')}", ""]
    if row:
        sid, kind, dist, mag, spect, teff, source = row
        facts = [f"**Type:** {kind}"]
        if dist is not None:
            facts.append(f"**Distance:** {dist:,.1f} ly" if dist < 1000 else f"**Distance:** {dist:,.0f} ly")
        if spect:
            facts.append(f"**Spectral type:** {spect}")
        if mag is not None and mag < 14.9:
            facts.append(f"**Apparent magnitude:** {mag:.2f}")
        if teff:
            facts.append(f"**Temperature:** about {teff:,.0f} K")
        lines += [" · ".join(facts), ""]
        planets = conn.execute(
            "SELECT name, period_d, sma_au, rade FROM planets WHERE star_id = ? ORDER BY period_d", (sid,)).fetchall()
        if planets:
            lines += [f"## Known planets ({len(planets)})", ""]
            for pn, per, sma, rad in planets:
                bits = []
                if per:
                    bits.append(f"period {per:,.2f} d")
                if sma:
                    bits.append(f"{sma:.3g} AU")
                if rad:
                    bits.append(f"{rad:.2f} Earth radii")
                lines.append(f"- **{pn}**" + (": " + ", ".join(bits) if bits else ""))
            lines.append("")
    else:
        lines += ["No catalog entry for this object yet.", ""]
    if extract:
        lines += [extract, "", f"*Summary from [Wikipedia]({url}), CC BY-SA 4.0.*", ""]
    lines.append("*Edit this record to add your own notes.*")
    return "\n".join(lines)


def wiki_fill(conn, limit):
    rows = conn.execute(
        "SELECT name FROM stars WHERE curated >= 1 OR has_planets = 1 ORDER BY (curated = 1) DESC, mag LIMIT ?",
        (limit,)).fetchall()
    done = 0
    for (name,) in rows:
        path = md_path(name)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                if "Stellar Objective" not in f.read():
                    continue
        title = WIKI_TITLES.get(name, name)
        url = "https://en.wikipedia.org/api/rest_v1/page/summary/" + urllib.parse.quote(title, safe="_'()*")
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
                data = json.loads(r.read().decode("utf-8"))
        except Exception:
            continue
        if data.get("type") == "disambiguation" or not data.get("extract"):
            continue
        page = data.get("content_urls", {}).get("desktop", {}).get("page", "https://en.wikipedia.org/wiki/" + title)
        with open(path, "w", encoding="utf-8") as f:
            f.write(build_markdown(conn, name, data["extract"], page))
        done += 1
        time.sleep(0.1)
    print(f"wiki: wrote {done} records")


HYG_URLS = [
    "https://raw.githubusercontent.com/astronexus/HYG-Database/main/hyg/CURRENT/hyg_v42.csv",
    "https://raw.githubusercontent.com/astronexus/HYG-Database/main/hyg/CURRENT/hyg_v41.csv",
    "https://raw.githubusercontent.com/astronexus/HYG-Database/main/hyg/CURRENT/hygdata_v3.csv",
]


def find_or_fetch_hyg(path_arg, url_arg):
    if path_arg and path_arg != "auto":
        return path_arg if os.path.exists(path_arg) else None
    patterns = [
        os.path.join(CACHE_DIR, "hyg*.csv"),
        os.path.join(CACHE_DIR, "hyg*.csv.gz"),
        os.path.join(CACHE_DIR, "hygdata*.csv"),
        "data/hyg*.csv", "data/hyg*.csv.gz", "hyg*.csv", "hyg*.csv.gz", "data/hygdata*.csv",
    ]
    for pat in patterns:
        found = sorted(glob.glob(pat))
        if found:
            return found[-1]
    os.makedirs(CACHE_DIR, exist_ok=True)
    for url in ([url_arg] if url_arg else HYG_URLS):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
                blob = r.read()
            if blob[:200].decode("utf-8", "ignore").lstrip().startswith("id,"):
                out = os.path.join(CACHE_DIR, "hyg.csv")
                with open(out, "wb") as f:
                    f.write(blob)
                print("downloaded", url)
                return out
        except Exception as e:
            print("  could not fetch", url, "-", e)
    return None


def ingest_hyg(conn, path):
    idx = SkyIndex(conn)
    opener = gzip.open if path.endswith(".gz") else open
    added = skipped = 0
    with opener(path, "rt", encoding="utf-8", newline="") as f:
        for i, row in enumerate(csv.DictReader(f)):
            dist_pc = fnum(row.get("dist"))
            if not dist_pc or dist_pc <= 0 or dist_pc >= 99999:
                continue
            try:
                ra, dec = math.degrees(float(row["rarad"])), math.degrees(float(row["decrad"]))
            except (KeyError, ValueError):
                ra, dec = float(row["ra"]) * 15.0, float(row["dec"])
            proper, bayer, con = (row.get("proper") or "").strip(), (row.get("bayer") or "").strip(), (row.get("con") or "").strip()
            flam, hip, hd = (row.get("flam") or "").strip(), (row.get("hip") or "").strip(), (row.get("hd") or "").strip()
            hr, gl, comp = (row.get("hr") or "").strip(), (row.get("gl") or "").strip(), (row.get("comp") or "").strip()
            if proper:
                name = norm_name(proper)
            elif bayer and con:
                name = f"{bayer}_{con}"
            elif flam and con:
                name = f"{flam}_{con}"
            elif hd:
                name = f"HD_{hd}"
            elif hip:
                name = f"HIP_{hip}"
            elif gl:
                name = norm_name(gl)
            else:
                name = f"HYG_{row.get('id')}"
            if comp not in ("", "1") and not proper:
                name += f"_{comp}"
            bv, spect = fnum(row.get("ci")), (row.get("spect") or "").strip()
            teff = teff_from_bv(bv) if bv is not None else teff_from_spect(spect)
            aliases = [proper, f"HIP {hip}" if hip else "", f"HD {hd}" if hd else "", f"HR {hr}" if hr else "", gl,
                       f"{bayer} {con}" if bayer and con else ""]
            _, created = insert_star(conn, idx, name, ra, dec, dist_pc * LY_PER_PC, fnum(row.get("mag")), teff,
                                     spect or None, "star", "hyg", row.get("hip") or None,
                                     curated=2 if proper else 0, aliases=aliases)
            added += created
            skipped += not created
            if i % 20000 == 0:
                conn.commit()
    conn.commit()
    print(f"hyg: added {added:,} stars ({skipped:,} duplicates/collisions skipped)")


EXO_URL = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"

def ingest_exoplanets(conn):
    query = ("select hostname,pl_name,pl_orbper,pl_orbsmax,pl_rade,sy_dist,ra,dec,st_teff,st_spectype,sy_vmag "
             "from pscomppars where sy_dist is not null")
    url = EXO_URL + "?" + urllib.parse.urlencode({"query": query, "format": "csv"})
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=180) as r:
        rows = list(csv.DictReader(io.StringIO(r.read().decode("utf-8"))))
    idx = SkyIndex(conn)
    hosts = {}
    for r in rows:
        hosts.setdefault(r["hostname"], []).append(r)
    new_hosts = n_planets = 0
    for host, prs in hosts.items():
        r0 = prs[0]
        ra, dec, dist_pc = fnum(r0["ra"]), fnum(r0["dec"]), fnum(r0["sy_dist"])
        if ra is None or dec is None or not dist_pc:
            continue
        teff = fnum(r0["st_teff"]) or teff_from_spect(r0["st_spectype"])
        sid, created = insert_star(conn, idx, norm_name(host), ra, dec, dist_pc * LY_PER_PC, fnum(r0["sy_vmag"]), teff,
                                   r0["st_spectype"] or None, "star", "nasa_exoplanet_archive", host, aliases=[host])
        if sid is None:
            continue
        new_hosts += created
        conn.execute("UPDATE stars SET has_planets = 1, teff = COALESCE(teff, ?) WHERE id = ?", (teff, sid))
        for p in prs:
            per, sma = fnum(p["pl_orbper"]), fnum(p["pl_orbsmax"])
            if per is None and sma:
                per = 365.25 * sma ** 1.5
            cur = conn.execute("INSERT OR IGNORE INTO planets (star_id, name, period_d, sma_au, rade) VALUES (?,?,?,?,?)",
                               (sid, p["pl_name"], per, sma, fnum(p["pl_rade"])))
            n_planets += cur.rowcount
    conn.commit()
    print(f"exoplanets: {len(hosts):,} host stars ({new_hosts:,} new), {n_planets:,} planets")


def ingest_simbad(conn):
    from astroquery.simbad import Simbad
    simbad = Simbad()
    simbad.TIMEOUT = 180
    idx = SkyIndex(conn)
    added = 0
    for lo, hi in [(100, 100000), (50, 100), (25, 50), (10, 25)]:
        template = ("SELECT TOP 8000 b.main_id, b.ra, b.dec, b.plx_value, b.sp_type{extra} FROM basic AS b {join} "
                    "WHERE b.plx_value > {lo} AND b.plx_value <= {hi} AND b.ra IS NOT NULL AND b.dec IS NOT NULL "
                    "ORDER BY plx_value DESC")
        table = None
        for extra, join in ((", f.V AS vmag", "LEFT OUTER JOIN allfluxes AS f ON f.oidref = b.oid"), ("", "")):
            try:
                table = simbad.query_tap(template.format(extra=extra, join=join, lo=lo, hi=hi))
                break
            except Exception as e:
                print(f"  simbad band {lo}-{hi} mas {'(with V mag)' if extra else ''} failed: {e}")
        if table is None:
            continue
        cols = {c.lower(): c for c in table.colnames}
        for row in table:
            plx, ra, dec = fnum(row[cols["plx_value"]]), fnum(row[cols["ra"]]), fnum(row[cols["dec"]])
            if not plx or plx <= 0 or ra is None or dec is None:
                continue
            main_id = str(row[cols["main_id"]])
            spect = str(row[cols["sp_type"]]) if not np.ma.is_masked(row[cols["sp_type"]]) else None
            vmag = fnum(row[cols["vmag"]]) if "vmag" in cols else None
            _, created = insert_star(conn, idx, norm_name(main_id), ra, dec, 1000.0 / plx * LY_PER_PC, vmag,
                                     teff_from_spect(spect), spect, "star", "simbad", main_id, aliases=[main_id])
            added += created
        conn.commit()
    print(f"simbad: added {added:,} nearby stars")
    found = 0
    for name, kind, ra, dec, dist, mag, teff, spect, aliases, query in LANDMARKS:
        try:
            res = simbad.query_object(query)
            sid = conn.execute("SELECT id FROM stars WHERE name = ?", (name,)).fetchone()
            if res is not None and len(res) and sid:
                add_alias(conn, sid[0], str(res["main_id"][0]))
                found += 1
        except Exception:
            pass
    conn.commit()
    print(f"simbad: resolved {found}/{len(LANDMARKS)} landmark names")


def ingest_vizier(conn):
    from astroquery.vizier import Vizier
    tables = Vizier(row_limit=-1).get_catalogs("J/A+A/640/A1")
    chosen = None
    for t in tables:
        cols = {c.lower(): c for c in t.colnames}
        ncol = cols.get("cluster")
        dcol = next((cols[c] for c in ("distpc", "dist") if c in cols), None)
        racol = next((cols[c] for c in ("ra_icrs", "raj2000", "_ra") if c in cols), None)
        decol = next((cols[c] for c in ("de_icrs", "dej2000", "_de") if c in cols), None)
        if ncol and dcol and racol and decol:
            chosen = (t, ncol, dcol, racol, decol)
            break
    if not chosen:
        print("vizier: no table with cluster name + distance + coordinates found in J/A+A/640/A1")
        return
    t, ncol, dcol, racol, decol = chosen
    idx = SkyIndex(conn)
    added = 0
    for row in t:
        ra, dec, d_pc = fnum(row[racol]), fnum(row[decol]), fnum(row[dcol])
        cname = str(row[ncol]).strip()
        if ra is None or dec is None or not d_pc or not cname:
            continue
        _, created = insert_star(conn, idx, "Cluster_" + norm_name(cname), ra, dec, d_pc * LY_PER_PC, None, None,
                                 "Open cluster", "cluster", "vizier:J/A+A/640/A1", cname, curated=2, aliases=[cname])
        added += created
    conn.commit()
    print(f"vizier: added {added:,} open clusters")


def ingest_gaia(conn, top=300000, max_g=11.0, refresh=False):
    from astropy.table import Table
    cache = os.path.join(CACHE_DIR, "gaia_cache.fits")
    if not os.path.exists(cache) and os.path.exists(os.path.join("data", "gaia_cache.fits")):
        cache = os.path.join("data", "gaia_cache.fits")
    os.makedirs(os.path.dirname(cache) or ".", exist_ok=True)

    if os.path.exists(cache) and not refresh:
        print("gaia: loading cached download", cache)
        t = Table.read(cache)
    else:
        from astroquery.gaia import Gaia
        Gaia.ROW_LIMIT = -1
        adql = f"""
            SELECT TOP {int(top)} source_id, ra, dec, phot_g_mean_mag AS gmag, bp_rp,
                   teff_gspphot AS teff, parallax
            FROM gaiadr3.gaia_source
            WHERE phot_g_mean_mag < {max_g} AND parallax > 0.333 AND parallax_over_error > 5"""
        print("gaia: submitting async job (can take a few minutes)...")
        t = Gaia.launch_job_async(adql).get_results()
        t.write(cache, format="fits", overwrite=True)
        print("gaia: cached to", cache)

    def col(name):
        return np.asarray(np.ma.filled(t[name].astype(float), np.nan), dtype=float)

    sid, ra, dec = np.asarray(t["source_id"], dtype=np.int64), col("ra"), col("dec")
    gmag, bprp, teff, plx = col("gmag"), col("bp_rp"), col("teff"), col("parallax")
    dist_pc = 1000.0 / plx
    ok = np.isfinite(ra) & np.isfinite(dec) & np.isfinite(dist_pc) & (dist_pc > 0)
    idx = SkyIndex(conn)
    existing = np.array(sorted({k[0] * 20000 + k[1] for k in idx.cells}), dtype=np.int64)
    kx, ky = np.floor(ra / CELL).astype(np.int64), np.floor((dec + 90.0) / CELL).astype(np.int64)
    dup = np.zeros(len(ra), dtype=bool)
    if len(existing):
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                dup |= np.isin((kx + dx) * 20000 + (ky + dy), existing)
    keep = ok & ~dup

    bv = np.clip(np.where(np.isfinite(bprp), 0.75 * bprp, 0.65), -0.4, 2.0)
    teff_fallback = 4600.0 * (1.0 / (0.92 * bv + 1.7) + 1.0 / (0.92 * bv + 0.62))
    teff = np.where(np.isfinite(teff), teff, teff_fallback)
    dist_ly = dist_pc * LY_PER_PC
    x, y, z = to_gal_arrays(ra, dec, dist_ly)

    sel = np.nonzero(keep)[0]
    rows = list(zip(
        [f"Gaia_{s}" for s in sid[sel].tolist()], ["star"] * len(sel),
        ra[sel].tolist(), dec[sel].tolist(), dist_ly[sel].tolist(),
        x[sel].tolist(), y[sel].tolist(), z[sel].tolist(),
        gmag[sel].tolist(), teff[sel].tolist(),
        [None] * len(sel), ["gaia_dr3"] * len(sel), [str(s) for s in sid[sel].tolist()], [0] * len(sel)))

    conn.execute("PRAGMA synchronous = OFF")
    for n in ("idx_stars_mag", "idx_stars_curated", "idx_stars_x", "idx_stars_y", "idx_stars_z", "idx_stars_galaxy"):
        conn.execute(f"DROP INDEX IF EXISTS {n}")
    conn.executemany(
        "INSERT OR IGNORE INTO stars (name, kind, ra, dec, dist_ly, x, y, z, mag, teff, spect, source, ext_id, curated) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    conn.executescript(SCHEMA)
    print(f"gaia: {len(t):,} rows, {len(rows):,} new stars stored ({int(dup.sum()):,} already known)")

def galaxy_center(conn, name):
    info = GALAXY_INFO[name]
    if "center" in info:
        return info["center"]
    row = conn.execute("SELECT x, y, z FROM stars WHERE name = ?", (name,)).fetchone()
    return tuple(row) if row else None


def classify_galaxies(conn):
    for name, info in GALAXY_INFO.items():
        if name == "Milky_Way":
            continue
        c = galaxy_center(conn, name)
        if not c:
            continue
        conn.execute(
            "UPDATE stars SET galaxy = ? WHERE kind = 'star' AND source != 'synthetic' "
            "AND (x-?)*(x-?) + (y-?)*(y-?) + (z-?)*(z-?) < ?",
            (name, c[0], c[0], c[1], c[1], c[2], c[2], info["radius_ly"] ** 2))
    conn.commit()
    print("galaxies:", dict(conn.execute("SELECT galaxy, COUNT(*) FROM stars GROUP BY galaxy").fetchall()))


DISC_THICKNESS = 0.008

def generate_galaxy_stars(conn, n=15000):
    conn.execute("DELETE FROM stars WHERE source = 'synthetic'")
    teffs = np.array([3200, 4500, 5600, 6800, 9000, 18000], dtype=float)
    for name, info in GALAXY_INFO.items():
        c = galaxy_center(conn, name)
        if not c:
            continue
        if name == "Milky_Way":
            continue
        R = float(info["radius_ly"])
        rng = np.random.default_rng(sum(map(ord, name)))
        pick = rng.random(n)
        arm_m, bulge_m = pick < 0.45, pick >= 0.88
        r = R * np.sqrt(rng.random(n))
        theta = rng.uniform(0, 2 * math.pi, n)
        t = np.sqrt(rng.random(n))
        arm_theta = rng.integers(0, 2, n) * math.pi + 4.0 * t + rng.normal(0, 0.35, n)
        r = np.where(arm_m, t * R, r)
        theta = np.where(arm_m, arm_theta, theta)
        r = np.where(bulge_m, R * 0.25 * rng.random(n), r)
        theta = np.where(bulge_m, rng.uniform(0, 2 * math.pi, n), theta)
        sigma_z = R * (DISC_THICKNESS + 0.02 * np.exp(-(r / (0.15 * R)) ** 2))
        x = c[0] + r * np.cos(theta)
        y = c[1] + r * np.sin(theta)
        z = c[2] + rng.normal(0, 1, n) * sigma_z
        keep = np.ones(n, dtype=bool)
        if name == "Milky_Way":
            keep = np.sqrt(x * x + y * y + z * z) >= 10000.0
        teff = rng.choice(teffs, n, p=[.3, .2, .2, .15, .1, .05])
        mag = rng.uniform(10, 20, n)
        rows = [(f"{name}_S{i:05d}", "star", None, None, float(math.sqrt(x[i]**2 + y[i]**2 + z[i]**2)),
                 float(x[i]), float(y[i]), float(z[i]), float(mag[i]), float(teff[i]),
                 None, "synthetic", None, 0, name) for i in np.nonzero(keep)[0]]
        conn.executemany(
            "INSERT OR IGNORE INTO stars (name, kind, ra, dec, dist_ly, x, y, z, mag, teff, spect, source, ext_id, curated, galaxy) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    print(f"galaxies: generated up to {n:,} placeholder stars per galaxy")

def step(label, fn, *args):
    print(f"\n== {label} ==")
    try:
        fn(*args)
    except Exception as e:
        print(f"!! {label} failed: {type(e).__name__}: {e}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--curated", action="store_true")
    ap.add_argument("--hyg", nargs="?", const="auto")
    ap.add_argument("--hyg-url")
    ap.add_argument("--exo", action="store_true")
    ap.add_argument("--simbad", action="store_true")
    ap.add_argument("--vizier", action="store_true")
    ap.add_argument("--gaia", nargs="?", type=int, const=300000)
    ap.add_argument("--wiki", nargs="?", type=int, const=150)
    ap.add_argument("--galaxies", nargs="?", type=int, const=4000)
    ap.add_argument("--gaia-refresh", action="store_true")
    a = ap.parse_args()
    if a.all:
        a.curated = a.exo = a.simbad = a.vizier = True
        a.hyg = a.hyg or "auto"
        a.gaia = a.gaia or 300000
        a.wiki = a.wiki or 150
        a.galaxies = a.galaxies or 4000
    if not any([a.curated, a.hyg, a.exo, a.simbad, a.vizier, a.gaia, a.wiki, a.galaxies]):
        ap.print_help()
        return

    conn = connect()
    init_schema(conn)
    if a.curated or a.hyg or a.exo or a.simbad or a.vizier or a.gaia:
        step("curated stars and landmarks", lambda: print("added", seed_curated(conn)))
    if a.hyg:
        path = find_or_fetch_hyg(a.hyg, a.hyg_url)
        if path:
            step(f"HYG ({path})", ingest_hyg, conn, path)
        else:
            print("\n== HYG ==\nNo HYG CSV found. Download hyg*.csv from the astronexus/HYG-Database GitHub repo "
                  "into ./data/ and re-run with --hyg")
    if a.exo:
        step("NASA Exoplanet Archive", ingest_exoplanets, conn)
    if a.simbad:
        step("SIMBAD", ingest_simbad, conn)
    if a.vizier:
        step("VizieR open clusters", ingest_vizier, conn)
    if a.gaia:
        step("Gaia DR3", ingest_gaia, conn, a.gaia, 11.0, a.gaia_refresh)
    if a.curated or a.hyg or a.exo or a.simbad or a.vizier or a.gaia or a.galaxies:
        if a.galaxies:
            step("placeholder galaxy stars", generate_galaxy_stars, conn, a.galaxies)
        step("galaxy classification", classify_galaxies, conn)
        rebuild_index(conn)
    if a.wiki:
        step("Wikipedia summaries", wiki_fill, conn, a.wiki)
    print("\nTotals by kind:", dict(conn.execute("SELECT kind, COUNT(*) FROM stars GROUP BY kind").fetchall()))
    print("Planets:", conn.execute("SELECT COUNT(*) FROM planets").fetchone()[0])
    conn.close()


if __name__ == "__main__":
    main()