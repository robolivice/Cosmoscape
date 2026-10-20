import json
import math
import os
import sqlite3
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import asynccontextmanager, closing

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import ingest

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
FS_DIR = os.path.dirname(CURRENT_DIR)
REPO_ROOT = os.path.dirname(FS_DIR)


def _env_flag(name, default=True):
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value.strip().lower() not in ("0", "false", "no", "off")


def _env_int(name, default=0):
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _default_frontend_dir():
    if getattr(sys, "frozen", False):
        return ingest.resource_path("frontend")
    for base in (FS_DIR, REPO_ROOT):
        candidate = os.path.join(base, "frontend")
        if os.path.isdir(candidate):
            return candidate
    return os.path.join(FS_DIR, "frontend")


DB_NAME = os.environ.get("COSMOSCAPE_DB") or ingest.DB_NAME
MARKDOWN_DIR = os.environ.get("COSMOSCAPE_MARKDOWN") or ingest.MARKDOWN_DIR
FRONTEND_DIR = os.environ.get("COSMOSCAPE_FRONTEND") or _default_frontend_dir()
SEARCH_DB = os.environ.get("COSMOSCAPE_SEARCH_DB") or (os.path.splitext(DB_NAME)[0] + "-search.db")
SEARCH_ENABLED = _env_flag("COSMOSCAPE_SEARCH", True)
SEARCH_SYNC = _env_flag("COSMOSCAPE_SEARCH_SYNC", False)
SEARCH_VERSION = "1"
WIKI_AUTO = _env_flag("COSMOSCAPE_WIKI_AUTO", True)
WIKI_FILL_LIMIT = _env_int("COSMOSCAPE_WIKI_FILL", 0)
STATIC_MAX_AGE = _env_int("COSMOSCAPE_STATIC_MAX_AGE", 0)
WIKI_UA = {"User-Agent": "UniverseNavigator/1.0 (personal project)"}

MAX_MARKDOWN_CHARS = 200_000
MAX_MARKDOWN_NAME = 100

EXTRA_INDEXES = [
    ("idx_stars_galaxy_kind", "CREATE INDEX IF NOT EXISTS idx_stars_galaxy_kind ON stars(galaxy, kind)"),
    ("idx_alias_star", "CREATE INDEX IF NOT EXISTS idx_alias_star ON aliases(star_id)"),
]


def _new_conn(path, *, query_only=False):
    conn = sqlite3.connect(path, timeout=30)
    conn.execute("PRAGMA busy_timeout=30000")
    for pragma in ("PRAGMA cache_size=-32768", "PRAGMA mmap_size=268435456", "PRAGMA temp_store=MEMORY"):
        try:
            conn.execute(pragma)
        except sqlite3.Error:
            pass
    if query_only:
        conn.execute("PRAGMA query_only=ON")
    return conn


class _DbPool:

    def __init__(self, path):
        self.path = path
        self._local = threading.local()
        self._lock = threading.Lock()
        self._connections = []
        self._generation = 0

    def connection(self):
        conn = getattr(self._local, "conn", None)
        if conn is None or getattr(self._local, "generation", -1) != self._generation:
            conn = _new_conn(self.path, query_only=True)
            self._local.conn = conn
            self._local.generation = self._generation
            with self._lock:
                self._connections.append(conn)
        return conn

    def close_all(self):
        with self._lock:
            self._generation += 1
            connections = list(self._connections)
            self._connections.clear()
        for conn in connections:
            try:
                conn.close()
            except sqlite3.Error:
                pass


_pool = _DbPool(DB_NAME)


def db():
    return _pool.connection()


def close_db_connections():
    _pool.close_all()


def db_stamp():
    parts = []
    for path in (DB_NAME, DB_NAME + "-wal"):
        try:
            st = os.stat(path)
            parts.extend((st.st_mtime_ns, st.st_size))
        except OSError:
            parts.append(None)
    return tuple(parts)


_cache_lock = threading.Lock()
_response_cache = {}
_CACHE_MAX = 12


