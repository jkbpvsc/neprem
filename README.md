# Nepremicnine listing notifier

Simple scraper that checks for new listings on `https://www.nepremicnine.net/` and notifies you when new ones appear.

## Setup

1. Create a virtualenv and install requirements:

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

If you enable Playwright, install the browser bundle:

```
python3 -m playwright install chromium
```

2. Copy `.env.example` to `.env` and fill in values.

```
cp config.example.env .env
```

## Run once

```
python3 neprem_scraper.py
```

## Run continuously

```
python3 neprem_scraper.py --loop --interval 300
```

## Notes

- By default, notifications print to stdout. If SMTP settings are provided, emails are sent.
- You can adjust selectors in `.env` if the site layout changes.
- If you hit Cloudflare bot checks, set `USE_PLAYWRIGHT=1` in `.env`.
# neprem
# neprem
