# Changelog

All notable changes to Cosmoscape are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.0] - 2026-10-20

### Changed
- One shared backend for both builds: the new `Cosmoscape-FS/` folder holds the FastAPI
  application (`Cosmoscape-FS/cosmoscape_fs/app.py`), the catalog loader
  (`Cosmoscape-FS/cosmoscape_fs/ingest.py`), the desktop only parts
  (`Cosmoscape-FS/cosmoscape_fs/desktop.py`) and the shared frontend
  (`Cosmoscape-FS/frontend/`). `Cosmoscape-web/main.py` and `Cosmoscape-win/main.py` are
  now thin entry points, and `ingest.py` in both app folders is a wrapper around the
  shared loader.
- Both builds now use the same database, the same notes and the same download caches in
  the user data folder, so one catalogue serves the browser and the desktop app.
- The database is opened with read-only connections that can be dropped and reopened,
  so the desktop build can replace the catalogue file while the server is running
  (Windows refuses to replace a file that is still open).
- Search uses a trigram index with a LIKE fallback, answers are cached per database
  version and the response body is compressed.
- The galaxy textures are shipped at 4096 px instead of 5600-5900 px. They still hold
  more detail than the screen can show, but they load and upload much faster and use
  about half the graphics memory.
- Source comments were removed from the first-party files. The Python code had none, so
  this only affects `Cosmoscape-FS/frontend/scripts.js`, `Cosmoscape-FS/frontend/styles.css`
  and `Cosmoscape-win/electron/main.js`.
- `Cosmoscape-FS/frontend/textures/Andromeda.png` is no longer tracked in the
  repository. Nothing referenced it, and it is now in `.gitignore`.

### Added
- `GET /api/health` for the Electron shell.
- `POST /api/wiki/{name}`, `POST /api/wiki/fill` and `GET /api/wiki/fill/status` to pull
  Wikipedia summaries into the notes.
- Notes are looked up by alias as well, so "Sun" opens the note of "Sol".

### Fixed
- Desktop: the loading screen no longer fades out before the galaxy textures have
  loaded. The status text the Electron shell watches is now published after the
  textures are in, so the galaxies are already on screen when the screen fades.
  `scripts.js` waits for the pending textures, `electron/main.js` allows more time
  for it.
- The galaxy textures are much smaller: `Andromeda2.png` (5884x5439, 33 MB, 122 MB in
  VRAM) is now `Andromeda2.jpg` (4096x3786, 2.3 MB) and `galaxy_top.jpg` is downscaled
  from 5600x5600 to 4096x4096. They are still above 1:1 at the normal viewing distance,
  but they decode and upload far faster and use half the graphics memory, which is what
  made the loading screen stall on weaker hardware.
- `GET /api/info/{name}` no longer writes a stub file for every requested name, and
  `PUT` limits the note to 200,000 characters and sanitises the file name.
- LIKE wildcards typed in the search box are escaped, so a `%` is no longer a wildcard.
- The server prints a warning and answers with 503 when the frontend folder is missing,
  instead of starting and serving nothing.
- Desktop: the health check has a timeout, so a backend that accepts the connection but
  never answers can no longer freeze the shell.

## [1.1.0] - 2026-10-18

### Added
- Navigator panel entrance animation: a beam traces the top edge of the panel, flashes the bar
  when it arrives, then the body rolls down.
- Click an empty part of the Navigator panel to collapse it with the reverse animation. A
  "Navigator" button appears at the top left to bring it back.
- Both animations are skipped when the system's reduced-motion setting is on.

### Changed
- Desktop: the panel animation now starts after the loading screen has finished fading out.
  `electron/main.js` adds a `ready` class to the page at that point.
- The panel's top bar now spans the full width of the panel and is slightly taller.
- Status text capitalised to "Verifying Data Systems".

## [1.0.1] - 2026-10-17