def cached_json(key, builder):
    stamp = db_stamp()
    with _cache_lock:
        hit = _response_cache.get(key)
        if hit is not None and hit[0] == stamp:
            return Response(content=hit[1], media_type="application/json")

    payload = json.dumps(builder(), separators=(",", ":"), ensure_ascii=False).encode("utf-8")

    with _cache_lock:
        if len(_response_cache) >= _CACHE_MAX:
            _response_cache.pop(next(iter(_response_cache)))
        _response_cache[key] = (stamp, payload)
    return Response(content=payload, media_type="application/json")


def clear_response_cache():
    with _cache_lock:
        _response_cache.clear()


def ensure_database():
    folder = os.path.dirname(os.path.abspath(DB_NAME))
    if folder:
        os.makedirs(folder, exist_ok=True)
    os.makedirs(MARKDOWN_DIR, exist_ok=True)
    fresh = not os.path.exists(DB_NAME)
    conn = _new_conn(DB_NAME)
    try:
        ingest.init_schema(conn)
        stars = conn.execute("SELECT COUNT(*) FROM stars").fetchone()[0]
        if stars == 0:
            print("db: empty catalog, seeding curated stars", flush=True)
            ingest.seed_curated(conn)
            if fresh:
                print(
                    f"db: WARNING - a new, nearly empty database was created at\n"
                    f"db:          {DB_NAME}\n"
                    f"db:          it only holds the hand-picked stars, not your catalogue.\n"
                    f"db:          build the full catalogue with: python ingest.py --all",
                    flush=True,
                )

        created = []
        for name, sql in EXTRA_INDEXES:
            exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='index' AND name=?", (name,)).fetchone()
            if exists:
                continue
            started = time.perf_counter()
            conn.execute(sql)
            conn.commit()
            created.append(name)
            print(f"db: created {name} in {time.perf_counter() - started:.2f}s", flush=True)

        if created:
            started = time.perf_counter()
            conn.execute("ANALYZE")
            conn.commit()
            print(f"db: analyzed in {time.perf_counter() - started:.2f}s", flush=True)

        try:
            conn.execute("PRAGMA optimize")
        except sqlite3.Error:
            pass
    finally:
        conn.close()


_fts_lock = threading.Lock()
_fts_state = {"status": "warming", "stamp": None, "error": None}


def _search_stamp(conn):
    max_id = conn.execute("SELECT COALESCE(MAX(id), 0) FROM stars").fetchone()[0]
    star_count = conn.execute("SELECT COUNT(*) FROM stars").fetchone()[0]
    alias_count = conn.execute("SELECT COUNT(*) FROM aliases").fetchone()[0]
    return f"{max_id}:{star_count}:{alias_count}"


def _read_search_meta():
    if not os.path.isfile(SEARCH_DB):
        return None
    uri = "file:" + urllib.parse.quote(SEARCH_DB.replace("\\", "/")) + "?mode=ro"
    try:
        with closing(sqlite3.connect(uri, uri=True, timeout=10)) as conn:
            return dict(conn.execute("SELECT key, value FROM meta").fetchall())
    except sqlite3.Error:
        return None


def _replace_with_retries(src, dst, attempts=10):
    for i in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if i == attempts - 1:
                raise
            time.sleep(0.2)


