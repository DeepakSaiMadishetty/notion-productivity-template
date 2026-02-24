#!/usr/bin/env python3
"""
Productivity Tracker 2026 - Notion Setup Script
Creates databases, populates weekly tracker entries, and builds page structure.

Compatible with Notion API 2025-09-03 (notion-client 3.x).
"""

import json
import sys
import time
from datetime import date, timedelta
from notion_client import Client

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

with open("config.json") as f:
    CONFIG = json.load(f)

NOTION_API_KEY = CONFIG["notion_api_key"]
PAGE_ID = CONFIG["page_id"]
YEAR = CONFIG.get("year", 2026)

notion = Client(auth=NOTION_API_KEY)

CATEGORIES = [
    {"name": "Health", "color": "green"},
    {"name": "Work", "color": "blue"},
    {"name": "Learning", "color": "purple"},
    {"name": "Personal", "color": "orange"},
    {"name": "Finance", "color": "yellow"},
    {"name": "Social", "color": "pink"},
]

MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

MONTH_COLORS = [
    "gray", "brown", "orange", "yellow", "green", "blue",
    "purple", "pink", "red", "default", "gray", "brown",
]

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

DEFAULT_METRICS = [
    {"name": "Exercise", "category": "Health", "target": 5},
    {"name": "Read 30 min", "category": "Learning", "target": 7},
    {"name": "Meditate", "category": "Health", "target": 5},
    {"name": "Deep Work (4 hrs)", "category": "Work", "target": 5},
    {"name": "Journal", "category": "Personal", "target": 7},
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def api_call(func, *args, retries=3, **kwargs):
    """API call wrapper with rate limiting and retry for transient errors."""
    for attempt in range(retries):
        try:
            result = func(*args, **kwargs)
            time.sleep(0.4)
            return result
        except Exception as e:
            err_str = str(e)
            if attempt < retries - 1 and ("502" in err_str or "429" in err_str or "503" in err_str):
                wait = 2 ** (attempt + 1)
                print(f"    Retry {attempt+1}/{retries} after {wait}s...")
                time.sleep(wait)
            else:
                raise


def get_weeks(year: int):
    """Return all Mon-Sun weeks that overlap with the given year."""
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

        days = {}
        for i, name in enumerate(DAY_NAMES):
            days[name] = monday + timedelta(days=i)

        weeks.append({
            "week_num": week_num,
            "monday": monday,
            "sunday": sunday,
            "month_num": month_num,
            "month_name": MONTHS[month_num - 1],
            "label": f"{monday.strftime('%b %d')} - {sunday.strftime('%b %d')}",
            "days": days,
            "week_key": f"W{week_num:02d}",
        })

        week_num += 1
        monday += timedelta(days=7)

    return weeks


def get_data_source_id(db_id: str) -> str:
    """Get the first data source ID for a database."""
    db = api_call(notion.databases.retrieve, db_id)
    return db["data_sources"][0]["id"]

# ---------------------------------------------------------------------------
# Database creation (Notion API 2025-09-03)
# ---------------------------------------------------------------------------

def create_metrics_database(parent_id: str) -> tuple[str, str]:
    """Create the 'My Metrics' database. Returns (db_id, data_source_id)."""
    print("Creating 'My Metrics' database...")
    db = api_call(
        notion.databases.create,
        parent={"type": "page_id", "page_id": parent_id},
        title=[{"type": "text", "text": {"content": "My Metrics"}}],
        icon={"type": "emoji", "emoji": "🎯"},
        is_inline=True,
    )
    db_id = db["id"]
    ds_id = db["data_sources"][0]["id"]
    print(f"  Database: {db_id}")
    print(f"  DataSource: {ds_id}")

    # Add properties via data_sources.update
    print("  Adding properties...")
    api_call(
        notion.data_sources.update,
        data_source_id=ds_id,
        properties={
            "Category": {"select": {"options": CATEGORIES}},
            "Weekly Target": {"number": {"format": "number"}},
            "Active": {"checkbox": {}},
        },
    )
    print("  Properties set: Name, Category, Weekly Target, Active")
    return db_id, ds_id


def create_tracker_database(parent_id: str, weeks: list) -> tuple[str, str]:
    """Create the 'Weekly Tracker 2026' database. Returns (db_id, data_source_id)."""
    print("Creating 'Weekly Tracker 2026' database...")
    db = api_call(
        notion.databases.create,
        parent={"type": "page_id", "page_id": parent_id},
        title=[{"type": "text", "text": {"content": "Weekly Tracker 2026"}}],
        icon={"type": "emoji", "emoji": "✅"},
        is_inline=True,
    )
    db_id = db["id"]
    ds_id = db["data_sources"][0]["id"]
    print(f"  Database: {db_id}")
    print(f"  DataSource: {ds_id}")

    month_options = [
        {"name": m, "color": MONTH_COLORS[i]} for i, m in enumerate(MONTHS)
    ]
    week_options = [{"name": f"W{n:02d}", "color": "default"} for n in range(1, 54)]

    # Step 1: Add base properties (non-formula)
    print("  Adding base properties...")
    api_call(
        notion.data_sources.update,
        data_source_id=ds_id,
        properties={
            "Name": {"name": "Metric", "title": {}},
            "Category": {"select": {"options": CATEGORIES}},
            "Month": {"select": {"options": month_options}},
            "Week": {"select": {"options": week_options}},
            "Week Dates": {"rich_text": {}},
            **{d: {"checkbox": {}} for d in DAY_NAMES},
            "Weekly Target": {"number": {"format": "number"}},
            "Streak": {"number": {"format": "number"}},
        },
    )

    # Step 2: Add Days Done formula (references checkbox properties)
    print("  Adding Days Done formula...")
    days_done_expr = " + ".join(
        [f'if(prop("{d}"), 1, 0)' for d in DAY_NAMES]
    )
    api_call(
        notion.data_sources.update,
        data_source_id=ds_id,
        properties={"Days Done": {"formula": {"expression": days_done_expr}}},
    )

    # Step 3: Add Target Met formula (must inline Days Done since cross-ref fails)
    print("  Adding Target Met formula...")
    target_met_expr = (
        f'if(prop("Weekly Target") > 0, ({days_done_expr}) >= prop("Weekly Target"), true)'
    )
    api_call(
        notion.data_sources.update,
        data_source_id=ds_id,
        properties={"Target Met": {"formula": {"expression": target_met_expr}}},
    )

    print("  All 16 properties set.")
    return db_id, ds_id

# ---------------------------------------------------------------------------
# Populate data
# ---------------------------------------------------------------------------

def add_default_metrics(metrics_db_id: str) -> list:
    """Add starter metrics with description subpages."""
    print("Adding default metrics...")
    results = []
    for m in DEFAULT_METRICS:
        page = api_call(
            notion.pages.create,
            parent={"database_id": metrics_db_id},
            properties={
                "Name": {"title": [{"text": {"content": m["name"]}}]},
                "Category": {"select": {"name": m["category"]}},
                "Weekly Target": {"number": m["target"]},
                "Active": {"checkbox": True},
            },
            children=[
                {
                    "object": "block",
                    "type": "heading_3",
                    "heading_3": {
                        "rich_text": [{"type": "text", "text": {"content": "Description"}}],
                    },
                },
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {
                                    "content": f"Track your daily '{m['name']}' habit. "
                                    f"Target: {m['target']} days per week.",
                                },
                            }
                        ],
                    },
                },
            ],
        )
        results.append({**m, "page_id": page["id"]})
        print(f"  + {m['name']}")
    return results


