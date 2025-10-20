# BookSeries.org Scraper

A Python script to scrape author and book series information from [bookseries.org](https://www.bookseries.org).

## Features

- Scrapes complete list of 1,300+ authors
- Extracts book series information for each author
- Includes author biographies
- Captures book titles, series organization, and book counts
- Respects server with configurable delays between requests
- Saves progress periodically to prevent data loss
- Exports data to JSON format

## Requirements

```bash
pip install requests beautifulsoup4
```

## Usage

### Scrape Authors List Only (Fast)

Get just the list of authors without fetching individual series:

```bash
python3 scripts/scrape_bookseries_org.py --authors-only --output authors_list.json
```

### Scrape Everything (Full Data)

Scrape all authors and their complete series information:

```bash
python3 scripts/scrape_bookseries_org.py --output bookseries_complete.json
```

**Note:** This will take approximately 20-30 minutes to complete (1,303 authors × 1 second delay).

### Test with Limited Authors

Test the scraper with just a few authors first:

```bash
python3 scripts/scrape_bookseries_org.py --limit 10 --output test.json
```

### All Command-Line Options

```bash
python3 scripts/scrape_bookseries_org.py [options]

Options:
  --limit N          Limit to first N authors (for testing)
  --delay SECONDS    Delay between requests (default: 1.0)
  --output FILE      Output JSON file (default: bookseries_data.json)
  --authors-only     Only scrape authors list, not individual series
  -h, --help         Show help message
```

## Output Format

The script generates JSON with the following structure:

```json
{
  "source": "https://www.bookseries.org",
  "total_authors": 1303,
  "authors": [
    {
      "name": "A.G. Riddle",
      "url": "https://www.bookseries.org/authors/a-g-riddle/",
      "bio": "A.G. Riddle is a bestselling indie author...",
      "series": [
        {
          "title": "The Origin Mystery Series",
          "book_count": 3,
          "books": [
            {
              "title": "The Atlantis Gene"
            },
            {
              "title": "The Atlantis Plague"
            },
            {
              "title": "The Atlantis World"
            }
          ]
        }
      ]
    }
  ]
}
```

## Data Collected

For each author:
- Full name
- Author page URL
- Biography (when available)
- All book series

For each series:
- Series title
- Number of books
- Book titles in order

## Progress Tracking

The script saves progress every 50 authors to prevent data loss if interrupted. You can safely stop and restart the script.

## Ethical Usage

This scraper:
- Uses a 1-second delay between requests by default
- Identifies itself with a proper User-Agent
- Respects the website's structure
- Is intended for personal research and educational purposes

Please use responsibly and consider the website's terms of service.

## Examples

### Quick test with 5 authors:
```bash
python3 scripts/scrape_bookseries_org.py --limit 5 --output test.json
```

### Full scrape with faster delay (0.5 seconds):
```bash
python3 scripts/scrape_bookseries_org.py --delay 0.5 --output full_data.json
```

### Authors list only:
```bash
python3 scripts/scrape_bookseries_org.py --authors-only
```

## Output Files

- `authors_list.json` - Just author names and URLs (~100KB)
- `bookseries_data.json` - Complete data with all series (~5-10MB)
- Progress is auto-saved every 50 authors during full scrape
