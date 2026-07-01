# UFC AI Predictor

UFC fight predictor: 47 stats, math engine, Polymarket lines, honest grading ledger.

---

### One-time setup (per machine)

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
```

On Windows, use `python -m streamlit` (not `streamlit` directly) if the command is not found.

### One-time database seed (roster depth)

Pulls completed cards until **every division** in the pool has at least 20 fighters (starts at 10 cards, expands up to 60 if needed). Slow — let it run.

```bash
python -m src.ingest --last-cards
```

Cards already in the database are skipped. After **code or stat-definition changes**, refresh so snapshots recompute:

```bash
python -m src.ingest --last-cards --refresh
```

### Each new card

```bash
python -m src.ingest --upcoming
```

### Launch the app

```bash
python -m streamlit run app.py
```

### Typical weekly flow

1. `python -m src.ingest --upcoming` — pull the upcoming card
2. `python -m src.grade --log` — lock picks before the card starts
3. `python -m streamlit run app.py` — use the UI

### After a card finishes

```bash
python -m src.ingest --event-name "UFC 329"
python -m src.grade --grade
```

Replace `"UFC 329"` with the actual event name.

### Quick checks

```bash
python -m src.ingest --status
python -m src.grade --record
```

---

## Weekly workflow (each card)

### 0. First-time setup (roster depth)

Seed the database with the last 10 completed cards so percentile rankings use a real division pool:

```bash
python -m src.ingest --last-cards
```

You only need to run this once (or again if you want to refresh historical depth). Cards already in the database are skipped; fighters are upserted when a card is ingested.

### 1. Pull stats for the upcoming card

```bash
python -m src.ingest --upcoming
```

Or by name:

```bash
python -m src.ingest --event-name "UFC 329"
```

### 2. Lock picks to the ledger (before the card starts)

```bash
python -m src.grade --log
```

Run this **once per card**, before the first fight. It saves every pick permanently (win %, tier, Polymarket line, edge). Running it again skips fights already logged.

### 3. Launch the app

```bash
python -m streamlit run app.py
```

This opens the UI in your browser. Use it to:

- View **Live Record** (wins, losses, hit rate, units)
- Browse the **card overview** and **fight analyzer**
- See Polymarket lines, edge, EV, and half-Kelly stakes
- Optionally **Lock picks** or **Grade pending** from the sidebar (same as the CLI commands)

**CLI alternative** (terminal only, no UI):

```bash
python -m src.predict
```

### 4. After the card finishes

Re-ingest the completed event so fight results (winners) are in the database:

```bash
python -m src.ingest --event-name "UFC 329"
```

Then grade your locked picks:

```bash
python -m src.grade --grade
```

Check your record:

```bash
python -m src.grade --record
```

Or refresh the Streamlit app — the **Live Record** box updates automatically.

---

## Quick reference

| When | Command |
|------|---------|
| **First time** — seed last 10 cards | `python -m src.ingest --last-cards` |
| New card — pull stats | `python -m src.ingest --upcoming` |
| Before bell — lock picks | `python -m src.grade --log` |
| **Launch UI** | `python -m streamlit run app.py` |
| After card — pull results | `python -m src.ingest --event-name "UFC XXX"` |
| After card — grade picks | `python -m src.grade --grade` |
| View record | `python -m src.grade --record` |

---

## Other commands

```bash
# Database summary
python -m src.ingest --status

# Seed roster from last N completed cards (default 10)
python -m src.ingest --last-cards
python -m src.ingest --last-cards 15

# Predict one fight in terminal
python -m src.predict --fight McGregor

# Ingest by UFCStats URL
python -m src.ingest --event-url "http://www.ufcstats.com/event-details/..."
```

---

## Architecture

- **`config/stats.yaml`** — 47 math inputs → 10 categories
- **`config/research_rules.yaml`** — context rules (max ±5% adjustment)
- **`config/model.yaml`** — sigmoid temperature, confidence tiers
- **`config/betting.yaml`** — edge threshold, half-Kelly cap
- **`data/ufc_ai.db`** — SQLite (stats, predictions, grades)

| Table | Contents |
|-------|----------|
| `events` | Card name, date, location |
| `fighters` | Profile (height, reach, stance, DOB) |
| `fights` | Matchups + results after card |
| `fighter_stat_snapshots` | 47 stats per fighter per ingest |
| `predictions` | Locked picks (Step 7 ledger) |

---

## Notes

- **Polymarket** lines load automatically in the app (no manual odds entry).
- UFCStats uses bot protection; ingest runs headless Chromium via Playwright.
- Missing stats are flagged, never silently treated as zero.
- Picks are locked once per fight — the ledger cannot be rewritten.