def _build_search_index(stamp):
    tmp = SEARCH_DB + f".tmp-{os.getpid()}"
    for path in (tmp, tmp + "-wal", tmp + "-shm"):
        try:
            os.remove(path)
        except OSError:
            pass

    started = time.perf_counter()
    print("search: building trigram index (first run only, this can take a while)...", flush=True)
    try:
        conn = sqlite3.connect(tmp, timeout=60)
        try:
            conn.execute("PRAGMA journal_mode=OFF")
            conn.execute("PRAGMA synchronous=OFF")
            conn.execute("CREATE VIRTUAL TABLE search_fts USING fts5(txt, star_id UNINDEXED, tokenize='trigram')")
            conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
            conn.execute("ATTACH DATABASE ? AS src", (DB_NAME,))
            conn.execute(
                "INSERT INTO search_fts (txt, star_id) "
                "SELECT REPLACE(name, ' ', '_'), id FROM src.stars "
                "WHERE galaxy = 'Milky_Way' AND source != 'synthetic' AND kind = 'star'"
            )
            conn.execute(
                "INSERT INTO search_fts (txt, star_id) "
                "SELECT REPLACE(a.alias, ' ', '_'), a.star_id FROM src.aliases a "
                "JOIN src.stars s ON s.id = a.star_id "
                "WHERE s.galaxy = 'Milky_Way' AND s.source != 'synthetic' AND s.kind = 'star'"
            )
            conn.execute("INSERT INTO meta (key, value) VALUES ('version', ?), ('stamp', ?)", (SEARCH_VERSION, stamp))
            conn.commit()
        finally:
            conn.close()

        _replace_with_retries(tmp, SEARCH_DB)
        with _fts_lock:
            _fts_state.update(status="ready", stamp=stamp, error=None)
        size_mb = os.path.getsize(SEARCH_DB) / 1e6
        print(f"search: index ready in {time.perf_counter() - started:.1f}s ({size_mb:.0f} MB)", flush=True)
    except Exception as exc:
        with _fts_lock:
            _fts_state.update(status="failed", error=str(exc))
        print(f"search: index build failed ({exc}); using LIKE fallback", flush=True)
        for path in (tmp, tmp + "-wal", tmp + "-shm"):
            try:
                os.remove(path)
            except OSError:
                pass


def start_search_warmup():
    if not SEARCH_ENABLED:
        with _fts_lock:
            _fts_state["status"] = "disabled"
        print("search: disabled, using LIKE fallback", flush=True)
        return

    try:
        with closing(_new_conn(DB_NAME, query_only=True)) as conn:
            stamp = _search_stamp(conn)
    except sqlite3.Error as exc:
        with _fts_lock:
            _fts_state.update(status="failed", error=str(exc))
        print(f"search: cannot read database ({exc}); using LIKE fallback", flush=True)
        return

    meta = _read_search_meta()
    if meta and meta.get("version") == SEARCH_VERSION and meta.get("stamp") == stamp:
        with _fts_lock:
            _fts_state.update(status="ready", stamp=stamp)
        print("search: trigram index ready", flush=True)
        return

    if SEARCH_SYNC:
        _build_search_index(stamp)
    else:
        threading.Thread(target=_build_search_index, args=(stamp,), name="search-index", daemon=True).start()


def refresh_after_db_swap():
    clear_response_cache()
    close_db_connections()
    try:
        stamp = _search_stamp(db())
    except sqlite3.Error:
        stamp = None
    with _fts_lock:
        _fts_state.update(status="warming", stamp=None, error=None)
    if stamp:
        threading.Thread(target=_build_search_index, args=(stamp,), name="search-index", daemon=True).start()


def _fts_ready():
    with _fts_lock:
        return _fts_state["status"] == "ready"


def _fts_search(q, limit):
    norm = q.replace(" ", "_")
    match = '"' + norm.replace('"', '""') + '"'
    uri = "file:" + urllib.parse.quote(SEARCH_DB.replace("\\", "/")) + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=10)) as conn:
        ids = [row[0] for row in conn.execute(
            "SELECT DISTINCT star_id FROM search_fts WHERE search_fts MATCH ? LIMIT 500", (match,))]
    if not ids:
        return []
    placeholders = ",".join("?" * len(ids))
    return db().execute(
        f"SELECT name, x, y, z, mag, teff, curated FROM stars WHERE id IN ({placeholders}) "
        "AND kind = 'star' AND galaxy = 'Milky_Way' AND source != 'synthetic' "
        "ORDER BY (curated = 0), curated, mag LIMIT ?",
        (*ids, limit),
    ).fetchall()


