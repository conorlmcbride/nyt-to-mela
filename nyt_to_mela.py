#!/usr/bin/env python3
"""Export saved NYT Cooking recipes to a Mela-compatible .melarecipes file."""

import argparse
import base64
import json
import os
import re
import sys
import zipfile
from io import BytesIO
from pathlib import Path

import requests
from recipe_scrapers import scrape_html

BASE_URL = "https://cooking.nytimes.com"

NUTRITION_LABELS = {
    "calories": "Calories",
    "fatContent": "Fat",
    "saturatedFatContent": "Saturated fat",
    "unsaturatedFatContent": "Unsaturated fat",
    "transFatContent": "Trans fat",
    "cholesterolContent": "Cholesterol",
    "sodiumContent": "Sodium",
    "carbohydrateContent": "Carbohydrates",
    "fiberContent": "Fiber",
    "sugarContent": "Sugar",
    "proteinContent": "Protein",
}

NUTRITION_ORDER = [
    "calories", "fatContent", "saturatedFatContent", "unsaturatedFatContent",
    "transFatContent", "cholesterolContent", "sodiumContent",
    "carbohydrateContent", "fiberContent", "sugarContent", "proteinContent",
]
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def make_session(cookie: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    s.cookies.set("NYT-S", cookie, domain=".nytimes.com")
    return s


def parse_jkidd_uid(jkidd: str) -> str | None:
    """Extract the uid from the nyt-jkidd cookie value (URL-encoded query string)."""
    import urllib.parse
    decoded = urllib.parse.unquote(jkidd)
    params = dict(urllib.parse.parse_qsl(decoded))
    return params.get("uid") or params.get("userId") or params.get("user_id")


def fetch_user_id(session: requests.Session) -> str:
    """Try to discover the user ID from the NYT Cooking homepage."""
    for url in (f"{BASE_URL}", f"{BASE_URL}/recipes"):
        resp = session.get(url, timeout=30)
        if not resp.ok:
            continue
        for pat in (
            r'"user_id"\s*:\s*"?(\d+)"?',
            r'"userId"\s*:\s*"?(\d+)"?',
            r'"regi_id"\s*:\s*"?(\d+)"?',
            r'"uid"\s*:\s*"?(\d+)"?',
        ):
            m = re.search(pat, resp.text)
            if m:
                return m.group(1)
    raise RuntimeError(
        "Could not auto-detect your user ID.\n"
        "In Firefox DevTools → Storage → Cookies → cooking.nytimes.com,\n"
        "copy the value of the 'nyt-jkidd' cookie and pass it as:\n"
        "  --jkidd '<value>'"
    )


def fetch_saved_recipes(session: requests.Session, user_id: str) -> list[dict]:
    recipes = []
    page = 1
    while True:
        url = f"{BASE_URL}/api/v2/users/{user_id}/search/recipe_box_search"
        resp = session.get(
            url,
            params={"per_page": 48, "page": page},
            headers={"x-cooking-api": "cooking-frontend", "Accept": "*/*"},
            timeout=30,
        )
        if resp.status_code in (401, 403):
            sys.exit(
                f"Authentication failed ({resp.status_code}). "
                "Check your --cookie and --user-id values."
            )
        resp.raise_for_status()

        data = resp.json()
        # Try common response shapes
        items = data.get("collectables") or data.get("results") or data.get("recipes") or data.get("items") or []
        if not items:
            break
        recipes.extend(items)
        if len(items) < 48:
            break
        page += 1

    return recipes


def recipe_url(item: dict) -> str | None:
    if item.get("url"):
        return item["url"]
    if item.get("recipe_url"):
        return item["recipe_url"]
    if item.get("link"):
        return item["link"]
    rid = item.get("id") or item.get("recipe_id")
    slug = item.get("slug") or re.sub(r"[^a-z0-9]+", "-", (item.get("title") or "").lower()).strip("-")
    if rid and slug:
        return f"{BASE_URL}/recipes/{rid}-{slug}"
    if rid:
        return f"{BASE_URL}/recipes/{rid}"
    return None


def download_image_b64(session: requests.Session, url: str) -> str | None:
    try:
        resp = session.get(url, timeout=15)
        resp.raise_for_status()
        return base64.b64encode(resp.content).decode("ascii")
    except Exception:
        return None


def minutes_to_mela_time(minutes: int | None) -> str:
    if not minutes:
        return ""
    hours, mins = divmod(int(minutes), 60)
    if hours and mins:
        return f"{hours}h {mins}min"
    if hours:
        return f"{hours}h"
    return f"{mins}min"


def to_mela_recipe(scraper, url: str, session: requests.Session, include_images: bool) -> dict:
    images = []
    if include_images:
        try:
            img_url = scraper.image()
            if img_url:
                b64 = download_image_b64(session, img_url)
                if b64:
                    images = [b64]
        except Exception:
            pass

    def safe(fn):
        try:
            return fn() or ""
        except Exception:
            return ""

    def safe_list(fn):
        try:
            return fn() or []
        except Exception:
            return []

    ingredients = "\n".join(safe_list(scraper.ingredients))
    instructions = "\n".join(safe_list(scraper.instructions_list))
    categories_raw = safe(scraper.category)
    categories = [c.strip() for c in categories_raw.split(",") if c.strip()]

    nutrition_str = ""
    try:
        nutrients = scraper.nutrients()
        if nutrients:
            lines = []
            for key in NUTRITION_ORDER:
                if key in nutrients:
                    label = NUTRITION_LABELS[key]
                    lines.append(f"**{label}** {nutrients[key]}")
            for key, value in nutrients.items():
                if key not in NUTRITION_LABELS:
                    lines.append(f"**{key}** {value}")
            nutrition_str = "\n".join(lines)
    except Exception:
        pass

    return {
        "id": re.sub(r"^https?://", "", url),
        "title": safe(scraper.title),
        "text": safe(scraper.description),
        "images": images,
        "categories": categories,
        "yield": safe(scraper.yields),
        "prepTime": minutes_to_mela_time(safe(scraper.prep_time) or None),
        "cookTime": minutes_to_mela_time(safe(scraper.cook_time) or None),
        "totalTime": minutes_to_mela_time(safe(scraper.total_time) or None),
        "ingredients": ingredients,
        "instructions": instructions,
        "notes": "",
        "nutrition": nutrition_str,
        "link": url,
        "favorite": False,
        "wantToCook": False,
    }


def create_melarecipes_bundle(mela_recipes: list[dict], output_path: str) -> None:
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for recipe in mela_recipes:
            safe_name = re.sub(r'[/\\:*?"<>|]', "_", recipe["title"]) or "recipe"
            zf.writestr(f"{safe_name}.melarecipe", json.dumps(recipe, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export saved NYT Cooking recipes to Mela (.melarecipes)"
    )
    parser.add_argument("--cookie", default=os.environ.get("NYT_COOKIE"), help="Value of the NYT-S cookie")
    parser.add_argument("--user-id", default=os.environ.get("NYT_USER_ID"), help="Your numeric NYT user ID (auto-detected if omitted)")
    parser.add_argument("--jkidd", default=os.environ.get("NYT_JKIDD"), help="Value of the nyt-jkidd cookie (used to detect user ID)")
    parser.add_argument("--output", default="recipes.melarecipes", help="Output file path (default: recipes.melarecipes)")
    parser.add_argument("--no-images", action="store_true", help="Skip downloading recipe images (faster)")
    args = parser.parse_args()

    if not args.cookie:
        parser.print_help()
        print(
            "\nError: --cookie is required.\n"
            "\nHow to find cookie values in Firefox:\n"
            "  1. Log in to cooking.nytimes.com\n"
            "  2. Open DevTools (F12) → Storage tab → Cookies → https://cooking.nytimes.com\n"
            "  3. Copy the value of the 'NYT-S' row\n"
            "  4. Optionally also copy the 'nyt-jkidd' row and pass it as --jkidd\n"
        )
        sys.exit(1)

    session = make_session(args.cookie)

    user_id = args.user_id
    if not user_id and args.jkidd:
        user_id = parse_jkidd_uid(args.jkidd)
        if user_id:
            print(f"Detected user ID from nyt-jkidd: {user_id}")
    if not user_id:
        print("Detecting user ID...")
        user_id = fetch_user_id(session)
        print(f"Detected user ID: {user_id}")

    print("Fetching saved recipes...")
    saved_items = fetch_saved_recipes(session, user_id)

    if not saved_items:
        print("No saved recipes found. Check your credentials and try again.")
        sys.exit(0)

    print(f"Found {len(saved_items)} saved recipe(s). Scraping...")

    mela_recipes = []
    for i, item in enumerate(saved_items, 1):
        url = recipe_url(item)
        label = item.get("name") or item.get("title") or url or f"recipe {i}"
        print(f"[{i}/{len(saved_items)}] {label}", end="", flush=True)

        if not url:
            print(" — skipped (no URL)")
            continue

        try:
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
            scraper = scrape_html(resp.text, org_url=url)
            mela = to_mela_recipe(scraper, url, session, include_images=not args.no_images)
            mela_recipes.append(mela)
            print(" ✓")
        except Exception as e:
            print(f" — failed: {e}")

    if not mela_recipes:
        print("No recipes were successfully converted.")
        sys.exit(1)

    create_melarecipes_bundle(mela_recipes, args.output)
    count = len(mela_recipes)
    print(f"\nWrote {args.output} ({count} recipe{'s' if count != 1 else ''})")
    print("Open this file in Mela to import your recipes.")


if __name__ == "__main__":
    main()
