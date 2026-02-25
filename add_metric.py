#!/usr/bin/env python3
"""
Add a new metric and auto-create all 12 monthly tracker entries.

Usage:
    python add_metric.py "Drink Water" --category Health --target 7
    python add_metric.py "Practice Guitar" --category Personal
"""

import argparse
import calendar
import json
import sys
import time
from notion_client import Client

with open("config.json") as f:
    CONFIG = json.load(f)

notion = Client(auth=CONFIG["notion_api_key"])
YEAR = CONFIG.get("year", 2026)
MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
VALID_CATEGORIES = ["Health", "Work", "Learning", "Personal", "Finance", "Social"]


def api_call(func, *args, retries=3, **kwargs):
    for attempt in range(retries):
        try:
            result = func(*args, **kwargs)
            time.sleep(0.4)
            return result
        except Exception as e:
            err_str = str(e)
            if attempt < retries - 1 and ("502" in err_str or "429" in err_str or "503" in err_str):
                time.sleep(2 ** (attempt + 1))
            else:
                raise


def add_metric(name: str, category: str = "Personal", weekly_target: int = 0):
    metrics_db_id = CONFIG.get("metrics_db_id")
    tracker_db_id = CONFIG.get("tracker_db_id")
    metrics_ds_id = CONFIG.get("metrics_ds_id")
    tracker_ds_id = CONFIG.get("tracker_ds_id")

    if not metrics_db_id or not tracker_db_id:
        print("Error: Database IDs not found in config.json. Run setup.py first.")
        sys.exit(1)

    # Check if metric already exists
    existing = api_call(
        notion.data_sources.query,
        data_source_id=metrics_ds_id,
        filter={"property": "Name", "title": {"equals": name}},
    )
    if existing["results"]:
        print(f"Error: Metric '{name}' already exists.")
        sys.exit(1)

    # Add to My Metrics database
    print(f"Adding metric: {name} (category={category}, weekly_target={weekly_target})")
    api_call(
        notion.pages.create,
        parent={"database_id": metrics_db_id},
        properties={
            "Name": {"title": [{"text": {"content": name}}]},
            "Category": {"select": {"name": category}},
            "Weekly Target": {"number": weekly_target},
            "Active": {"checkbox": True},
        },
        children=[
            {
                "object": "block",
                "type": "heading_3",
                "heading_3": {"rich_text": [{"type": "text", "text": {"content": "Description"}}]},
            },
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": f"Describe your '{name}' metric here."}}],
                },
            },
        ],
    )
    print(f"  Added to My Metrics.")

    # Check which months already have entries
    existing_months = set()
    cursor = None
    while True:
        kwargs = {
            "data_source_id": tracker_ds_id,
            "filter": {"property": "Metric", "title": {"equals": name}},
            "page_size": 100,
        }
        if cursor:
            kwargs["start_cursor"] = cursor
        resp = api_call(notion.data_sources.query, **kwargs)
        for page in resp["results"]:
            month_sel = page["properties"].get("Month", {}).get("select")
            if month_sel:
                existing_months.add(month_sel["name"])
        if not resp.get("has_more"):
            break
        cursor = resp["next_cursor"]

    needed = [m for m in MONTHS if m not in existing_months]
    print(f"  Creating {len(needed)} monthly tracker entries...")

    for i, month_name in enumerate(needed, 1):
        month_num = MONTHS.index(month_name) + 1
        num_days = calendar.monthrange(YEAR, month_num)[1]
        monthly_target = round(weekly_target * num_days / 7) if weekly_target else 0

        api_call(
            notion.pages.create,
            parent={"database_id": tracker_db_id},
            properties={
                "Metric": {"title": [{"text": {"content": name}}]},
                "Category": {"select": {"name": category}},
                "Month": {"select": {"name": month_name}},
                "Monthly Target": {"number": monthly_target},
                **{str(d): {"checkbox": False} for d in range(1, 32)},
                "Streak": {"number": 0},
            },
        )
        print(f"  + {month_name}")

    print(f"\nDone! '{name}' added with {len(needed)} monthly entries.")


def main():
    parser = argparse.ArgumentParser(description="Add a new metric to the productivity tracker.")
    parser.add_argument("name", help="Name of the metric (e.g., 'Drink Water')")
    parser.add_argument("--category", default="Personal", choices=VALID_CATEGORIES,
                        help="Category (default: Personal)")
    parser.add_argument("--target", type=int, default=0,
                        help="Weekly target in days (default: 0 = no target)")
    args = parser.parse_args()
    add_metric(args.name, args.category, args.target)


if __name__ == "__main__":
    main()
