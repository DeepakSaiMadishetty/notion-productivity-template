#!/usr/bin/env python3
"""
Productivity Tracker 2026 - Notion Setup Script
Creates databases, populates monthly tracker entries, and builds page structure.

Compatible with Notion API 2025-09-03 (notion-client 3.x).
"""

import json
import sys
import time
from datetime import date, timedelta
import calendar
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

DEFAULT_METRICS = [
    {"name": "Exercise", "category": "Health", "target": 5},
    {"name": "Read 30 min", "category": "Learning", "target": 7},
    {"name": "Meditate", "category": "Health", "target": 5},
    {"name": "Deep Work (4 hrs)", "category": "Work", "target": 5},
    {"name": "Journal", "category": "Personal", "target": 7},
]

DAY_ABBR = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

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


def get_month_day_labels(year: int, month: int) -> list[str]:
    """Return day labels like '1 (Mon)', '2 (Tue)' ... for a given month."""
    num_days = calendar.monthrange(year, month)[1]
    labels = []
    for day in range(1, num_days + 1):
        d = date(year, month, day)
        day_name = DAY_ABBR[d.weekday()]
        labels.append(f"{day} ({day_name})")
    return labels

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
    print(f"  Created: {db_id}")
    return db_id, ds_id


def create_tracker_database(parent_id: str) -> tuple[str, str]:
    """Create the 'Monthly Tracker 2026' database. Returns (db_id, data_source_id)."""
    print("Creating 'Monthly Tracker 2026' database...")
    db = api_call(
        notion.databases.create,
        parent={"type": "page_id", "page_id": parent_id},
        title=[{"type": "text", "text": {"content": "Monthly Tracker 2026"}}],
        icon={"type": "emoji", "emoji": "✅"},
        is_inline=True,
    )
    db_id = db["id"]
    ds_id = db["data_sources"][0]["id"]

    month_options = [
        {"name": m, "color": MONTH_COLORS[i]} for i, m in enumerate(MONTHS)
    ]

    # Step 1: Base properties + day columns 1-31
    print("  Adding base properties + day columns 1-31...")
    day_props = {str(d): {"checkbox": {}} for d in range(1, 32)}
    api_call(
        notion.data_sources.update,
        data_source_id=ds_id,
        properties={
            "Name": {"name": "Metric", "title": {}},
            "Category": {"select": {"options": CATEGORIES}},
            "Month": {"select": {"options": month_options}},
            "Monthly Target": {"number": {"format": "number"}},
            "Streak": {"number": {"format": "number"}},
            **day_props,
        },
    )

    # Step 2: Days Done formula
    print("  Adding Days Done formula...")
    days_done_parts = [f'if(prop("{d}"), 1, 0)' for d in range(1, 32)]
    days_done_expr = " + ".join(days_done_parts)
    api_call(
        notion.data_sources.update,
        data_source_id=ds_id,
        properties={"Days Done": {"formula": {"expression": days_done_expr}}},
    )

    # Step 3: Target Met formula (inlined)
    print("  Adding Target Met formula...")
    target_met_expr = (
        f'if(prop("Monthly Target") > 0, ({days_done_expr}) >= prop("Monthly Target"), true)'
    )
    api_call(
        notion.data_sources.update,
        data_source_id=ds_id,
        properties={"Target Met": {"formula": {"expression": target_met_expr}}},
    )

    print(f"  Created with 37 properties: {db_id}")
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


def populate_tracker(tracker_db_id: str, tracker_ds_id: str, metrics: list):
    """Create one row per metric per month (60 entries for 5 metrics)."""
    # Check existing
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
            month_sel = props.get("Month", {}).get("select")
            if metric_title and month_sel:
                name = metric_title[0].get("text", {}).get("content", "")
                month = month_sel.get("name", "")
                existing.add((name, month))
        if not resp.get("has_more"):
            break
        cursor = resp["next_cursor"]

    needed = []
    for metric in metrics:
        for month_name in MONTHS:
            if (metric["name"], month_name) not in existing:
                needed.append((metric, month_name))

    total = len(needed)
    if total == 0:
        print(f"  All entries exist. Skipping.")
        return

    print(f"  {len(existing)} exist, {total} to create...")

    # Monthly target = weekly target * ~4.3 (rounded)
    count = 0
    for metric, month_name in needed:
        month_num = MONTHS.index(month_name) + 1
        num_days = calendar.monthrange(YEAR, month_num)[1]
        monthly_target = round(metric["target"] * num_days / 7)

        api_call(
            notion.pages.create,
            parent={"database_id": tracker_db_id},
            properties={
                "Metric": {"title": [{"text": {"content": metric["name"]}}]},
                "Category": {"select": {"name": metric["category"]}},
                "Month": {"select": {"name": month_name}},
                "Monthly Target": {"number": monthly_target},
                **{str(d): {"checkbox": False} for d in range(1, 32)},
                "Streak": {"number": 0},
            },
        )
        count += 1
        if count % 10 == 0:
            print(f"  Progress: {count}/{total}")

    print(f"  Done: {count} entries created. Total: {len(existing) + count}")

# ---------------------------------------------------------------------------
# Page structure
# ---------------------------------------------------------------------------

