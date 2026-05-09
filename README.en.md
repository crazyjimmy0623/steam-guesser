# steam-guesser

> English · [繁中](README.md)

Look at the game's trailer, screenshots, and metadata — guess which review-count bucket it falls into. A Fermi-estimation game for Steam.

## Play

**https://crazyjimmy0623.github.io/steam-guesser/**

## How to play

Two modes:
- **Time Attack** — 3-minute countdown, race for high score
- **Endless** — no clock, end the run yourself with the END RUN button

Each round you see a game's trailer + screenshots + description + genre + developer + price, and pick one of 4 review-count buckets:

| Bucket | Range |
| --- | --- |
| A | 10 – 100 |
| B | 100 – 1K |
| C | 1K – 10K |
| D | 10K – 50K |

Scoring:

| Distance from correct | Points |
| --- | --- |
| Perfect match | +100 (× combo) |
| Adjacent bucket | +50 |
| Further | 0 |

Consecutive perfects activate a combo multiplier (2 in a row → ×1.5, 3 → ×2, 5+ → ×3); breaks reset to ×1. Keyboard shortcuts: `A`/`B`/`C`/`D` pick buckets, `Enter` advances phase.

## Architecture

Pure static frontend + GitHub Actions to pre-bake game data + Cloudflare Worker for the global leaderboard:

```
steam-guesser/
├── docs/                       # served as the GitHub Pages root
│   ├── index.html
│   ├── style.css               # full CSS (theme, CRT, curtain, entry animations)
│   ├── app.js                  # state machine (idle/playing/revealed/ended) + interaction
│   ├── modules/
│   │   ├── i18n.js             # 繁中 / EN translation dict
│   │   ├── bgm.js              # WebAudio ambient drone
│   │   ├── particles.js        # mouse-grid particle background
│   │   ├── timer.js            # countdown widget + onTick callback
│   │   ├── sfx.js              # hover/press/clock/tick/score SFX
│   │   ├── fx.js               # perfect flash, miss shake, TIME UP, toast
│   │   └── colorize.js         # extract dominant color from header → CSS variable
│   ├── data/
│   │   ├── games.json          # CI-baked: ~3000 games × bilingual
│   │   ├── version.txt         # cachebust hash
│   │   └── config.json         # leaderboard_api setting
│   └── assets/favicon.svg
├── scripts/
│   ├── build_pool.py           # Python script that bakes games.json
│   └── requirements-build.txt  # requests, tenacity
├── worker/
│   ├── index.js                # Cloudflare Worker — global leaderboard API
│   ├── wrangler.toml
│   └── README.md               # Worker deployment guide
└── .github/workflows/
    └── build-pool.yml          # weekly auto-bake + commit
```

Data flow: GitHub Actions calls Steam APIs (SteamSpy + Store + Reviews) weekly → bakes `docs/data/games.json` → push to master → GitHub Pages auto-republishes. Frontend is fully static; the browser never touches Steam APIs directly (avoids CORS issues).

## Local development

```bash
# 1. Bake a small dev dataset (~50 games × EN only, takes ~30s)
pip install -r scripts/requirements-build.txt
python scripts/build_pool.py --limit 50

# 2. Serve locally
cd docs
python -m http.server 8080
# Open http://localhost:8080
```

`docs/data/games.json` (the full ~3000-game bilingual file) is written by CI; `games.dev.json` is the local dev counterpart and is gitignored.

## Deploying to GitHub Pages (one-time setup)

1. Settings → Pages → Source = "Deploy from a branch"
2. Branch = `master`, Folder = `/docs`
3. Save → wait ~1 minute for first deploy
4. Actions tab → manually run `build-pool` to bake the real 3000-game dataset

Subsequent runs trigger automatically every Sunday at 17:00 UTC; you can also dispatch manually any time from the Actions page.

## Global leaderboard (Cloudflare Worker)

Follow [`worker/README.md`](worker/README.md) — five steps to deploy a free Cloudflare Worker (KV-backed, with IP rate-limiting and validation), then put its URL into `docs/data/config.json`'s `leaderboard_api` field.

If you skip the worker, the ended screen still shows "Personal Best" (local top 10), "Session Games" (with Steam store links), achievements, and the share button.

## Data sources

- Game pool: SteamSpy `all` endpoint (10 pages ≈ 10,000 games), bucketed by estimated review count, then fairly sampled at 750 per bucket
- Per-game details / reviews: Steam Store API (`appdetails` + `appreviews`), bilingual (`l=english` + `l=tchinese`)
- Filter: review count must be in `[10, 50000]` (matching [steamle.com](https://steamle.com/)'s bucket boundaries)

Player-side data (history, best score, mode preference, handle) is stored in browser localStorage (`sg_history` / `sg_best` / `sg_mode` / `sg_player_name`, etc.) and never leaves the device.

## License

[MIT](LICENSE) © 2026 crazyjimmy0623

## Disclaimer

Steam Review Guesser is a fan-made guessing game and is **not affiliated with, endorsed by, sponsored by, or specifically approved by Valve Corporation**. "Steam" and the Steam logo are trademarks of Valve Corporation.

Game names, descriptions, prices, release dates, genres, developers, header images, screenshots, and trailers are sourced from the public [Steam Web API](https://store.steampowered.com/api) and [SteamSpy](https://steamspy.com), and remain the property of their respective publishers and Valve. They are displayed here for the educational/entertainment purpose of a guessing game, with each entry linking back to its official Steam store page.

### Privacy

When you submit to the global leaderboard, the Cloudflare Worker KV stores:
**your chosen handle (1–16 characters) + score + timestamp**.

No email, IP, cookie, or browser data is retained (the IP is briefly used for the 60-second rate-limit cooldown only and is not persisted). Local statistics (history, best score, mode preference, handle) are only stored in your browser's localStorage and never leave your device.
