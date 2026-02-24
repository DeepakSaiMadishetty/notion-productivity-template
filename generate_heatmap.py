#!/usr/bin/env python3
"""
Generate a GitHub-style contribution heatmap from Notion tracker data.

Usage:
    python generate_heatmap.py
    # Then open heatmap/index.html in your browser.
"""

import json
import os
import time
from collections import defaultdict
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
        days = {}
        for i, name in enumerate(DAY_NAMES):
            days[name] = monday + timedelta(days=i)
        weeks.append({
            "week_key": f"W{week_num:02d}",
            "monday": monday,
            "days": days,
        })
        week_num += 1
        monday += timedelta(days=7)
    return weeks


def fetch_all_tracker_entries():
    """Fetch all entries from the tracker data source."""
    tracker_ds_id = CONFIG.get("tracker_ds_id")
    if not tracker_ds_id:
        print("Error: tracker_ds_id not in config.json. Run setup.py first.")
        return []

    pages = []
    start_cursor = None
    print("Fetching tracker data from Notion...")
    while True:
        kwargs = {"data_source_id": tracker_ds_id, "page_size": 100}
        if start_cursor:
            kwargs["start_cursor"] = start_cursor
        response = api_call(notion.data_sources.query, **kwargs)
        pages.extend(response["results"])
        if not response.get("has_more"):
            break
        start_cursor = response["next_cursor"]
        print(f"  Fetched {len(pages)} entries...")

    print(f"  Total: {len(pages)} entries")
    return pages


def compute_daily_scores(pages, weeks):
    """
    For each day of the year, compute:
      completed_metrics / total_metrics * 100
    Returns dict: { "2026-01-05": 75.0, ... }
    """
    # Map week_key -> list of day dates
    week_day_map = {}
    for w in weeks:
        week_day_map[w["week_key"]] = w["days"]

    # For each date: track (completed, total)
    daily_completed = defaultdict(int)
    daily_total = defaultdict(int)

    for page in pages:
        props = page["properties"]

        # Get week key
        week_sel = props.get("Week", {}).get("select")
        if not week_sel:
            continue
        week_key = week_sel["name"]

        if week_key not in week_day_map:
            continue

        days = week_day_map[week_key]

        for day_name in DAY_NAMES:
            d = days[day_name]
            # Only count days in the target year
            if d.year != YEAR:
                continue
            date_str = d.isoformat()
            checked = props.get(day_name, {}).get("checkbox", False)
            daily_total[date_str] += 1
            if checked:
                daily_completed[date_str] += 1

    scores = {}
    for date_str in daily_total:
        total = daily_total[date_str]
        completed = daily_completed[date_str]
        scores[date_str] = round(completed / total * 100, 1) if total > 0 else 0

    return scores


