# scraper-2.0

Multi-ATS job scraper that fetches listings from Greenhouse, Lever, Ashby, Workday, iCIMS, and BambooHR, enriches them with skills and salary data, scores them against your resume, and stores results in a local SQLite database.

## Supported ATS Platforms

| Platform   | Companies configured                          |
|------------|-----------------------------------------------|
| Greenhouse | Stripe, Notion, Figma, Airbnb, Dropbox        |
| Lever      | Netflix, Lyft, Reddit, Twitch, Coinbase       |
| Ashby      | Anthropic, Linear, Retool, Vercel, Brex       |
| Workday    | Microsoft, Amazon, Google, Meta, Apple        |

## Setup

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Usage

**Scrape all companies:**
```bash
python -m src.cli scrape
```

**Scrape a single ATS:**
```bash
python -m src.cli scrape --ats greenhouse
```

**Scrape a single company:**
```bash
python -m src.cli scrape --ats ashby --company anthropic
```

**List top matches from the database:**
```bash
python -m src.cli list-jobs --min-score 0.3
python -m src.cli list-jobs --remote-only
```

## Resume

Edit `data/resume.txt` with your actual resume content. Skills are extracted automatically and used for scoring.

## Project Structure

```
scraper-2.0/
├── config/companies.yaml      # ATS company registry
├── src/
│   ├── fetchers/              # One module per ATS platform
│   ├── core/                  # Models, normalizer, SQLite DB layer
│   ├── enrichment/            # Skills & salary extraction
│   ├── scoring/               # Resume match scoring
│   └── cli.py                 # Typer CLI entrypoint
├── data/
│   ├── resume.txt             # Your resume (plain text)
│   └── jobs.db                # Auto-created SQLite database
└── requirements.txt
```

## Scoring

Jobs are scored 0–1 using:
- **Jaccard similarity** on extracted skill tags (fast, no model needed)
- **Semantic similarity** via `sentence-transformers` (all-MiniLM-L6-v2) when a description is available

Weights: 40% skill overlap + 60% semantic similarity.
