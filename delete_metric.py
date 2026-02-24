#!/usr/bin/env python3
"""
Delete a metric and all its weekly tracker entries.

Usage:
    python delete_metric.py "Drink Water"
"""

import argparse
import json
import sys
import time
from notion_client import Client

with open("config.json") as f:
    CONFIG = json.load(f)

notion = Client(auth=CONFIG["notion_api_key"])


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


def fetch_all_pages(ds_id: str, filter_obj: dict) -> list:
    """Fetch all pages from a data source, handling pagination."""
    pages = []
    start_cursor = None
    while True:
        kwargs = {"data_source_id": ds_id, "filter": filter_obj, "page_size": 100}
        if start_cursor:
            kwargs["start_cursor"] = start_cursor
        response = api_call(notion.data_sources.query, **kwargs)
        pages.extend(response["results"])
        if not response.get("has_more"):
            break
        start_cursor = response["next_cursor"]
    return pages


def delete_metric(name: str):
    metrics_ds_id = CONFIG.get("metrics_ds_id")
    tracker_ds_id = CONFIG.get("tracker_ds_id")

    if not metrics_ds_id or not tracker_ds_id:
        print("Error: Data source IDs not found in config.json. Run setup.py first.")
        sys.exit(1)

    # Find metric in My Metrics
    metric_pages = fetch_all_pages(
        metrics_ds_id,
        {"property": "Name", "title": {"equals": name}},
    )

    if not metric_pages:
        print(f"Error: Metric '{name}' not found in My Metrics database.")
        sys.exit(1)

    # Find all tracker entries for this metric
    tracker_pages = fetch_all_pages(
        tracker_ds_id,
        {"property": "Metric", "title": {"equals": name}},
    )

    total = len(metric_pages) + len(tracker_pages)
    print(f"Found {len(metric_pages)} metric page(s) and {len(tracker_pages)} tracker entries.")
    confirm = input(f"Delete all {total} pages for '{name}'? (y/N): ").strip().lower()
    if confirm != "y":
        print("Aborted.")
        sys.exit(0)

    # Archive (soft-delete) all pages
    count = 0
    for page in metric_pages:
        api_call(notion.pages.update, page_id=page["id"], archived=True)
        count += 1

    for page in tracker_pages:
        api_call(notion.pages.update, page_id=page["id"], archived=True)
        count += 1
        if count % 10 == 0:
            print(f"  Progress: {count}/{total}")

    print(f"\nDone! Archived {count} pages for '{name}'.")


def main():
    parser = argparse.ArgumentParser(description="Delete a metric and all its tracker entries.")
    parser.add_argument("name", help="Exact name of the metric to delete")
    args = parser.parse_args()
    delete_metric(args.name)


if __name__ == "__main__":
    main()