def populate_tracker(tracker_db_id: str, tracker_ds_id: str, metrics: list, weeks: list):
    """Create one row per metric per week, skipping already-existing entries."""
    # Check for existing entries (supports resume after partial failure)
    print("  Checking for existing entries...")
    existing = set()
    cursor = None
    while True:
        kwargs = {"data_source_id": tracker_ds_id, "page_size": 100}
        if cursor:
            kwargs["start_cursor"] = cursor
        resp = api_call(notion.data_sources.query, **kwargs)
        for page in resp["results"]:
            props = page["properties"]
            metric_title = props.get("Metric", {}).get("title", [])
            week_sel = props.get("Week", {}).get("select")
            if metric_title and week_sel:
                name = metric_title[0].get("text", {}).get("content", "")
                week = week_sel.get("name", "")
                existing.add((name, week))
        if not resp.get("has_more"):
            break
        cursor = resp["next_cursor"]

    # Build list of missing entries
    needed = []
    for metric in metrics:
        for week in weeks:
            if (metric["name"], week["week_key"]) not in existing:
                needed.append((metric, week))

    total = len(needed)
    if total == 0:
        print(f"  All {len(existing)} entries already exist. Skipping.")
        return

    print(f"  {len(existing)} exist, {total} to create...")

    count = 0
    for metric, week in needed:
        api_call(
            notion.pages.create,
            parent={"database_id": tracker_db_id},
            properties={
                "Metric": {"title": [{"text": {"content": metric["name"]}}]},
                "Category": {"select": {"name": metric["category"]}},
                "Month": {"select": {"name": week["month_name"]}},
                "Week": {"select": {"name": week["week_key"]}},
                "Week Dates": {"rich_text": [{"text": {"content": week["label"]}}]},
                **{d: {"checkbox": False} for d in DAY_NAMES},
                "Weekly Target": {"number": metric["target"]},
                "Streak": {"number": 0},
            },
        )
        count += 1
        if count % 25 == 0:
            pct = count * 100 // total
            print(f"  Progress: {count}/{total} ({pct}%)")

    print(f"  Done: {count} entries created. Total: {len(existing) + count}")

