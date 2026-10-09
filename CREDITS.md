# Credits

Universe Navigator uses data, images and libraries from the sources below.
Thank you to everyone who makes these available.

## Textures and images

- **Planet, Sun and ring textures** (`sun`, `mercury`, `venus`, `earth_day`,
  `earth_night`, `mars`, `jupiter`, `saturn`, `saturn_ring`, `uranus`, `neptune`):
  [Solar System Scope](https://www.solarsystemscope.com/textures/), licensed under
  [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Based on NASA imagery and
  elevation data.
- **Milky Way image** (`galaxy_top.jpg`): NASA/JPL-Caltech/R. Hurt (SSC-Caltech),
  [PIA10748, "Our Milky Way Gets a Makeover" (artist's concept)](https://www.jpl.nasa.gov/images/pia10748-our-milky-way-gets-a-makeover-artist-concept/).
  This is an artist's concept, not a photograph. Use of NASA/JPL imagery does not imply
  NASA endorsement of this project.

## Star and planet data (downloaded by the user with `ingest.py`)

No catalog data is distributed in this repository.

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

- [three.js](https://threejs.org/) r128 (MIT), loaded from jsDelivr
- [marked](https://github.com/markedjs/marked) 4.3.0 (MIT), loaded from jsDelivr
- [FastAPI](https://fastapi.tiangolo.com/) (MIT), [Uvicorn](https://www.uvicorn.org/)
  (BSD), [Pydantic](https://docs.pydantic.dev/) (MIT), [NumPy](https://numpy.org/) (BSD)
- [Space Mono](https://fonts.google.com/specimen/Space+Mono) via Google Fonts (SIL OFL)
- Search bar styling adapted from a component by Navarog21 on
  [Uiverse.io](https://uiverse.io/) (MIT)

## Licensing note

The project's own code is MIT (see `LICENSE`). That license does **not** cover the
textures or any catalog data you import; those remain under the licenses listed above.