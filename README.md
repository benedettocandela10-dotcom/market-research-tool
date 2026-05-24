# Market Research Tool

Collect market signals from Reddit, Etsy, and eBay for your niche keywords, export a unified CSV, and explore results in a Streamlit dashboard.

## Setup

### Reddit (approval required — not instant)

Reddit’s [Responsible Builder Policy](https://support.reddithelp.com/hc/en-us/articles/42728983564564-Responsible-Builder-Policy) requires **explicit approval before** you can create an app or use the Data API. If you see that policy message at [prefs/apps](https://www.reddit.com/prefs/apps), you must apply first — creating an app there will not work until approved.

**Step 1 — Request non-commercial Data API access**

1. Read the [Responsible Builder Policy](https://support.reddithelp.com/hc/en-us/articles/42728983564564-Responsible-Builder-Policy).
2. Submit a request via Reddit’s signup form:  
   [Request Data API access (non-commercial)](https://support.reddithelp.com/hc/en-us/requests/new?ticket_form_id=14868593862164)
3. In the form, describe your use case honestly, for example:
   - *Personal market research tool; search public posts by keyword in a few hobby subreddits; export to local CSV; no resale, no AI training, low volume.*
4. Wait for Reddit’s approval email (timeline varies; often days, sometimes longer).

Official reference: [Developer Platform & Accessing Reddit Data](https://support.reddithelp.com/hc/en-us/articles/14945211791892-Developer-Platform-Accessing-Reddit-Data)

**Step 2 — After approval, create the script app**

1. Go to [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps) (should work once approved).
2. **Create app** → type **script**, redirect URI `http://localhost:8080`.
3. Copy **client ID** and **secret** into `.env`.

**Step 3 — Add credentials to `.env`**

PRAW needs a **script** app plus your Reddit account (password grant):

- `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`
- `REDDIT_USERNAME`, `REDDIT_PASSWORD`
- `REDDIT_USER_AGENT` = `market_research/1.0 by u/YourUsername`

**While waiting for Reddit:** use Etsy + eBay only:

```bash
python market_collector.py --keywords "your niche" --no-reddit
```

Or use Trends MCP for Reddit *demand* signals (not post search): set `TRENDS_API_KEY` and run with `--trends`.

---

1. Copy the environment template:

   ```bash
   copy config.example.env .env
   ```

2. Fill in API credentials in `.env` (see comments in `config.example.env` for where to get each key).

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

## Collect data

```bash
python market_collector.py --keywords "1:144 decal" "mechanical keyboard switch"
```

Options:

| Flag | Description |
|------|-------------|
| `--keywords` | One or more search terms (required) |
| `--subs` | Reddit subreddits (default: ScaleModeling, MechanicalKeyboards, fountainpens, watchrepair) |
| `--limit` | Max results per keyword per source (default: 20) |
| `--reddit` / `--no-reddit` | Enable or disable Reddit |
| `--etsy` / `--no-etsy` | Enable or disable Etsy |
| `--ebay` / `--no-ebay` | Enable or disable eBay |
| `--trends` | Also fetch Trends MCP demand scores (requires `TRENDS_API_KEY`) |

Output is written to `output/market_data_YYYYMMDD_HHMM.csv`.

## Browse results

```bash
streamlit run dashboard.py
```

Use the sidebar to filter by platform, keyword, price range, and engagement. Sort columns and view summary stats.

## Trends MCP (optional)

With `TRENDS_API_KEY` set, run:

```bash
python trends_collector.py --keywords "air fryer" --sources "google shopping" amazon
```

Or pass `--trends` to the main collector to append trend scores to the export.

## Project layout

```
market_collector.py   # Main collector (Reddit, Etsy, eBay)
trends_collector.py   # Optional Trends MCP demand layer
dashboard.py          # Streamlit UI
output/               # Generated CSV files (gitignored)
```
