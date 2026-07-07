# Knowledge Vault

Save reels, videos, and articles and get back a short, useful note — not a
transcript. Everything runs **locally on your own PC** using a free local AI
(no subscriptions, no cloud AI, nothing you save ever leaves your computer
except an optional link sent from your phone).

Notes are saved as plain Markdown files in an [Obsidian](https://obsidian.md)
vault, automatically organized into folders, deduplicated, and searchable —
plus a knowledge graph so you can see how everything connects.

## What you need

- **Windows 10 or 11.**
- About **10 GB free disk space** and **10–15 minutes** the first time (the
  setup downloads a local AI model).
- A reasonably modern PC. It works on a laptop with no dedicated graphics
  card too — it'll just be slower per note.

No coding knowledge needed — everything below is a double-click.

## Quick start

1. Click the green **Code** button at the top of this page → **Download ZIP**.
2. Extract the ZIP anywhere (e.g. your Desktop).
3. Open the extracted folder and double-click **`Setup Knowledge Vault.bat`**.
   Follow what it prints — it installs everything needed (including the free
   local AI, [Ollama](https://ollama.com)) and creates your vault folder.
4. Double-click **`Start Knowledge Vault.bat`**. A dashboard opens in your
   browser at `http://localhost:8765` — you're ready to save your first link.

Your notes end up in a **`Knowledge Vault`** folder next to the app folder.
Open that folder in Obsidian any time to browse your notes directly.

## Using it

- **Add** — paste a link (Instagram reel, TikTok, YouTube, an article) or any
  raw text. It's processed automatically and shows up in **Recently added**.
- **Browse** / **Search** — your notes, organized into folders that grow on
  their own as you save more.
- **Graph** — a visual map of your notes and categories, similar to
  Obsidian's graph view.
- **Phone capture (optional)** — after first setup, open the file
  `PHONE-SETUP.md` that appears in this folder. It walks you through a free,
  10-minute setup (a Cloudflare account) so you can share a reel from your
  phone with one tap, even while your PC is off — it'll be waiting for you
  next time you turn the PC on.

## Privacy

All AI analysis (reading the video/article and writing the note) happens on
your PC using Ollama — nothing is sent to any AI company. The only thing that
ever leaves your PC is the link/text you share from your phone (which needs
somewhere to wait until your PC turns on) and the pages you ask it to fetch.

## If something goes wrong

- **"Ollama is not running"** on the dashboard → open the Ollama app from
  your Start menu, then it resumes automatically.
- **Setup can't find Python** → install [Python 3.12](https://www.python.org/downloads/)
  first (tick "Add python.exe to PATH" during install), then rerun setup.
- **Port already in use** → close any other copy of Knowledge Vault that
  might already be running, or change `"port"` in `config.json` (created
  after first setup) and restart.
- Re-running `Setup Knowledge Vault.bat` any time is safe — it only fixes or
  fills in what's missing.