### Added
- Web: a loading screen (orbit animation, starfield, COSMOSCAPE title and status text)
  that fades out once the galaxy list and textures have loaded, with a 30 second fallback.
- Web: Favicon (previously didnt exist)
- Unified Frontend

### Changed
- The map now opens on a wider starting view: camera at (-4180, 4448, 2963) looking at
  the origin, with the field of view set to 60 (`initEngine()` in `scripts.js`).
- Camera FOV fixes when entering the system.
- Entering a galaxy now flies straight in along your current line of sight instead of
  swinging round to a fixed angle on arrival. This matches how leaving a galaxy works.
- After the Milky Way's stars finish loading, the camera zooms in a little further on its
  own (`GALAXY_SETTLE_R` 2500, `GALAXY_SETTLE_MS` 2250), so the yellow star markers are
  visible straight away.
- Unified UI (frontend) for both the Desktop and the Web version.
- Web: static files are served with Cache-Control: no-cache, so updates show without a hard refresh.

### Fixed
- Desktop: fixed a crash in the packaged app ("TypeError: Cannot read properties of null
  (reading 'setBounds')") when the window was resized after the loading screen had
  finished. The `fit` resize handler in `electron/main.js` no longer uses the loading
  view once it has been removed.

## [1.0.0] - 2026-10-16

First release.

### Added
- 3D star map built with FastAPI, SQLite and three.js: fly from the Milky Way and
  other galaxies down to individual star systems, search stars by name or alias, and
  read or edit notes on any object.
- Electron desktop version wrapping the same backend and frontend. The backend starts
  on a free local port and stops when the app closes. Features match the web version.
- Animated loading screen for the desktop app (`electron/loading.html`) with an orbit
  animation, starfield, COSMOSCAPE title and rotating status text. It sits on top of
  the app in a second `WebContentsView` while it loads, and fades out once the backend reports
  it is online, with a 30 second fallback.
- KTX2 (Basis Universal) compressed textures for planets, the Sun and rings, loaded
  with three.js `KTX2Loader`. Galaxy textures from the database can still be PNG or JPG.
- three.js r147 vendored locally in `frontend/vendor/three/`, loaded as ES modules
  through an import map. No CDN is needed.
- Fonts (Space Mono) and the marked library bundled locally.
- `ingest.py` for building a local star database from HYG, NASA Exoplanet Archive,
  SIMBAD, VizieR, Gaia DR3 and Wikipedia, plus curated stars and generated galaxy stars.
- `build_backend.py` (PyInstaller bundle of the backend and `frontend/`) and
  `package_db.py` (compresses a database for hosting).
- Premade Windows installer, published on GitHub Releases, with a bundled star database.
- First-launch database seeding from a bundled `seed/universe.db` into the user data
  folder. `COSMOSCAPE_DATA` overrides the data location.
- `requirements-ingest.txt` for ingest-only dependencies (numpy, astroquery, astropy).

### Security
- CORS restricted to the local app, since the server accepts writes.
- DevTools disabled in packaged builds with `devTools: !app.isPackaged`, which blocks
  Ctrl+Shift+I, F12 and Inspect.

### Notes
- Textures must be Basis Universal KTX2 (UASTC or ETC1S). If they appear upside down,
  re-encode them with `toktx --lower_left_maps_to_s0t0`.
- `setTranscoderPath` must point at the folder where the Basis transcoder
  (`basis_transcoder.js` and `.wasm`) was copied.
- Release builds need `npm run build:backend` followed by `npm run dist` whenever
  `frontend/` changes. `npm start` runs the backend from source.
- If you add a Content Security Policy, `script-src` needs `'wasm-unsafe-eval'` and
  `'unsafe-inline'`, and `worker-src` needs `blob:`.

[1.2.0]: https://github.com/robolivice/cosmoscape/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/robolivice/cosmoscape/compare/v1.0.1...v1.1.0
[1.0.1]: https://github.com/robolivice/cosmoscape/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/robolivice/cosmoscape/releases/tag/v1.0.0