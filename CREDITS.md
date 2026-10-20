# Credits

Cosmoscape uses data, images and libraries from the sources below.
Thank you to everyone who makes these available.

## Textures and images

- **Planet, Sun and ring textures** (`sun`, `mercury`, `venus`, `earth_day`,
  `earth_night`, `mars`, `jupiter`, `saturn`, `saturn_ring`, `uranus`, `neptune`):
  [Solar System Scope](https://www.solarsystemscope.com/textures/), licensed under
  [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Based on NASA imagery and
  elevation data. Converted to KTX2 for this project.
- **Milky Way image** (`galaxy_top.jpg`): NASA/JPL-Caltech/R. Hurt (SSC-Caltech),
  [PIA10748, "Our Milky Way Gets a Makeover" (artist's concept)](https://www.jpl.nasa.gov/images/pia10748-our-milky-way-gets-a-makeover-artist-concept/).
  This is an artist's concept, not a photograph. Use of NASA/JPL imagery does not imply
  NASA endorsement of this project.

## Star and planet data

This repository contains no catalog data. `ingest.py` downloads it from the sources
below, and the premade Windows installer includes a database built from the same
sources.

HYG and Wikipedia content is licensed under CC BY-SA, so the bundled database is
distributed under CC BY-SA, with the credits below. The other sources keep their own
terms and acknowledgements. Curated entries and generated galaxy stars are original to
this project, and the generated stars are placeholders, not real catalog data.

- **Gaia DR3**: This work has made use of data from the European Space Agency (ESA)
  mission Gaia (https://www.cosmos.esa.int/gaia), processed by the Gaia Data Processing
  and Analysis Consortium (DPAC, https://www.cosmos.esa.int/web/gaia/dpac/consortium).
- **HYG Database** by David Nash (astronexus):
  https://github.com/astronexus/HYG-Database, licensed under CC BY-SA.
- **NASA Exoplanet Archive**: This research has made use of the NASA Exoplanet Archive,
  which is operated by the California Institute of Technology, under contract with the
  National Aeronautics and Space Administration under the Exoplanet Exploration Program.
- **SIMBAD**: This research has made use of the SIMBAD database, operated at CDS,
  Strasbourg, France (Wenger et al. 2000, A&AS 143, 9).
- **VizieR**: This research has made use of the VizieR catalogue access tool, CDS,
  Strasbourg, France (Ochsenbein et al. 2000, A&AS 143, 23). Open cluster data:
  Cantat-Gaudin et al. 2020, A&A 640, A1.
- **Wikipedia**: article summaries written by `ingest.py --wiki` are text from Wikipedia,
  licensed under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).
  Each generated record links back to its source article.
- **astroquery**: Ginsburg et al. 2019, AJ 157, 98. **Astropy**: Astropy Collaboration.

## Software and fonts

Bundled with the app (stored in `Cosmoscape-FS/frontend/vendor/` and `Cosmoscape-FS/frontend/fonts/`, no CDN needed):

- [three.js](https://threejs.org/) r147 (MIT)
- [marked](https://github.com/markedjs/marked) (MIT)
- [Space Mono](https://fonts.google.com/specimen/Space+Mono) (SIL OFL)
- [Basis Universal](https://github.com/BinomialLLC/basis_universal) transcoder (Apache-2.0),
  [ktx-parse](https://github.com/donmccurdy/ktx-parse) (MIT) and
  [zstddec](https://github.com/donmccurdy/zstddec) (MIT), used by three.js `KTX2Loader`

Used to run and build:

- [FastAPI](https://fastapi.tiangolo.com/) (MIT), [Uvicorn](https://www.uvicorn.org/)
  (BSD), [Pydantic](https://docs.pydantic.dev/) (MIT),
  [platformdirs](https://github.com/tox-dev/platformdirs) (MIT),
  [NumPy](https://numpy.org/) (BSD, used by `ingest.py` only)
- [Electron](https://www.electronjs.org/) (MIT) and
  [electron-builder](https://www.electron.build/) (MIT) for the desktop app
- [PyInstaller](https://pyinstaller.org/) (GPL-2.0 with a bootloader exception that
  allows bundling non-GPL apps) for the desktop backend
- Search bar styling adapted from a component by Navarog21 on
  [Uiverse.io](https://uiverse.io/) (MIT)

## Licensing note

The project's own code is MIT (see `LICENSE`). That license does **not** cover the
textures or the star data, including the database in the premade installer. Those remain
under the licenses listed above.