# ---------------------------------------------------------------------------
# Page structure
# ---------------------------------------------------------------------------

def build_page_structure(parent_id: str, weeks: list):
    """Append headings, toggles, and instructions to the parent page."""
    print("Building page layout...")

    months_weeks: dict[str, list] = {}
    for w in weeks:
        months_weeks.setdefault(w["month_name"], []).append(w)

    blocks: list[dict] = []

    # Header
    blocks.append(_heading1("Productivity Tracker 2026"))
    blocks.append(_callout(
        "💡",
        "How to use:\n"
        "1. Scroll down to 'Weekly Tracker 2026' and click the ⋯ menu → Add view → Table.\n"
        "2. Filter by Week = current week. Save as 'This Week'.\n"
        "3. Repeat for each month (filter by Month). Add Chart views for analytics.\n"
        "4. Check boxes daily. Use 'My Metrics' to manage your metrics list.",
    ))
    blocks.append(_divider())

    # Pinned current week
    blocks.append(_heading2("📌 This Week"))
    blocks.append(_paragraph(
        "Create a 'This Week' filtered view on the Weekly Tracker database above, "
        "then drag it here for quick access."
    ))
    blocks.append(_divider())

    # Monthly toggles
    blocks.append(_heading2("📆 Monthly Views"))

    for month_name in MONTHS:
        m_weeks = months_weeks.get(month_name, [])
        children = []
        for w in m_weeks:
            day_header = "  |  ".join(
                f"{d} {w['days'][d].strftime('%m/%d')}" for d in DAY_NAMES
            )
            children.append(_callout(
                "📋",
                f"{w['week_key']}: {w['label']}\n{day_header}",
                "gray_background",
            ))

        if not children:
            children.append(_paragraph("No weeks in this month."))

        blocks.append({
            "object": "block",
            "type": "toggle",
            "toggle": {
                "rich_text": [
                    {"type": "text", "text": {"content": f"  {month_name}"}, "annotations": {"bold": True}},
                    {"type": "text", "text": {"content": f"  ({len(m_weeks)} weeks)"}, "annotations": {"color": "gray"}},
                ],
                "children": children,
            },
        })

    blocks.append(_divider())

    # Charts section
    blocks.append(_heading2("📈 Charts & Analytics"))
    blocks.append(_callout(
        "📊",
        "Set up charts on the Weekly Tracker database:\n"
        "1. Per-metric completion → Bar chart, X: Metric, Y: Days Done\n"
        "2. Monthly trend → Line chart, X: Month, Y: Days Done (sum)\n"
        "3. Category breakdown → Pie chart, group by Category\n"
        "4. Target hit rate → Bar chart, X: Week, Y: Target Met (% true)\n\n"
        "To add: open Weekly Tracker → + Add a view → Chart.",
    ))
    blocks.append(_divider())

    # Heatmap section
    blocks.append(_heading2("🟩 Yearly Contribution Heatmap"))
    blocks.append(_paragraph(
        "Run  python generate_heatmap.py  to create a GitHub-style heatmap.\n"
        "Open heatmap/index.html in your browser to view it."
    ))
    blocks.append(_divider())

    # Quick reference
    blocks.append(_heading2("📖 Quick Reference"))
    blocks.append(_callout(
        "⚙️",
        "CLI Commands:\n"
        '• Add metric:    python add_metric.py "Drink Water" --category Health --target 7\n'
        '• Remove metric: python delete_metric.py "Drink Water"\n'
        "• Gen heatmap:   python generate_heatmap.py\n"
        "• Re-run setup:  python setup.py  (only if starting fresh)",
    ))

    # Append blocks in batches of 100
    for i in range(0, len(blocks), 100):
        api_call(notion.blocks.children.append, block_id=parent_id, children=blocks[i : i + 100])

    print("  Page layout created.")


