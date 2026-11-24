# cine.ar-chivador

> [!NOTE]
> Archived: published for conservation purposes. Not maintained, and likely
> broken by later changes to cine.ar.

Tools for archiving films from [cine.ar](https://play.cine.ar):

- `archivador.py`: Playwright-based fetcher that injects an auth token and grabs the stream URL.
- `cine_ar_enhanced.py` / `cine_ar_enhanced/`: direct downloader via the Odeon player API + ffmpeg.
- `download_movie.py`: simple HLS downloader.
- `cinearbash/`: modified copy of [GrafoVolaverunt/cinearbash](https://github.com/GrafoVolaverunt/cinearbash) (see its LICENSE).

Credentials are read from the environment (`CINEAR_TOKEN`, `CINEAR_PERFIL`) or,
for `cinearbash`, from `cinear.cfg` (see `cinear.cfg.example`).
