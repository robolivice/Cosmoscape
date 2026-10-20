# Cosmoscape 1.2.0

A release where the browser and the desktop app finally share everything: one backend,
one frontend, one database and one notes folder. The catalogue you build once now serves
both builds, so the web version and the desktop app show the same stars and the same notes.

The desktop loading screen also got the treatment it needed: it now waits for the galaxy
textures before it fades, and those textures are a fraction of the size they used to be,
so the app starts quicker and asks a lot less of your graphics card.

## Download
- Windows: Cosmoscape Setup 1.2.0.exe (see the Assets section below)
- macOS and Linux builds are planned. Until then you can build them from source, see
  the Desktop app section of the README.

SHA256: 7FACCFF76A193E16800208006F896C5A0EB09335064B64A009968C38867EF575

## Highlights
- One shared backend. A new `Cosmoscape-FS/` folder holds the FastAPI application, the
  catalog loader, the desktop only parts and the frontend. The web and desktop entry
  points are now thin wrappers around it, so there is a single copy of the code.
- One catalogue for both builds. The database, your notes and the download caches all
  live in the user data folder, so a catalogue built once serves the browser and the
  desktop app, and a note written in one is there in the other.
- A loading screen that actually covers the loading. It now stays up until the galaxy
  textures are on screen, so the view you land on is the finished view.
- Lighter galaxy textures: half the graphics memory and much faster to decode, so the
  app starts faster and behaves better on modest hardware.
- The installer is about 235 MB, about the same as 1.1.0. It would have been 268 MB
  if the galaxy textures had been left at their original size.
- Faster search. Search uses a trigram index with a LIKE fallback, answers are cached
  per database version and response bodies are compressed.
- The database is opened read-only and its connections can be dropped and reopened, so
  the desktop build can replace the catalogue file while the server is running. Windows
  refuses to replace a file that is still open.
- Wikipedia summaries can be pulled into the notes, one object at a time or in a batch,
  through `POST /api/wiki/{name}`, `POST /api/wiki/fill` and `GET /api/wiki/fill/status`.
- Notes are looked up by alias as well, so searching for "Sun" opens the note of "Sol".
- `GET /api/health` is back, so the desktop shell can tell when the backend is really up.

## Fixed
- The desktop loading screen no longer fades out before the galaxy textures have
  loaded. The galaxies were still arriving after the screen had gone, which left you
  looking at an empty sky for a few seconds. The loading screen now stays up until
  everything is on screen.
- The galaxy textures are much smaller and load far faster. The Andromeda texture was
  a 5884x5439 PNG: 33 MB on disk and 122 MB of graphics memory once decoded. It is now
  a 4096x3786 JPEG of 2.3 MB, and the Milky Way texture was scaled down from 5600x5600
  to 4096x4096. Both still hold more detail than your screen can show, but they use
  about half the graphics memory, which is what made the loading screen stall or go
  blank on weaker hardware.
- The page loader no longer waits on three.js's global loading manager, which stayed busy
  and left the web version sitting on its loading screen.
- Galaxy textures (PNG and JPG) now count towards the loading progress and report their
  own failures, instead of letting the loader hang.
- `GET /api/info/{name}` no longer writes a stub file for every name that is requested,
  and `PUT` limits a note to 200,000 characters and sanitises the file name.
- LIKE wildcards typed in the search box are escaped, so a `%` is no longer a wildcard.
- The server prints a warning and answers with 503 when the frontend folder is missing,
  instead of starting and serving nothing.
- The desktop shell's health check has a timeout, so a backend that stops answering can
  no longer freeze the app on the loading screen.
- In development, `npm start` now watches the shared `Cosmoscape-FS` folder as well and
  restarts the backend when a Python file changes there.

## Install
1. Download the installer from the Assets section below.
2. Run it and follow the prompts. You can install it over 1.0.0, 1.0.1 or 1.1.0 to update.
3. Windows may show a "Windows protected your PC" warning because the installer is not
   code-signed yet. Click "More info", then "Run anyway".

## Your data
The database and your notes are stored in your user data folder
(C:\Users\<you>\AppData\Local\Cosmoscape). Updating or uninstalling the app does not
delete them.

Starting with 1.2.0 the web version uses the same folder, so both builds show the same
catalogue and the same notes.

## Licensing
The app code is MIT. The bundled star database combines HYG and Wikipedia content,
which is CC BY-SA, with data from Gaia, the NASA Exoplanet Archive, SIMBAD and VizieR,
so it is distributed under CC BY-SA. Textures are from Solar System Scope (CC BY 4.0)
and NASA/JPL. Full credits are in CREDITS.md.

## Known limitations
- Unsigned installer, so Windows shows a security warning.
- Windows only for now.
- The Import Database button is hidden in this version.
- `python ingest.py --galaxies` on its own does nothing on a fresh database. Use
  `--curated --galaxies` or `--all`.
- Leaving a star system frees its geometry but not its textures yet, so memory grows
  slowly over a long session.
- See BUGS.md for the list of known issues.

Full changelog: CHANGELOG.md