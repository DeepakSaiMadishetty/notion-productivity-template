#!/usr/bin/env python3
"""
Add a new metric and auto-create all weekly tracker entries for the year.

Usage:
    python add_metric.py "Drink Water" --category Health --target 7
    python add_metric.py "Practice Guitar" --category Personal
"""

import argparse
import json
import sys
import time
from datetime import date, timedelta
from notion_client import Client

with open("config.json") as f:
    CONFIG = json.load(f)

notion = Client(auth=CONFIG["notion_api_key"])
YEAR = CONFIG.get("year", 2026)
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
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
                wait = 2 ** (attempt + 1)
                print(f"    Retry {attempt+1} after {wait}s...")
                time.sleep(wait)
            else:
                raise


def get_weeks(year: int):
    jan1 = date(year, 1, 1)
    first_monday = jan1 - timedelta(days=jan1.weekday())
    weeks = []
    monday = first_monday
    week_num = 1
    while True:
        sunday = monday + timedelta(days=6)
        if monday.year > year:
            break
        thursday = monday + timedelta(days=3)
        if thursday.year < year:
            month_num = 1
        elif thursday.year > year:
            month_num = 12
        else:
            month_num = thursday.month
        weeks.append({
            "week_num": week_num,
            "month_name": MONTHS[month_num - 1],
            "label": f"{monday.strftime('%b %d')} - {sunday.strftime('%b %d')}",
            "week_key": f"W{week_num:02d}",
        })
        week_num += 1
        monday += timedelta(days=7)
    return weeks


def add_metric(name: str, category: str = "Personal", target: int = 0):
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
    print(f"Adding metric: {name} (category={category}, target={target})")
    api_call(
        notion.pages.create,
        parent={"database_id": metrics_db_id},
        properties={
            "Name": {"title": [{"text": {"content": name}}]},
            "Category": {"select": {"name": category}},
            "Weekly Target": {"number": target},
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

    # Check which tracker entries already exist for this metric
    existing_weeks = set()
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
            week_sel = page["properties"].get("Week", {}).get("select")
            if week_sel:
                existing_weeks.add(week_sel["name"])
        if not resp.get("has_more"):
            break
        cursor = resp["next_cursor"]

    # Create weekly tracker entries
    weeks = get_weeks(YEAR)
    needed = [w for w in weeks if w["week_key"] not in existing_weeks]
    total = len(needed)
    print(f"  Creating {total} tracker entries ({len(existing_weeks)} already exist)...")

    for i, week in enumerate(needed, 1):
        api_call(
            notion.pages.create,
            parent={"database_id": tracker_db_id},
            properties={
                "Metric": {"title": [{"text": {"content": name}}]},
                "Category": {"select": {"name": category}},
                "Month": {"select": {"name": week["month_name"]}},
                "Week": {"select": {"name": week["week_key"]}},
                "Week Dates": {"rich_text": [{"text": {"content": week["label"]}}]},
                **{d: {"checkbox": False} for d in DAY_NAMES},
                "Weekly Target": {"number": target},
                "Streak": {"number": 0},
            },
        )
        if i % 10 == 0:
            print(f"  Progress: {i}/{total}")

    print(f"\nDone! '{name}' added with {total} weekly entries.")
    print("Open your Notion page and filter by the current week to see it.")


def main():
    parser = argparse.ArgumentParser(description="Add a new metric to the productivity tracker.")
    parser.add_argument("name", help="Name of the metric (e.g., 'Drink Water')")
    parser.add_argument("--category", default="Personal", choices=VALID_CATEGORIES,
                        help="Category for the metric (default: Personal)")
    parser.add_argument("--target", type=int, default=0,
                        help="Weekly target in days (default: 0 = no target)")
    args = parser.parse_args()
    add_metric(args.name, args.category, args.target)


if __name__ == "__main__":
    main()
