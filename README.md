# nyt-to-mela

Export your saved [NYT Cooking](https://cooking.nytimes.com) recipes to [Mela](https://mela.recipes), the recipe manager for iPhone, iPad, and Mac.

Generates a `.melarecipes` file you can open directly in Mela to import all your recipes at once, with ingredients, instructions, times, nutrition info, and photos.

## Prerequisites

- Python 3.10+
- A NYT Cooking subscription
- [Mela](https://apps.apple.com/app/mela-recipe-manager/id1548466041) on any Apple device to import the resulting file

## Installation

```bash
git clone https://github.com/conor/nyt-to-mela.git
cd nyt-to-mela
pip install -r requirements.txt
```

## Getting your credentials

1. Log in to [cooking.nytimes.com](https://cooking.nytimes.com)
2. Open DevTools: `F12` or `Cmd+Option+I`
3. Go to the **Storage** tab (Firefox) or **Application** tab (Chrome/Edge) → **Cookies** → `https://cooking.nytimes.com`
4. Copy the **Value** of the `NYT-S` cookie
5. Copy the **Value** of the `nyt-jkidd` cookie

## Usage

```bash
python3 nyt_to_mela.py --cookie "<NYT-S value>" --jkidd "<nyt-jkidd value>"
```

This exports all your saved recipes (with photos) to `recipes.melarecipes` in the current directory.

### Options

| Flag | Description |
|---|---|
| `--cookie` | Value of the `NYT-S` cookie (required) |
| `--jkidd` | Value of the `nyt-jkidd` cookie (used to detect your user ID) |
| `--user-id` | Your numeric NYT user ID (alternative to `--jkidd`) |
| `--output` | Output file path (default: `recipes.melarecipes`) |
| `--no-images` | Skip downloading photos — much faster, smaller file |

You can also set credentials via environment variables:

```bash
export NYT_COOKIE="<NYT-S value>"
export NYT_JKIDD="<nyt-jkidd value>"
python3 nyt_to_mela.py
```

### Example

```
Detected user ID from nyt-jkidd: 93592072
Fetching saved recipes...
Found 165 saved recipe(s). Scraping...
[1/165] Golden Diner's Tuna Melt ✓
[2/165] Dan Dan Noodle Salad ✓
...
[165/165] Skillet Chicken With Tomatoes, Pancetta and Mozzarella ✓

Wrote recipes.melarecipes (165 recipes)
Open this file in Mela to import your recipes.
```

## Importing into Mela

- **Mac**: Double-click `recipes.melarecipes` — Mela will prompt you to import
- **iPhone / iPad**: AirDrop or save to iCloud Drive, then tap the file to open in Mela

## Notes

- Your cookies are only used to authenticate with NYT Cooking — they are never stored or sent anywhere else.
- Cookies expire periodically. If you get an authentication error, grab fresh values from your browser.
- Running with images (~165 recipes) produces a ~240MB file and takes a couple of minutes. Without images the same 165 recipes come in under 250KB. Use `--no-images` if you just want a quick export.