def _like_search(q, limit):
    pattern = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_").replace(" ", "_") + "%"
    return db().execute(
        "SELECT s.name, s.x, s.y, s.z, s.mag, s.teff, s.curated FROM stars s "
        "WHERE s.kind = 'star' AND s.galaxy = 'Milky_Way' AND s.source != 'synthetic' "
        "AND (s.name LIKE ? ESCAPE '\\' OR EXISTS("
        "  SELECT 1 FROM aliases a WHERE a.star_id = s.id AND a.alias LIKE ? ESCAPE '\\')) "
        "ORDER BY (s.curated = 0), s.curated, s.mag LIMIT ?",
        (pattern, pattern, limit),
    ).fetchall()


_wiki_lock = threading.Lock()
_wiki_state = {"running": False, "done": 0, "total": 0, "message": "idle"}


def _wiki_summary(title):
    url = "https://en.wikipedia.org/api/rest_v1/page/summary/" + urllib.parse.quote(title, safe="_'()*")
    with urllib.request.urlopen(urllib.request.Request(url, headers=WIKI_UA), timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _placeholder_text(name):
    return (
        f"# {name}\n\nType: Stellar Objective\n\n"
        f"*Edit `{markdown_filename(name)}` to add records.*"
    )


def _is_placeholder(text, name=None):
    def norm(value):
        return " ".join(value.split())

    if name is None:
        stripped = norm(text)
        return stripped.startswith("Type: Stellar Objective") and stripped.endswith("to add records.*")
    return norm(text) == norm(_placeholder_text(name))


def canonical_star_name(conn, name):
    row = conn.execute("SELECT name FROM stars WHERE name = ? COLLATE NOCASE", (name,)).fetchone()
    if row:
        return row[0]
    row = conn.execute(
        "SELECT s.name FROM aliases a JOIN stars s ON s.id = a.star_id "
        "WHERE a.alias = ? COLLATE NOCASE LIMIT 1", (name,)
    ).fetchone()
    return row[0] if row else None


def pull_wikipedia(conn, name, force=False):
    path = markdown_path(name)
    if os.path.isfile(path) and not force:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                if not _is_placeholder(handle.read(), name):
                    return "kept"
        except OSError:
            pass

    title = ingest.WIKI_TITLES.get(name, name)
    try:
        data = _wiki_summary(title)
    except urllib.error.HTTPError as exc:
        return "missing" if exc.code == 404 else "error"
    except Exception:
        return "error"

    if data.get("type") == "disambiguation" or not data.get("extract"):
        return "missing"

    page = data.get("content_urls", {}).get("desktop", {}).get("page", "https://en.wikipedia.org/wiki/" + title)
    try:
        write_atomic(path, ingest.build_markdown(conn, name, data["extract"], page))
    except OSError:
        return "error"
    return "pulled"


def _wiki_pending(conn, limit):
    names = []
    for (name,) in conn.execute(
        "SELECT name FROM stars WHERE curated >= 1 OR has_planets = 1 "
        "ORDER BY (curated = 1) DESC, mag LIMIT ?",
        (limit,),
    ):
        try:
            path = markdown_path(name)
        except HTTPException:
            continue
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    if not _is_placeholder(handle.read(), name):
                        continue
            except OSError:
                pass
        names.append(name)
    return names


def _wiki_fill_worker(limit):
    conn = None
    try:
        conn = _new_conn(DB_NAME, query_only=True)
        names = _wiki_pending(conn, limit)
        with _wiki_lock:
            _wiki_state.update(running=True, done=0, total=len(names), message="pulling Wikipedia summaries")
        for name in names:
            pull_wikipedia(conn, name)
            with _wiki_lock:
                _wiki_state["done"] += 1
            time.sleep(0.1)
        with _wiki_lock:
            _wiki_state["message"] = f"done ({_wiki_state['done']} checked)"
    except Exception as exc:
        with _wiki_lock:
            _wiki_state["message"] = f"failed: {exc}"
    finally:
        if conn is not None:
            conn.close()
        with _wiki_lock:
            _wiki_state["running"] = False


def to_scene(x, y, z):
    gx, gy, gz = x, z, -y
    r = math.sqrt(gx * gx + gy * gy + gz * gz)
    if r == 0:
        return 0.0, 0.0, 0.0
    if r <= 100:
        k = 15.0
    else:
        k = (1500.0 + 300.0 * math.log10(r / 100.0)) / r
    return gx * k, gy * k, gz * k


def to_scene_galaxy(name, info, c):
    sx, sy, sz = c[0], c[2], -c[1]
    if name == "Milky_Way":
        s = info["display"] / (2.0 * info["radius_ly"])
        return sx * s, sy * s, sz * s
    r = math.sqrt(sx * sx + sy * sy + sz * sz)
    if r == 0:
        return 0.0, 0.0, 0.0
    d = 5500.0 + 600.0 * math.log10(max(r, 1.0) / 100000.0)
    return sx / r * d, sy / r * d, sz / r * d


MW_Z_SQUASH = 0.15


class MarkdownUpdate(BaseModel):
    content: str = Field(..., max_length=MAX_MARKDOWN_CHARS)


def markdown_filename(name: str) -> str:
    stem = ingest.note_stem(name)
    if len(stem) > MAX_MARKDOWN_NAME:
        raise HTTPException(status_code=400, detail="Object name is too long for a note file")
    return f"{stem}.md"


def markdown_path(name: str) -> str:
    return os.path.join(MARKDOWN_DIR, markdown_filename(name))


def write_atomic(path: str, content: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".note-", suffix=".tmp", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def resolve_note(conn, requested):
    path = markdown_path(requested)
    if os.path.isfile(path):
        return requested, path
    canonical = canonical_star_name(conn, requested)
    if canonical:
        canonical_path = markdown_path(canonical)
        if os.path.isfile(canonical_path):
            return canonical, canonical_path
    return canonical, path


def create_app(desktop: bool = False) -> FastAPI:

    desktop_support = None
    startup_hooks = []
    if desktop:
        from . import desktop as desktop_support
        startup_hooks = [desktop_support.install_seed, desktop_support.install_seed_notes]

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        print(f"data    : {ingest.DATA_DIR}", flush=True)
        print(f"db      : {DB_NAME}", flush=True)
        print(f"notes   : {MARKDOWN_DIR}", flush=True)
        print(f"frontend: {FRONTEND_DIR}", flush=True)
        for hook in startup_hooks:
            try:
                hook()
            except Exception as exc:
                print(f"startup hook failed: {type(exc).__name__}: {exc}", flush=True)
        ensure_database()
        start_search_warmup()
        if WIKI_FILL_LIMIT > 0:
            threading.Thread(target=_wiki_fill_worker, args=(WIKI_FILL_LIMIT,), name="wiki-fill", daemon=True).start()
            print(f"wiki: background fill of up to {WIKI_FILL_LIMIT} placeholder notes started", flush=True)
        yield

    app = FastAPI(lifespan=lifespan)

    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:8000", "http://localhost:8000"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def cache_headers(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/static/"):
            if STATIC_MAX_AGE > 0:
                response.headers.setdefault("Cache-Control", f"public, max-age={STATIC_MAX_AGE}")
            else:
                response.headers["Cache-Control"] = "no-cache"
        else:
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/health")
    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/api/status")
    def api_status():
        return cached_json(("status",), lambda: {"stars": db().execute("SELECT COUNT(*) FROM stars").fetchone()[0]})

    @app.get("/galaxies/")
    def get_galaxies():
        def build():
            conn = db()
            counts = dict(conn.execute("SELECT galaxy, COUNT(*) FROM stars WHERE kind = 'star' GROUP BY galaxy"))
            out = []
            for name, info in ingest.GALAXY_INFO.items():
                center = ingest.galaxy_center(conn, name)
                if not center:
                    continue
                sx, sy, sz = to_scene_galaxy(name, info, center)
                out.append({
                    "name": name, "x": sx, "y": sy, "z": sz,
                    "radius_ly": info["radius_ly"], "display": info["display"],
                    "tilt": info["tilt"], "texture": info.get("texture"),
                    "count": counts.get(name, 0),
                })
            return ingest.layout_galaxy_scene(out)

        return cached_json(("galaxies",), build)

    @app.get("/galaxy/{name}/stars")
    def get_galaxy_stars(name: str, limit: int = Query(40001, ge=1, le=200000)):
        info = ingest.GALAXY_INFO.get(name)
        if not info:
            raise HTTPException(status_code=404, detail="Unknown galaxy")

        def build():
            conn = db()
            center = ingest.galaxy_center(conn, name)
            if not center:
                raise HTTPException(status_code=404, detail="Galaxy not in database")

            cols = "name, x, y, z, mag, teff, curated"
            rows = []

            if name != "Milky_Way":
                rows.extend(conn.execute(
                    f"SELECT {cols} FROM stars WHERE galaxy = ? AND kind = 'star' AND source = 'synthetic' LIMIT ?",
                    (name, limit),
                ).fetchall())

            if len(rows) < limit:
                rows.extend(conn.execute(
                    f"SELECT {cols} FROM stars WHERE galaxy = ? AND kind = 'star' AND source != 'synthetic' "
                    "AND (curated >= 1 OR has_planets = 1) LIMIT ?",
                    (name, limit - len(rows)),
                ).fetchall())

            if len(rows) < limit:
                rows.extend(conn.execute(
                    f"SELECT {cols} FROM stars WHERE galaxy = ? AND kind = 'star' AND source != 'synthetic' "
                    "AND curated = 0 AND has_planets = 0 ORDER BY rnd LIMIT ?",
                    (name, limit - len(rows)),
                ).fetchall())

            rows = rows[:limit]
            scale = info["display"] / (2.0 * info["radius_ly"])
            squash = MW_Z_SQUASH if name == "Milky_Way" else 1.0
            cx, cy, cz = center
            return [
                {
                    "name": n,
                    "x": (x - cx) * scale,
                    "y": (z - cz) * scale * squash,
                    "z": -(y - cy) * scale,
                    "mag": mag, "teff": teff, "cur": cur,
                }
                for n, x, y, z, mag, teff, cur in rows
            ]

        return cached_json(("stars", name, limit), build)

    @app.get("/search/")
    def search_stars(q: str = Query(..., max_length=80), limit: int = Query(8, ge=1, le=50)):
        q = q.strip()
        if len(q) < 2 or not any(ch.isalnum() for ch in q):
            return []

        rows = None
        if len(q) >= 3 and _fts_ready():
            try:
                rows = _fts_search(q, limit)
            except sqlite3.Error as exc:
                print(f"search: FTS query failed ({exc}); falling back to LIKE", flush=True)
                with _fts_lock:
                    _fts_state["status"] = "failed"
                rows = None

        if rows is None:
            rows = _like_search(q, limit)

        info = ingest.GALAXY_INFO["Milky_Way"]
        scale = info["display"] / (2.0 * info["radius_ly"])
        cx, cy, cz = info["center"]
        return [
            {
                "name": n,
                "x": (x - cx) * scale,
                "y": (z - cz) * scale * MW_Z_SQUASH,
                "z": -(y - cy) * scale,
                "mag": mag, "teff": teff, "cur": cur,
            }
            for n, x, y, z, mag, teff, cur in rows
        ]

    @app.get("/planets/")
    def get_planets():
        def build():
            out = {}
            for star, pname, period, sma, rade in db().execute(
                "SELECT s.name, p.name, p.period_d, p.sma_au, p.rade FROM planets p "
                "JOIN stars s ON s.id = p.star_id WHERE s.galaxy = 'Milky_Way'"
            ):
                out.setdefault(star, []).append({"name": pname, "period": period, "sma": sma, "rade": rade})
            return out

        return cached_json(("planets",), build)

    @app.get("/objects/")
    def get_objects(limit: int = Query(300, ge=1, le=5000)):
        def build():
            rows = db().execute(
                "SELECT name, x, y, z FROM stars "
                "WHERE kind != 'galaxy' AND source != 'synthetic' AND (curated >= 1 OR dist_ly < 50) "
                "ORDER BY curated DESC, dist_ly LIMIT ?", (limit,)
            ).fetchall()
            out = []
            for name, x, y, z in rows:
                sx, sy, sz = to_scene(x, y, z)
                out.append({"name": name, "x": sx, "y": sy, "z": sz})
            return out

        return cached_json(("objects", limit), build)

    @app.post("/api/wiki/fill")
    def wiki_fill_start(limit: int = Query(150, ge=1, le=2000)):
        with _wiki_lock:
            if _wiki_state["running"]:
                raise HTTPException(status_code=409, detail="A Wikipedia fill is already running")
            _wiki_state.update(running=True, done=0, total=0, message="scanning notes")
        threading.Thread(target=_wiki_fill_worker, args=(limit,), name="wiki-fill", daemon=True).start()
        return {"status": "started", "limit": limit}

    @app.get("/api/wiki/fill/status")
    def wiki_fill_status():
        with _wiki_lock:
            return dict(_wiki_state)

    @app.post("/api/wiki/{celestial_body}")
    def wiki_pull_one(celestial_body: str, force: bool = Query(False)):
        canonical = canonical_star_name(db(), celestial_body)
        if canonical is None:
            raise HTTPException(status_code=404, detail="Not in the catalogue: notes are only created for known objects")
        filename = markdown_filename(canonical)
        result = pull_wikipedia(db(), canonical, force=force)
        if result == "kept":
            return {
                "status": "kept", "file": filename,
                "message": "this note has your own content; add ?force=true to overwrite",
            }
        if result == "missing":
            raise HTTPException(status_code=404, detail="No Wikipedia summary found for this object")
        if result == "error":
            raise HTTPException(status_code=502, detail="Wikipedia request failed (offline or blocked)")
        with open(os.path.join(MARKDOWN_DIR, filename), "r", encoding="utf-8") as handle:
            content = handle.read()
        return {"status": "pulled", "file": filename, "content": content}

    @app.get("/api/info/{celestial_body}")
    def get_celestial_markdown(celestial_body: str):
        conn = db()
        canonical, path = resolve_note(conn, celestial_body)
        content = None
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    content = handle.read()
            except OSError:
                content = None

        if content is None and WIKI_AUTO and canonical:
            try:
                pull_wikipedia(conn, canonical)
                canonical_path = markdown_path(canonical)
                if os.path.isfile(canonical_path):
                    with open(canonical_path, "r", encoding="utf-8") as handle:
                        content = handle.read()
            except HTTPException:
                pass
            except Exception as exc:
                print(f"wiki: pull for {celestial_body!r} failed: {exc}", flush=True)

        if content is None:
            content = _placeholder_text(canonical or celestial_body)
        return {"name": celestial_body, "content": content}

    @app.put("/api/info/{celestial_body}")
    def save_celestial_markdown(celestial_body: str, update: MarkdownUpdate):
        conn = db()
        canonical, path = resolve_note(conn, celestial_body)
        target = path
        if canonical and not os.path.isfile(path):
            target = markdown_path(canonical)
        try:
            write_atomic(target, update.content)
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"Could not save note: {exc}") from exc
        return {"status": "saved", "file": os.path.basename(target)}

    if desktop_support is not None:
        desktop_support.register_routes(app)
    else:
        @app.post("/api/import-data")
        def import_data():
            raise HTTPException(
                status_code=501,
                detail="Import is not available in the web build. Run: python ingest.py --all",
            )

        @app.get("/api/import-status")
        def import_status():
            return {"status": "error", "message": "Import is not available in the web build.", "progress": 0}

    if os.path.isdir(FRONTEND_DIR):
        app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
    else:
        print(f"WARNING: frontend folder not found at {FRONTEND_DIR}", flush=True)

    @app.get("/")
    def read_index():
        index = os.path.join(FRONTEND_DIR, "index.html")
        if not os.path.isfile(index):
            raise HTTPException(status_code=503, detail=f"Frontend not found at {index}")
        return FileResponse(index)

    return app
