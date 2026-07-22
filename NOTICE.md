# Legal notice & intellectual property disclaimer

This is an **unofficial, non-commercial fan project**. It is not affiliated with, endorsed by,
sponsored by, or in any way officially connected with **Bushiroad Co., Ltd.**, the publisher of
**Weiß Schwarz**, or with the copyright holders of the anime/manga/game franchises whose
characters appear on Weiß Schwarz cards.

## What this repository is

A research pipeline that reverse-engineers the **power cost** Bushiroad's card designers assign to
each printed ability, plus a static, read-only lookup website built on top of that analysis. Both
are **free, open-source (MIT-licensed code, see [`LICENSE`](LICENSE))**, run with **no advertising,
no paywall, and no monetization of any kind**, and exist purely as a reference tool for players and
custom-card designers.

## What data it contains, and where it comes from

| Data | Source | Notes |
|---|---|---|
| Japanese card list (names, stats, ability text) | Bushiroad's own official public card-list endpoint (`ws-tcg.com`) | The primary source of truth — data Bushiroad itself publishes for anyone to browse |
| Official English card text | Bushiroad's official English card list (via the community-maintained [`CCondeluci/WeissSchwarz-ENG-DB`](https://github.com/CCondeluci/WeissSchwarz-ENG-DB) mirror) | Reproduces Bushiroad's own official EN localization |
| English names for cards with no official EN release | [heartofthecards.com](https://www.heartofthecards.com/) (a long-running, publicly operated Weiß Schwarz fan translation resource) | Community translation, credited to its source |
| English text for cards that never released in English at all | An unofficial fan-made Weiß Schwarz simulator's local card data | The only sourcing step once removed from an official channel; used strictly for text (no code or assets of the simulator itself are redistributed) |
| Official rulebooks (`reference/`, `pipeline/sources/`) | Bushiroad's own freely-distributed Comprehensive Rules / Quick Manual PDFs | TCG rulebooks are routinely published free by the game's own company so players can learn the game |

**What it deliberately does NOT contain:** card **artwork or images**. No card image is ever
committed to this repository, even locally — the entire product is text and structured metadata
only.

## Why this is believed to be a permitted use

- Bushiroad's own published guidelines (`en.bushiroad.com/company/legal/`) permit non-commercial
  fan use of its game assets, without needing prior approval, provided the material isn't sold,
  isn't altered in a misleading way, and is credited.
- This project only reproduces **text/metadata**, not artwork — the category of content Bushiroad's
  own guidelines are most permissive about.
- Long-standing precedent: the official-EN mirror and the fan-translation site this project reads
  from have operated publicly, without incident, for years.
- The core deliverable — the power-cost model — is a **transformative analytical work**, not a
  copy of the game: it measures a pattern in the designers' choices, it does not republish the game
  itself.

This is a good-faith reading of a public policy, made by the project's maintainer — **it is not a
legal opinion**, and Bushiroad's position could differ from what's summarized here.

## Attribution

Weiß Schwarz, all card names, ability text, character names, and any other game content referenced
here are © **Bushiroad Co., Ltd.**, and the copyright of the respective anime/manga/game licensors
whose characters and works are depicted on those cards. All rights to that content remain with
their original owners.

## Takedown / correction requests

If you are a rights holder (Bushiroad or any licensor) and believe any content in this repository
should not be here, or if anything here is factually wrong, please **open an issue on this GitHub
repository** — that is the only contact channel for this project. Any legitimate request will be
acted on promptly (removal or correction, as appropriate); this project has no interest in a
dispute over content that a rights holder wants taken down.
