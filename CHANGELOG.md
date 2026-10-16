# Changelog

All notable changes to Cosmoscape are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[1.0.0]: https://github.com/robolivice/cosmoscape/releases/tag/v1.0.0