def generate_html(scores: dict):
    """Generate a self-contained heatmap HTML file."""
    # Build data for every day of the year
    jan1 = date(YEAR, 1, 1)
    dec31 = date(YEAR, 12, 31)

    days_data = []
    d = jan1
    while d <= dec31:
        score = scores.get(d.isoformat(), 0)
        days_data.append({
            "date": d.isoformat(),
            "weekday": d.weekday(),  # 0=Mon, 6=Sun
            "score": score,
            "label": d.strftime("%b %d, %Y"),
        })
        d += timedelta(days=1)

    data_json = json.dumps(days_data)

    # Compute summary stats
    total_days = len(days_data)
    active_days = sum(1 for dd in days_data if dd["score"] > 0)
    avg_score = round(sum(dd["score"] for dd in days_data) / max(total_days, 1), 1)
    perfect_days = sum(1 for dd in days_data if dd["score"] >= 100)

    # Compute current streak
    today = date.today()
    streak = 0
    d = min(today, dec31)
    while d >= jan1:
        if scores.get(d.isoformat(), 0) > 0:
            streak += 1
            d -= timedelta(days=1)
        else:
            break

    # Compute longest streak
    longest_streak = 0
    current = 0
    d = jan1
    while d <= min(today, dec31):
        if scores.get(d.isoformat(), 0) > 0:
            current += 1
            longest_streak = max(longest_streak, current)
        else:
            current = 0
        d += timedelta(days=1)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Productivity Heatmap {YEAR}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #0d1117;
    color: #c9d1d9;
    padding: 40px;
    min-width: 900px;
  }}
  h1 {{
    font-size: 24px;
    margin-bottom: 8px;
    color: #f0f6fc;
  }}
  .subtitle {{
    color: #8b949e;
    margin-bottom: 30px;
    font-size: 14px;
  }}
  .stats {{
    display: flex;
    gap: 32px;
    margin-bottom: 30px;
    flex-wrap: wrap;
  }}
  .stat {{
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 16px 24px;
    min-width: 140px;
  }}
  .stat-value {{
    font-size: 28px;
    font-weight: 700;
    color: #58a6ff;
  }}
  .stat-value.green {{ color: #3fb950; }}
  .stat-value.orange {{ color: #d29922; }}
  .stat-value.purple {{ color: #bc8cff; }}
  .stat-label {{
    font-size: 12px;
    color: #8b949e;
    margin-top: 4px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }}
  .heatmap-container {{
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 24px;
    overflow-x: auto;
  }}
  .month-labels {{
    display: flex;
    margin-left: 36px;
    margin-bottom: 8px;
    font-size: 12px;
    color: #8b949e;
  }}
  .month-label {{
    text-align: left;
  }}
  .heatmap {{
    display: flex;
    gap: 3px;
  }}
  .day-labels {{
    display: flex;
    flex-direction: column;
    gap: 3px;
    margin-right: 6px;
    font-size: 11px;
    color: #8b949e;
  }}
  .day-labels span {{
    height: 13px;
    line-height: 13px;
  }}
  .week-column {{
    display: flex;
    flex-direction: column;
    gap: 3px;
  }}
  .day-cell {{
    width: 13px;
    height: 13px;
    border-radius: 2px;
    position: relative;
    cursor: pointer;
  }}
  .day-cell:hover {{
    outline: 2px solid #c9d1d9;
    outline-offset: -1px;
  }}
  .tooltip {{
    display: none;
    position: absolute;
    bottom: 20px;
    left: 50%;
    transform: translateX(-50%);
    background: #1b1f23;
    border: 1px solid #484f58;
    color: #f0f6fc;
    padding: 6px 10px;
    border-radius: 6px;
    font-size: 12px;
    white-space: nowrap;
    z-index: 100;
    pointer-events: none;
    box-shadow: 0 4px 12px rgba(0,0,0,0.4);
  }}
  .day-cell:hover .tooltip {{
    display: block;
  }}
  .legend {{
    display: flex;
    align-items: center;
    gap: 4px;
    margin-top: 16px;
    margin-left: 36px;
    font-size: 12px;
    color: #8b949e;
  }}
  .legend-cell {{
    width: 13px;
    height: 13px;
    border-radius: 2px;
  }}
  .level-0 {{ background-color: #161b22; }}
  .level-1 {{ background-color: #0e4429; }}
  .level-2 {{ background-color: #006d32; }}
  .level-3 {{ background-color: #26a641; }}
  .level-4 {{ background-color: #39d353; }}
</style>
</head>
<body>
<h1>Productivity Heatmap {YEAR}</h1>
<p class="subtitle">Daily metric completion rate — darker = higher % of daily targets met</p>

<div class="stats">
  <div class="stat">
    <div class="stat-value green">{active_days}</div>
    <div class="stat-label">Active Days</div>
  </div>
  <div class="stat">
    <div class="stat-value">{avg_score}%</div>
    <div class="stat-label">Avg Completion</div>
  </div>
  <div class="stat">
    <div class="stat-value orange">{streak}</div>
    <div class="stat-label">Current Streak</div>
  </div>
  <div class="stat">
    <div class="stat-value purple">{longest_streak}</div>
    <div class="stat-label">Longest Streak</div>
  </div>
  <div class="stat">
    <div class="stat-value green">{perfect_days}</div>
    <div class="stat-label">Perfect Days (100%)</div>
  </div>
</div>

<div class="heatmap-container">
  <div class="month-labels" id="monthLabels"></div>
  <div style="display:flex;">
    <div class="day-labels">
      <span>&nbsp;</span>
      <span>Mon</span>
      <span>&nbsp;</span>
      <span>Wed</span>
      <span>&nbsp;</span>
      <span>Fri</span>
      <span>&nbsp;</span>
    </div>
    <div class="heatmap" id="heatmap"></div>
  </div>
  <div class="legend">
    <span>Less</span>
    <div class="legend-cell level-0"></div>
    <div class="legend-cell level-1"></div>
    <div class="legend-cell level-2"></div>
    <div class="legend-cell level-3"></div>
    <div class="legend-cell level-4"></div>
    <span>More</span>
  </div>
</div>

<script>
const data = {data_json};
const YEAR = {YEAR};

function getLevel(score) {{
  if (score === 0) return 0;
  if (score <= 25) return 1;
  if (score <= 50) return 2;
  if (score <= 75) return 3;
  return 4;
}}

function render() {{
  const heatmap = document.getElementById('heatmap');
  const monthLabels = document.getElementById('monthLabels');

  // Build a date->score map
  const scoreMap = {{}};
  data.forEach(d => {{ scoreMap[d.date] = d; }});

  // Find the first Monday on or before Jan 1
  const jan1 = new Date(YEAR, 0, 1);
  const startOffset = (jan1.getDay() + 6) % 7; // days since Monday
  const startDate = new Date(jan1);
  startDate.setDate(startDate.getDate() - startOffset);

  // Find last Sunday on or after Dec 31
  const dec31 = new Date(YEAR, 11, 31);
  const endOffset = (7 - dec31.getDay()) % 7;
  const endDate = new Date(dec31);
  endDate.setDate(endDate.getDate() + endOffset);

  // Build weeks
  const weeks = [];
  let current = new Date(startDate);
  while (current <= endDate) {{
    const week = [];
    for (let i = 0; i < 7; i++) {{
      const dateStr = current.toISOString().split('T')[0];
      const inYear = current.getFullYear() === YEAR;
      const entry = scoreMap[dateStr];
      week.push({{
        date: dateStr,
        score: entry ? entry.score : 0,
        label: entry ? entry.label : dateStr,
        inYear: inYear,
      }});
      current.setDate(current.getDate() + 1);
    }}
    weeks.push(week);
  }}

  // Render month labels
  const monthWidths = {{}};
  weeks.forEach((week, i) => {{
    // Use Thursday to determine month
    const thu = new Date(week[3].date);
    if (thu.getFullYear() === YEAR) {{
      const m = thu.getMonth();
      if (!monthWidths[m]) monthWidths[m] = {{ start: i, count: 0 }};
      monthWidths[m].count++;
    }}
  }});

  const monthNames = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  let lastEnd = 0;
  Object.keys(monthWidths).sort((a,b) => a-b).forEach(m => {{
    const info = monthWidths[m];
    const gap = info.start - lastEnd;
    if (gap > 0) {{
      const spacer = document.createElement('span');
      spacer.style.width = (gap * 16) + 'px';
      spacer.style.flexShrink = '0';
      monthLabels.appendChild(spacer);
    }}
    const label = document.createElement('span');
    label.className = 'month-label';
    label.style.width = (info.count * 16) + 'px';
    label.style.flexShrink = '0';
    label.textContent = monthNames[m];
    monthLabels.appendChild(label);
    lastEnd = info.start + info.count;
  }});

  // Render heatmap cells
  weeks.forEach(week => {{
    const col = document.createElement('div');
    col.className = 'week-column';
    week.forEach(day => {{
      const cell = document.createElement('div');
      cell.className = 'day-cell';
      if (!day.inYear) {{
        cell.classList.add('level-0');
        cell.style.opacity = '0.3';
      }} else {{
        cell.classList.add('level-' + getLevel(day.score));
      }}
      const tooltip = document.createElement('div');
      tooltip.className = 'tooltip';
      tooltip.textContent = day.inYear
        ? `${{day.label}}: ${{day.score}}% completed`
        : '';
      cell.appendChild(tooltip);
      col.appendChild(cell);
    }});
    heatmap.appendChild(col);
  }});
}}

render();
</script>
</body>
</html>"""

    os.makedirs("heatmap", exist_ok=True)
    output_path = os.path.join("heatmap", "index.html")
    with open(output_path, "w") as f:
        f.write(html)
    return output_path


def main():
    weeks = get_weeks(YEAR)
    pages = fetch_all_tracker_entries()

    if not pages:
        print("No tracker entries found. Run setup.py first, then check some boxes in Notion.")
        return

    print("Computing daily scores...")
    scores = compute_daily_scores(pages, weeks)

    active_days = sum(1 for s in scores.values() if s > 0)
    print(f"  {len(scores)} days tracked, {active_days} active days")

    print("Generating heatmap...")
    path = generate_html(scores)
    print(f"\nDone! Open {path} in your browser.")
    print(f"  file://{os.path.abspath(path)}")


if __name__ == "__main__":
    main()
