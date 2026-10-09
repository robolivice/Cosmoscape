[![License](https://shields.io)](https://github.com/robolivice/cosmoscape)
[![GitHub stars](https://shields.io)](https://github.com)
# Cosmoscape

A 3D star map that runs in your browser. Fly from the Milky Way to individual star
systems, search for stars, and read or edit notes on any object. Built with FastAPI,
SQLite and three.js.

> **This repository ships no star data.** You build your own local database with
> `ingest.py`, so every catalog stays with its original source and license.

## Quick start

```bash
git clone https://github.com/roboliveice/cosmoscape.git
cd Cosmoscape
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate

pip install -r requirements-ingest.txt
python ingest.py --all
python main.py
```

Open http://127.0.0.1:8000

Run `python ingest.py --all` **before the first launch**. Without it you only get about
35 hand-picked stars and landmarks, and the other galaxies have no stars at all.

Need only the viewer with minimal data? Use `pip install -r requirements.txt` and
`python ingest.py --curated --galaxies`.

## Importing data

| Flag | Source | Notes |
|---|---|---|
| `--curated` | built in | Hand-picked stars and landmarks. Offline, instant. |
| `--hyg [path]` | HYG database | About 120k stars. Auto-download may fail; if so, put the CSV in `data/` yourself. |
| `--exo` | NASA Exoplanet Archive | Real planets and host stars. |
| `--simbad` | SIMBAD | Nearby stars and catalog IDs for landmarks. |
| `--vizier` | VizieR | Open clusters (Cantat-Gaudin et al. 2020). |
| `--gaia [N]` | Gaia DR3 | N brightest stars within about 3 kpc (default 300000). Slowest; the download is cached in `data/`. |
| `--galaxies [N]` | generated | Placeholder stars for the other galaxies. Needs `--curated` (or `--all`) on a fresh database. |
| `--wiki [N]` | Wikipedia | Writes summaries into `database/*.md`. |
| `--all` | everything | Runs all of the above in the right order. |

Flags can be combined, e.g. `python ingest.py --curated --exo --gaia 100000`.
Re-running is safe; duplicates between catalogs are detected by sky position.

## Controls

- Click a galaxy to fly into it. Click a star to enter its system.
- Search box: find a star by name or alias (Milky Way only).
- Left-drag orbits, right-drag pans, scroll zooms, arrow keys pan.
- "Show All Star Names" and "True Scale (Alpha Centauri)" toggles in the panel.
- Time slider and pause appear inside a star system.
- Texture alignment keys (Milky Way): `[` `]` rotate, `,` `.` scale, `m` mirror.
- Click a star or planet name to open its notes; use Edit Records to change them.

## Textures

The repository needs the images listed in `frontend/textures/README.md`.
They are not covered by this project's license; see `CREDITS.md`.

## Project layout

See the tree in this repo: `main.py` (API), `ingest.py` (catalog loader),
`frontend/` (page, styles, scripts, textures), `tools/` (helper scripts).

## License

Code: MIT, see `LICENSE`. Textures and imported catalog data keep their original
licenses, see `CREDITS.md`.

## Credits

Full acknowledgements are in [CREDITS.md](CREDITS.md).