def build_page_structure(parent_id: str):
    """Append headings, month references, and instructions to the parent page."""
    print("Building page layout...")

    blocks: list[dict] = []

    # Header
    blocks.append(_heading1("Productivity Tracker 2026"))
    blocks.append(_callout(
        "💡",
        "How to use:\n"
        "1. Open 'Monthly Tracker 2026' below.\n"
        "2. Use the view tabs (January, February, ...) to switch months.\n"
        "3. Check boxes daily — Days Done and Target Met auto-calculate.\n"
        "4. Click any metric in 'My Metrics' to edit its description.\n"
        "5. Use the embedded tracker widget for the best visual experience.",
    ))
    blocks.append(_divider())

    # Month reference toggles (showing day-of-week mapping)
    blocks.append(_heading2("📆 Month Day Reference"))
    blocks.append(_paragraph(
        "Expand a month to see which day of the week each date falls on."
    ))

    for month_idx, month_name in enumerate(MONTHS):
        month_num = month_idx + 1
        num_days = calendar.monthrange(YEAR, month_num)[1]
        labels = get_month_day_labels(YEAR, month_num)

        # Build rows of 7 for readability
        rows = []
        for i in range(0, len(labels), 7):
            chunk = labels[i:i+7]
            rows.append("  ".join(f"{l:>8}" for l in chunk))
        day_text = "\n".join(rows)

        blocks.append({
            "object": "block",
            "type": "toggle",
            "toggle": {
                "rich_text": [
                    {"type": "text", "text": {"content": f"  {month_name} {YEAR}"}, "annotations": {"bold": True}},
                    {"type": "text", "text": {"content": f"  ({num_days} days)"}, "annotations": {"color": "gray"}},
                ],
                "children": [
                    {
                        "object": "block",
                        "type": "code",
                        "code": {
                            "rich_text": [{"type": "text", "text": {"content": day_text}}],
                            "language": "plain text",
                        },
                    },
                ],
            },
        })

    blocks.append(_divider())

    # Charts section
    blocks.append(_heading2("📈 Charts & Analytics"))
    blocks.append(_callout(
        "📊",
        "Set up charts on Monthly Tracker:\n"
        "1. Per-metric completion → Bar chart, X: Metric, Y: Days Done\n"
        "2. Monthly trend → Line chart, X: Month, Y: Days Done\n"
        "3. Category breakdown → Pie chart, group by Category\n\n"
        "To add: open Monthly Tracker → + Add a view → Chart.",
    ))
    blocks.append(_divider())

    # Heatmap section
    blocks.append(_heading2("🟩 Yearly Contribution Heatmap"))
    blocks.append(_paragraph(
        "Run  python generate_heatmap.py  to create a GitHub-style heatmap.\n"
        "Open heatmap/index.html in your browser to view it."
    ))
    blocks.append(_divider())

    # Web tracker widget section
    blocks.append(_heading2("🌐 Interactive Tracker Widget"))
    blocks.append(_callout(
        "🖥️",
        "After running setup, deploy the web tracker to GitHub Pages:\n"
        "  git push origin main\n"
        "Then embed this URL in Notion with /embed:\n"
        f"  https://<your-username>.github.io/notion-productivity-template/tracker/\n\n"
        "The widget has a month dropdown with dynamic day headers like '1 (Mon)'.",
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

def save_config(**ids):
    CONFIG.update(ids)
    with open("config.json", "w") as f:
        json.dump(CONFIG, f, indent=4)
    print("  IDs saved to config.json")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 55)
    print(f"  Productivity Tracker {YEAR} — Monthly Setup")
    print("=" * 55)

    if CONFIG.get("tracker_db_id") and CONFIG.get("tracker_ds_id"):
        print("\n⚠️  config.json already has database IDs.")
        print("   Running again will create DUPLICATE databases.")
        resp = input("   Continue? (y/N): ").strip().lower()
        if resp != "y":
            print("Aborted.")
            sys.exit(0)

    # 1. Build page structure first (databases appear above this content)
    build_page_structure(PAGE_ID)

    # 2. Create databases
    metrics_db_id, metrics_ds_id = create_metrics_database(PAGE_ID)
    tracker_db_id, tracker_ds_id = create_tracker_database(PAGE_ID)

    # 3. Save IDs
    save_config(
        metrics_db_id=metrics_db_id,
        tracker_db_id=tracker_db_id,
        metrics_ds_id=metrics_ds_id,
        tracker_ds_id=tracker_ds_id,
    )

    # 4. Populate
    add_default_metrics(metrics_db_id)
    populate_tracker(tracker_db_id, tracker_ds_id, DEFAULT_METRICS)

    total_entries = len(DEFAULT_METRICS) * 12
    print("\n" + "=" * 55)
    print("  Setup complete!")
    print("=" * 55)
    print(f"\n  Metrics DB:  {metrics_db_id}")
    print(f"  Tracker DB:  {tracker_db_id}")
    print(f"  Entries:     {len(DEFAULT_METRICS)} metrics x 12 months = {total_entries}")
    print(f"\n  Next steps:")
    print(f"  1. Open your Notion page")
    print(f"  2. Monthly Tracker already has view tabs per month")
    print(f"  3. Start checking off your daily habits!")
    print(f"  4. Run 'python add_metric.py' to add more metrics\n")


if __name__ == "__main__":
    main()
