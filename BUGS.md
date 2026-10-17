# Bugs and cleanup notes

## Fixed
- [x] Google Fonts link pointed at googleapis.com (fonts are now local, in the shared `frontend/fonts`)
- [x] `stroke-linejoin="linejoin"` in the True Scale checkbox SVG
- [x] `.button` vs `.xbutton` in the click and hover guards
- [x] Duplicate `@app.get("/galaxies/")`
- [x] CORS was `*` on a server that accepts writes
- [x] `test.py` renamed to `main.py`
- [x] `import numpy as np` removed from `main.py`
- [x] `sqlite3.connect` used with `with` did not close the connection (now `closing`)
- [x] `/galaxy/{name}/stars` used `ORDER BY RANDOM()` (now a stored `rnd` column)
- [x] "Sync Real Data" button was misleading (now "Import Database")
- [x] Name and year in `LICENSE`
- [x] Missing `platformdirs` in `requirements.txt`
- [x] Packaged app crash ("Cannot read properties of null (reading 'setBounds')") when the
      window was resized after the loading screen finished (`fit` in `electron/main.js`)
- [x] `Cosmoscape-web` and `Cosmoscape-win` each had their own copy of `frontend/` and the
      two had drifted apart (CDN vs bundled libraries, different loaders, different import
      code). There is now one shared `frontend/` at the repo root, and both backends and
      the PyInstaller build read from it
- [x] Web version needed an internet connection for three.js, marked and fonts (now bundled)
- [x] Web `GET /api/status` returned 404 (route added to `Cosmoscape-web/main.py`)
- [x] Web in-page loader showed on top of the desktop loading screen (the page loader is
      now hidden when the app opens with `?desktop=1`)
- [x] Web icon link used backslashes (`static\textures\icon.png`), now forward slashes
- [x] Old `/sync-real-data/` route and the "Sync Data" button removed from the web version
      (it only re-ran the curated seed that the server already runs on first start)
- [x] Page could be reloaded in the packaged app with F5, Ctrl+R or Ctrl+Shift+R, and the
      hidden menu had a Reload item (shortcuts blocked and menu removed when packaged)

## Open: real bugs
- [ ] **`ingest.py --galaxies` alone does nothing on a fresh DB.** The curated step only
      runs for the other flags, so the galaxy centers (from the landmark rows) don't exist
      yet and `generate_galaxy_stars` skips every galaxy. Fix: include `a.galaxies` in the
      condition that runs `seed_curated`. Workaround: `--curated --galaxies` or `--all`.
- [ ] **Silent empty server if the shared `frontend/` folder is missing.** Both `main.py`
      files only mount it `if os.path.exists(FRONTEND_DIR)`, so the server starts and
      serves nothing (now easier to hit, because the folder sits outside the app folders).
      Print a warning or raise instead.
- [ ] **`GET /api/info/{name}` creates a file for any name requested.** Anyone hitting the
      URL can fill `database/` with stub files. Return the template without writing, and
      only write on PUT.
- [ ] **No size limit on `PUT /api/info/...`.** Add a max length on `content`.
- [ ] **LIKE wildcards in `/search/`**: a typed `%` acts as a wildcard. Escape it.
- [ ] **Texture leak**: `exitSystem` disposes geometries but not materials or textures,
      and each Sol entry calls `textureLoader.load` again for every planet. Cache the
      loaded textures and dispose materials on exit.
- [ ] **`REAL_SYSTEMS.Sol` references `earth.ktx2`**, but Earth actually uses the shader with
      `earth_day` / `earth_night`; `earth.ktx2` is never loaded. Harmless, but the
      path is misleading.
- [ ] **`HYG_URLS` are guessed file names** and may break when the repo renames the file.
      The manual fallback in `data/` is the safety net.
- [ ] **Gaia insert skips `galaxy` and `INSERT OR IGNORE` hides name clashes**, so the
      reported "new stars stored" count can be higher than what actually landed.
- [ ] **Gaia rows get `rnd` only on the next `init_schema`.** Until then they have
      `rnd = NULL` and sort first in `ORDER BY rnd`. Set `rnd` in the Gaia insert.

## Open: cleanup
- [ ] `scripts.js`: `REAL_SYSTEMS.Sun = REAL_SYSTEMS.Sol;` is still written twice
- [ ] `scripts.js`: dead code: `loadStars()`, `/objects/` endpoint and `to_scene()` in
      main.py, `wantModels = false` model-streaming path, unused `camDist`,
      `MODEL_VIEW_DIST`, `skip: new Set()`, `if (true) { ... } else { ... }` in
      orbit-path creation
- [ ] `ingest.py`: unused `import sys`; `idx_stars_mag` created twice in SCHEMA; the
      `if name == "Milky_Way"` block after `continue` in `generate_galaxy_stars` is dead
- [ ] `main.py`: unused `MW_REAL_COVERAGE_LY`
- [ ] `index.html`: three `.cosmic-dust` divs have no CSS; `#wormhole-icon` is empty
- [ ] `styles.css`: `.button`, `.wormhole-border` and the `rotate` keyframes are unused;
      `body` is defined twice; `.button` has duplicate declarations
- [ ] `marked.parse` output goes into `innerHTML`; fine for your own notes, wrap with
      DOMPurify if untrusted markdown ever lands there
- [ ] `main.py` and `ingest.py` are still duplicated between `Cosmoscape-web` and
      `Cosmoscape-win` and have drifted apart (the desktop copy has seed install and the
      import routes, the web copy has the no-cache header and CORS). Consider a shared
      `backend/` folder the same way `frontend/` is shared
- [ ] `frontend/vendor/` may contain files the import map no longer uses (`three.min.js`,
      `OrbitControls.js`); check and delete to shrink the installer

## Web version
- [ ] The shared `frontend/` calls `/api/import-data` and `/api/import-status` from the
      Import Database button, which is hidden. `Cosmoscape-web/main.py` has no such
      routes, so un-hiding the button there gives 404s. Add the routes first
- [ ] `Cosmoscape-web/main.py` sends `Cache-Control: no-cache` for static files; the
      desktop backend does not (not needed there, since the port changes on every launch)

## Desktop version
- [ ] Test the installer on a machine without Python or Node
- [ ] Code-signing: unsigned Windows builds show security warnings
- [ ] `DB_URL` in `main.py` is still a placeholder; set it and `DB_SHA256` before
      showing the Import Database button
- [ ] After the shared-frontend move, check that `dist/cosmoscape-backend/_internal/frontend/index.html`
      exists after `npm run build:backend` (the `--add-data` path now points at `../frontend`)
- [ ] Reload shortcuts are only blocked when packaged; check in the installed app, not
      with `npm start`