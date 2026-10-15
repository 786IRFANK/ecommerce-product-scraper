# E-commerce Product Scraper (Amazon, Reliance Digital, Croma, Flipkart)

Scrapes product details from Amazon, Reliance Digital, Croma and Flipkart and stores them in a CSV file. The scraper works in two stages:

1. **Collect product URLs** from search or category pages and save them to the CSV.
2. **Visit each product URL**, extract the price (and other details), and update the same CSV.

---

## Table of Contents

- [Overview](#overview)
- [How It Works](#how-it-works)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [CSV Schema](#csv-schema)
- [Site-Specific Notes](#site-specific-notes)
- [Scheduling](#scheduling)
- [Error Handling and Retries](#error-handling-and-retries)
- [Troubleshooting](#troubleshooting)
- [Legal and Ethical Notes](#legal-and-ethical-notes)

---

## Overview

| Item | Detail |
|------|--------|
| **Sources** | Amazon.in, Reliance Digital, Croma, Flipkart |
| **Output** | `products.csv` |
| **Stage 1** | Search keywords / category pages → product URLs |
| **Stage 2** | Product URLs → price and details, written back to the CSV |
| **Language** | Python 3.10+ |

## How It Works

```
 keywords / category URLs
          │
          ▼
┌───────────────────────┐
│ Stage 1: URL collector│  one collector per site
└──────────┬────────────┘
           ▼
   products.csv  (site, keyword, product_url, status=pending)
           │
           ▼
┌───────────────────────┐
│ Stage 2: Price scraper│  reads pending rows, opens each URL
└──────────┬────────────┘
           ▼
   products.csv  (price, title, availability, scraped_at, status=done)
```

1. **Stage 1** takes the keywords or category URLs from `config.yaml` and, for each site, loads the search results pages and extracts the product links. New links are appended to `products.csv` with `status=pending`. Existing URLs are skipped, so the CSV never has duplicates.
2. **Stage 2** reads every row that is `pending` (or older than the refresh window), opens the product URL, extracts the price and other details, and updates that row in place with `status=done`.
3. Failed URLs are marked `status=failed` with the error message so they can be retried.

## Project Structure

```
.
├── scraper/
│   ├── main.py              # CLI entry point (collect / scrape / all)
│   ├── collect_urls.py      # Stage 1 orchestration
│   ├── scrape_prices.py     # Stage 2 orchestration
│   ├── csv_store.py         # Read / append / update CSV safely
│   ├── utils.py             # Price parsing, user agents, delays, retries
│   └── sites/
│       ├── amazon.py
│       ├── reliance_digital.py
│       ├── croma.py
│       └── flipkart.py
├── config.yaml              # Keywords, sites, delays, output path
├── products.csv             # Output (created on first run)
├── requirements.txt
└── README.md
```

> Adjust file names to match your repository layout.

## Prerequisites

- Python 3.10 or newer
- Google Chrome or Chromium (used by Playwright for JavaScript-rendered pages)
- Optional: a rotating proxy service if you scrape at higher volume

## Installation

```bash
git clone <repository-url> product-scraper
cd product-scraper

python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

pip install -r requirements.txt
playwright install chromium
```

Example `requirements.txt`:

```
playwright
beautifulsoup4
lxml
pandas
pyyaml
tenacity
python-dotenv
```

## Configuration

Edit `config.yaml`:

```yaml
output_csv: products.csv

sites:
  - amazon
  - flipkart
  - croma
  - reliance_digital

keywords:
  - "iphone 15"
  - "samsung galaxy s24"

max_pages_per_keyword: 3        # search result pages to scan per site
max_products_per_keyword: 50    # cap per site per keyword

delay_seconds:
  min: 3
  max: 8

refresh_after_hours: 24         # re-scrape rows older than this
headless: true
timeout_seconds: 30
max_retries: 3

# Optional
proxy: ""                       # e.g. http://user:pass@host:port
```

Optional `.env` for secrets (for example a proxy):

```env
PROXY_URL=
```

## Usage

Run both stages:

```bash
python -m scraper.main all
```

Run each stage separately:

```bash
# Stage 1: collect product URLs
python -m scraper.main collect

# Stage 2: fetch prices for pending URLs and update the CSV
python -m scraper.main scrape
```

Useful options:

```bash
# Only one site
python -m scraper.main all --site flipkart

# Re-scrape every row regardless of age
python -m scraper.main scrape --force

# Retry rows that failed earlier
python -m scraper.main scrape --retry-failed

# Override keyword from the command line
python -m scraper.main collect --keyword "oneplus 12"
```

## CSV Schema

| Column | Description |
|--------|-------------|
| `site` | `amazon`, `flipkart`, `croma` or `reliance_digital` |
| `keyword` | Search keyword that produced the URL |
| `product_url` | Canonical product page URL (unique key) |
| `title` | Product name |
| `price` | Current selling price as a number (INR, no symbols) |
| `mrp` | List price / MRP, if shown |
| `currency` | `INR` |
| `availability` | `in_stock`, `out_of_stock` or `unknown` |
| `rating` | Average rating, if shown |
| `status` | `pending`, `done` or `failed` |
| `error` | Error message for failed rows |
| `collected_at` | When the URL was collected |
| `scraped_at` | When the price was last fetched |

Example:

```csv
site,keyword,product_url,title,price,mrp,currency,availability,rating,status,error,collected_at,scraped_at
amazon,iphone 15,https://www.amazon.in/dp/XXXXXXXXXX,Apple iPhone 15 (128 GB),65999,79900,INR,in_stock,4.5,done,,2026-10-15T10:00:00,2026-10-15T10:05:12
flipkart,iphone 15,https://www.flipkart.com/.../p/itmXXXX,Apple iPhone 15 (128 GB),64999,79900,INR,in_stock,4.6,pending,,2026-10-15T10:01:00,
```

The CSV is written atomically (temp file, then rename) so an interrupted run does not corrupt it.

## Site-Specific Notes

| Site | URL collection | Price extraction | Notes |
|------|----------------|------------------|-------|
| **Amazon.in** | Search results (`/s?k=`), links containing `/dp/` | Price block on the product page | Strips tracking parameters, keeps `/dp/<ASIN>`. Aggressive bot detection; CAPTCHA pages are detected and the row is retried later |
| **Flipkart** | Search results (`/search?q=`), links containing `/p/` | Price element on the product page | Class names change often; prefer JSON-LD (`application/ld+json`) when present |
| **Croma** | Search results page | Price element or JSON-LD on the product page | Content loads dynamically, so Playwright is required |
| **Reliance Digital** | Search results page | Price element or JSON-LD on the product page | Content loads dynamically, so Playwright is required |

Selectors are kept in each site's module so a layout change only needs a fix in one place. Where available, structured data (JSON-LD / embedded JSON) is preferred over CSS selectors because it is more stable.

## Scheduling

Run daily to keep prices fresh (cron example, 06:00):

```cron
0 6 * * * cd /path/to/product-scraper && /path/to/product-scraper/venv/bin/python -m scraper.main scrape >> scraper.log 2>&1
```

Run Stage 1 less often (for example weekly) to pick up new products:

```cron
0 5 * * 1 cd /path/to/product-scraper && /path/to/product-scraper/venv/bin/python -m scraper.main collect >> scraper.log 2>&1
```

## Error Handling and Retries

- Random delay between requests (`delay_seconds`) and a rotating user agent.
- Automatic retries with exponential backoff (`max_retries`).
- CAPTCHA / block page detection: the row stays `pending` and is retried on the next run.
- Missing price: the row is saved with an empty `price` and `availability=out_of_stock` or `unknown`.
- Every failure is logged with the URL and reason, and stored in the `error` column.

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| Empty `price` for many rows | Site layout changed | Update selectors in `scraper/sites/<site>.py` or use JSON-LD |
| CAPTCHA or "Access denied" | Too many requests from one IP | Increase delays, lower volume, use a proxy |
| Few or no URLs collected | Search page not fully loaded | Increase `timeout_seconds`, run with `headless: false` to inspect |
| Duplicate products | URL not normalized | Check canonicalization in `utils.py` (strip tracking params) |
| `playwright` browser not found | Browsers not installed | Run `playwright install chromium` |
| Price like `65,999.00` parsed wrongly | Formatting differences | Use the shared price parser in `utils.py` |
| CSV locked or corrupt (Windows) | File open in Excel | Close the file before running |

## Legal and Ethical Notes

- Review each site's Terms of Service and `robots.txt` before scraping. Several of these sites restrict automated access.
- Where available, prefer official APIs, such as the Amazon Product Advertising API or affiliate and partner feeds, for production use.
- Keep request rates low and do not bypass logins, paywalls or CAPTCHAs.
- Use the data only for purposes you are permitted to, and do not republish it without checking the sites' terms.
