"""
cosmoscape_fs - the shared backend of Cosmoscape.

    cosmoscape_fs/ingest.py   catalog loader, database schema and helpers
    cosmoscape_fs/app.py      the FastAPI application shared by the web and desktop builds
    cosmoscape_fs/desktop.py  seed install and database import (desktop build only)

The package lives in `Cosmoscape-FS/` at the repository root, next to the
shared `frontend/` folder. The app folders (`Cosmoscape-web/`,
`Cosmoscape-win/`) only contain thin entry points that call
`cosmoscape_fs.app.create_app()`.
"""
