# cyberday-hunter

Scans Sodimac (fast tier) every 15 minutes for deals matching
`config/watchlist.json`, filters out fake "was $X" discounts by tracking each
item's real price history, and pushes qualifying deals to Telegram.

## Setup

1. `pip install -r requirements.txt`
2. `playwright install chromium`
3. Edit `config/watchlist.json` with your categories/keywords/thresholds.
4. Copy your own `.env` with `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` for local runs,
   or set them as GitHub Actions repo secrets for CI (`.github/workflows/fast.yml`).

## Run locally

```
python main_fast.py
```

## Scope

This repo currently covers one source (Sodimac, fast tier). See
`docs/superpowers/specs/2026-10-01-cyberday-hunter-design.md` for the full
multi-site design and the hard-tier (Falabella/Paris/Ripley) plan still to come.