# Block builder helpers
def _heading1(text):
    return {"object": "block", "type": "heading_1", "heading_1": {"rich_text": [{"type": "text", "text": {"content": text}}]}}

def _heading2(text):
    return {"object": "block", "type": "heading_2", "heading_2": {"rich_text": [{"type": "text", "text": {"content": text}}]}}

def _paragraph(text):
    return {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": text}}]}}

def _divider():
    return {"object": "block", "type": "divider", "divider": {}}

def _callout(emoji, text, color="default"):
    return {
        "object": "block",
        "type": "callout",
        "callout": {
            "icon": {"type": "emoji", "emoji": emoji},
            "rich_text": [{"type": "text", "text": {"content": text}}],
            "color": color,
        },
    }

# ---------------------------------------------------------------------------
# Config persistence
# ---------------------------------------------------------------------------

def save_config(metrics_db_id: str, tracker_db_id: str, metrics_ds_id: str, tracker_ds_id: str):
    CONFIG["metrics_db_id"] = metrics_db_id
    CONFIG["tracker_db_id"] = tracker_db_id
    CONFIG["metrics_ds_id"] = metrics_ds_id
    CONFIG["tracker_ds_id"] = tracker_ds_id
    with open("config.json", "w") as f:
        json.dump(CONFIG, f, indent=4)
    print("  IDs saved to config.json")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 55)
    print(f"  Productivity Tracker {YEAR} — Notion Setup")
    print("=" * 55)

    if CONFIG.get("metrics_db_id") and CONFIG.get("tracker_db_id"):
        print("\n⚠️  config.json already has database IDs.")
        print("   Running again will create DUPLICATE databases.")
        resp = input("   Continue? (y/N): ").strip().lower()
        if resp != "y":
            print("Aborted.")
            sys.exit(0)

    weeks = get_weeks(YEAR)
    print(f"\nGenerated {len(weeks)} weeks for {YEAR}")
    print(f"  First week: {weeks[0]['label']}")
    print(f"  Last week:  {weeks[-1]['label']}\n")

    # 1. Build page structure first (databases will appear above this content)
    build_page_structure(PAGE_ID, weeks)

    # 2. Create databases + add properties via data sources API
    metrics_db_id, metrics_ds_id = create_metrics_database(PAGE_ID)
    tracker_db_id, tracker_ds_id = create_tracker_database(PAGE_ID, weeks)

    # 3. Save IDs
    save_config(metrics_db_id, tracker_db_id, metrics_ds_id, tracker_ds_id)

    # 4. Populate
    add_default_metrics(metrics_db_id)
    populate_tracker(tracker_db_id, tracker_ds_id, DEFAULT_METRICS, weeks)

    # Done
    print("\n" + "=" * 55)
    print("  Setup complete!")
    print("=" * 55)
    print(f"\n  Metrics DB:  {metrics_db_id}")
    print(f"  Tracker DB:  {tracker_db_id}")
    print(f"  Entries:     {len(DEFAULT_METRICS)} metrics x {len(weeks)} weeks = {len(DEFAULT_METRICS) * len(weeks)}")
    print(f"\n  Next steps:")
    print(f"  1. Open your Notion page and explore the databases")
    print(f"  2. Create filtered views: 'This Week', monthly views, chart views")
    print(f"  3. Start checking off your daily habits!")
    print(f"  4. Run 'python add_metric.py' to add more metrics\n")


if __name__ == "__main__":
    main()
