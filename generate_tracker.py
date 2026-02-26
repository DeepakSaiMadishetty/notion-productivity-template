#!/usr/bin/env python3
"""
Generate the interactive tracker widget with real data from Notion.

Usage:
    python generate_tracker.py
    # Then open tracker/index.html or push to GitHub Pages.
"""

import calendar
import json
import os
import time
from datetime import date
from notion_client import Client

with open("config.json") as f:
    CONFIG = json.load(f)

notion = Client(auth=CONFIG["notion_api_key"])
YEAR = CONFIG.get("year", 2026)
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
            if attempt < retries - 1 and any(c in str(e) for c in ("502", "429", "503")):
                time.sleep(2 ** (attempt + 1))
            else:
                raise


def fetch_metrics():
    """Fetch all active metrics from My Metrics database."""
    ds_id = CONFIG.get("metrics_ds_id")
    if not ds_id:
        print("Error: metrics_ds_id not in config.json. Run setup.py first.")
        return []

    metrics = []
    cursor = None
    while True:
        kwargs = {"data_source_id": ds_id, "page_size": 100}
        if cursor:
            kwargs["start_cursor"] = cursor
        resp = api_call(notion.data_sources.query, **kwargs)
        for page in resp["results"]:
            props = page["properties"]
            name_title = props.get("Name", {}).get("title", [])
            if not name_title:
                continue
            name = name_title[0]["text"]["content"]
            cat_sel = props.get("Category", {}).get("select")
            category = cat_sel["name"] if cat_sel else "Personal"
            target = props.get("Weekly Target", {}).get("number") or 0
            active = props.get("Active", {}).get("checkbox", True)
            if active:
                metrics.append({"name": name, "category": category, "target": target})
        if not resp.get("has_more"):
            break
        cursor = resp["next_cursor"]

    return metrics


def fetch_tracker_data():
    """Fetch all tracker entries and build a nested dict of checked days."""
    ds_id = CONFIG.get("tracker_ds_id")
    if not ds_id:
        return {}

    # { "January": { "Exercise": { "01": true, ... }, ... }, ... }
    data = {}
    cursor = None
    while True:
        kwargs = {"data_source_id": ds_id, "page_size": 100}
        if cursor:
            kwargs["start_cursor"] = cursor
        resp = api_call(notion.data_sources.query, **kwargs)
        for page in resp["results"]:
            props = page["properties"]
            metric_title = props.get("Metric", {}).get("title", [])
            month_sel = props.get("Month", {}).get("select")
            if not metric_title or not month_sel:
                continue
            metric_name = metric_title[0]["text"]["content"]
            month_name = month_sel["name"]

            if month_name not in data:
                data[month_name] = {}
            if metric_name not in data[month_name]:
                data[month_name][metric_name] = {}

            month_num = MONTHS.index(month_name) + 1
            num_days = calendar.monthrange(YEAR, month_num)[1]
            for d in range(1, num_days + 1):
                key = f"{d:02d}"
                checked = props.get(key, {}).get("checkbox", False)
                if checked:
                    data[month_name][metric_name][str(d)] = True

        if not resp.get("has_more"):
            break
        cursor = resp["next_cursor"]

    return data


def generate_html(metrics, tracker_data):
    metrics_json = json.dumps(metrics)
    data_json = json.dumps(tracker_data)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Productivity Tracker {YEAR}</title>
<style>
  :root {{
    --bg: #1e1e2e;
    --surface: #262637;
    --border: #363649;
    --text: #cdd6f4;
    --text-dim: #6c7086;
    --accent: #89b4fa;
    --green: #a6e3a1;
    --red: #f38ba8;
    --yellow: #f9e2af;
    --check-bg: #313244;
    --check-active: #a6e3a1;
    --cat-health: #a6e3a1;
    --cat-work: #89b4fa;
    --cat-learning: #cba6f7;
    --cat-personal: #fab387;
    --cat-finance: #f9e2af;
    --cat-social: #f5c2e7;
  }}

  * {{ margin: 0; padding: 0; box-sizing: border-box; }}

  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', sans-serif;
    background: var(--bg);
    color: var(--text);
    padding: 24px;
    min-height: 100vh;
  }}

  .header {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 24px;
    flex-wrap: wrap;
    gap: 16px;
  }}
  .header h1 {{ font-size: 22px; font-weight: 700; }}
  .header-controls {{ display: flex; align-items: center; gap: 12px; }}

  .month-select {{
    background: var(--surface);
    border: 1px solid var(--border);
    color: var(--text);
    padding: 8px 16px;
    border-radius: 8px;
    font-size: 15px;
    cursor: pointer;
    appearance: none;
    -webkit-appearance: none;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%236c7086' d='M2 4l4 4 4-4'/%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-position: right 12px center;
    padding-right: 32px;
  }}
  .month-select:focus {{ outline: 2px solid var(--accent); }}

  .year-display {{ font-size: 15px; color: var(--text-dim); font-weight: 500; }}

  .stats-bar {{ display: flex; gap: 16px; margin-bottom: 20px; flex-wrap: wrap; }}
  .stat {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 12px 20px;
    min-width: 110px;
  }}
  .stat-value {{ font-size: 24px; font-weight: 700; }}
  .stat-value.green {{ color: var(--green); }}
  .stat-value.blue {{ color: var(--accent); }}
  .stat-value.yellow {{ color: var(--yellow); }}
  .stat-label {{ font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; margin-top: 2px; }}

  .tracker-wrap {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    overflow-x: auto;
  }}
  .tracker-table {{
    border-collapse: separate;
    border-spacing: 0;
    width: max-content;
    min-width: 100%;
  }}
  .tracker-table th, .tracker-table td {{
    padding: 6px 4px;
    text-align: center;
    font-size: 12px;
    border-bottom: 1px solid var(--border);
    white-space: nowrap;
  }}

  .tracker-table th:first-child,
  .tracker-table td:first-child {{
    position: sticky;
    left: 0;
    z-index: 2;
    background: var(--surface);
    text-align: left;
    padding-left: 16px;
    padding-right: 12px;
    min-width: 160px;
    font-weight: 600;
    border-right: 2px solid var(--border);
  }}
  .tracker-table thead th:first-child {{ z-index: 3; }}

  .tracker-table thead th {{
    position: sticky;
    top: 0;
    background: var(--surface);
    z-index: 1;
    padding: 10px 4px 6px;
    font-weight: 500;
  }}
  .day-num {{ display: block; font-size: 14px; font-weight: 600; color: var(--text); }}
  .day-name {{ display: block; font-size: 10px; color: var(--text-dim); margin-top: 1px; }}
  .weekend .day-num {{ color: var(--accent); }}
  .today-col {{ background: rgba(137, 180, 250, 0.08) !important; }}

  .cat-pill {{
    display: inline-block;
    font-size: 10px;
    padding: 1px 6px;
    border-radius: 4px;
    margin-left: 6px;
    font-weight: 400;
    opacity: 0.8;
  }}

  .cb-cell {{ padding: 3px 2px; min-width: 28px; }}
  .cb {{
    width: 20px;
    height: 20px;
    border-radius: 4px;
    border: 2px solid var(--border);
    background: var(--check-bg);
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    transition: all 0.15s;
  }}
  .cb:hover {{ border-color: var(--accent); transform: scale(1.1); }}
  .cb.checked {{
    background: var(--check-active);
    border-color: var(--check-active);
  }}
  .cb.checked::after {{
    content: '';
    width: 6px;
    height: 10px;
    border: solid var(--bg);
    border-width: 0 2.5px 2.5px 0;
    transform: rotate(45deg) translate(-1px, -1px);
  }}

  .score-cell {{
    font-weight: 700;
    font-size: 13px;
    padding-right: 16px !important;
    border-left: 2px solid var(--border);
    min-width: 60px;
  }}
  .score-cell.perfect {{ color: var(--green); }}
  .score-cell.good {{ color: var(--accent); }}
  .score-cell.low {{ color: var(--red); }}

  .status-bar {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 16px;
    font-size: 12px;
    color: var(--text-dim);
  }}

  .tracker-wrap::-webkit-scrollbar {{ height: 8px; }}
  .tracker-wrap::-webkit-scrollbar-track {{ background: var(--surface); }}
  .tracker-wrap::-webkit-scrollbar-thumb {{ background: var(--border); border-radius: 4px; }}

  .week-sep {{ border-left: 2px solid var(--border) !important; }}
</style>
</head>
<body>

<div class="header">
  <h1>Productivity Tracker {YEAR}</h1>
  <div class="header-controls">
    <span class="year-display">{YEAR}</span>
    <select class="month-select" id="monthSelect"></select>
  </div>
</div>

<div class="stats-bar" id="statsBar">
  <div class="stat"><div class="stat-value green" id="statDone">0</div><div class="stat-label">Days Done</div></div>
  <div class="stat"><div class="stat-value blue" id="statPct">0%</div><div class="stat-label">Completion</div></div>
  <div class="stat"><div class="stat-value yellow" id="statStreak">0</div><div class="stat-label">Streak</div></div>
</div>

<div class="tracker-wrap">
  <table class="tracker-table" id="trackerTable">
    <thead id="tableHead"></thead>
    <tbody id="tableBody"></tbody>
  </table>
</div>

<div class="status-bar">
  <span>Synced from Notion — re-run <code>python generate_tracker.py</code> to refresh</span>
  <span id="monthInfo"></span>
</div>

<script>
const YEAR = {YEAR};
const MONTHS = {json.dumps(MONTHS)};
const DAY_NAMES = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
const CAT_COLORS = {{
  Health: 'var(--cat-health)',
  Work: 'var(--cat-work)',
  Learning: 'var(--cat-learning)',
  Personal: 'var(--cat-personal)',
  Finance: 'var(--cat-finance)',
  Social: 'var(--cat-social)',
}};

const metrics = {metrics_json};
let data = {data_json};

// Merge any localStorage overrides on top of Notion data
const localOverrides = JSON.parse(localStorage.getItem('tracker_overrides') || '{{}}');
Object.keys(localOverrides).forEach(month => {{
  if (!data[month]) data[month] = {{}};
  Object.keys(localOverrides[month] || {{}}).forEach(metric => {{
    if (!data[month][metric]) data[month][metric] = {{}};
    Object.assign(data[month][metric], localOverrides[month][metric]);
  }});
}});

function daysInMonth(month) {{ return new Date(YEAR, month + 1, 0).getDate(); }}
function getDayOfWeek(month, day) {{ return (new Date(YEAR, month, day).getDay() + 6) % 7; }}
function isToday(month, day) {{
  const now = new Date();
  return now.getFullYear() === YEAR && now.getMonth() === month && now.getDate() === day;
}}
function isWeekStart(month, day) {{ return getDayOfWeek(month, day) === 0 && day > 1; }}

function getChecked(monthName, metricName, day) {{
  return !!(data[monthName] && data[monthName][metricName] && data[monthName][metricName][String(day)]);
}}

function setChecked(monthName, metricName, day, value) {{
  if (!data[monthName]) data[monthName] = {{}};
  if (!data[monthName][metricName]) data[monthName][metricName] = {{}};
  data[monthName][metricName][String(day)] = value;
  // Save override to localStorage
  if (!localOverrides[monthName]) localOverrides[monthName] = {{}};
  if (!localOverrides[monthName][metricName]) localOverrides[monthName][metricName] = {{}};
  localOverrides[monthName][metricName][String(day)] = value;
  localStorage.setItem('tracker_overrides', JSON.stringify(localOverrides));
}}

function computeStats(monthIdx) {{
  const monthName = MONTHS[monthIdx];
  const numDays = daysInMonth(monthIdx);
  let totalChecks = 0;
  metrics.forEach(m => {{
    for (let d = 1; d <= numDays; d++) {{ if (getChecked(monthName, m.name, d)) totalChecks++; }}
  }});
  const now = new Date();
  let streak = 0;
  let checkDate = new Date(YEAR, monthIdx, Math.min(now.getMonth() === monthIdx ? now.getDate() : numDays, numDays));
  while (checkDate.getMonth() === monthIdx && checkDate.getDate() >= 1) {{
    const day = checkDate.getDate();
    if (metrics.length > 0 && metrics.every(m => getChecked(monthName, m.name, day))) {{
      streak++;
      checkDate.setDate(checkDate.getDate() - 1);
    }} else break;
  }}
  return {{ totalChecks, totalPossible: metrics.length * numDays, streak }};
}}

function render(monthIdx) {{
  const monthName = MONTHS[monthIdx];
  const numDays = daysInMonth(monthIdx);
  const thead = document.getElementById('tableHead');
  let hdr = '<tr><th>Metric</th>';
  for (let d = 1; d <= numDays; d++) {{
    const dow = getDayOfWeek(monthIdx, d);
    let cls = (dow >= 5 ? ' weekend' : '') + (isToday(monthIdx, d) ? ' today-col' : '') + (isWeekStart(monthIdx, d) ? ' week-sep' : '');
    hdr += `<th class="${{cls}}"><span class="day-num">${{d}}</span><span class="day-name">${{DAY_NAMES[dow]}}</span></th>`;
  }}
  hdr += '<th>Score</th></tr>';
  thead.innerHTML = hdr;

  const tbody = document.getElementById('tableBody');
  let body = '';
  metrics.forEach(m => {{
    const catColor = CAT_COLORS[m.category] || 'var(--text-dim)';
    body += `<tr><td>${{m.name}}<span class="cat-pill" style="background:${{catColor}}22;color:${{catColor}}">${{m.category}}</span></td>`;
    let done = 0;
    for (let d = 1; d <= numDays; d++) {{
      const checked = getChecked(monthName, m.name, d);
      if (checked) done++;
      let cls = 'cb-cell' + (isToday(monthIdx, d) ? ' today-col' : '') + (isWeekStart(monthIdx, d) ? ' week-sep' : '');
      body += `<td class="${{cls}}"><div class="cb${{checked ? ' checked' : ''}}" data-metric="${{m.name}}" data-day="${{d}}" data-month="${{monthName}}"></div></td>`;
    }}
    const pct = numDays > 0 ? Math.round(done / numDays * 100) : 0;
    let sc = 'score-cell' + (pct >= 90 ? ' perfect' : pct >= 50 ? ' good' : pct > 0 ? ' low' : '');
    body += `<td class="${{sc}}">${{done}}/${{numDays}}</td></tr>`;
  }});
  tbody.innerHTML = body;

  const stats = computeStats(monthIdx);
  document.getElementById('statDone').textContent = stats.totalChecks;
  document.getElementById('statPct').textContent = (stats.totalPossible > 0 ? Math.round(stats.totalChecks / stats.totalPossible * 100) : 0) + '%';
  document.getElementById('statStreak').textContent = stats.streak;
  document.getElementById('monthInfo').textContent = `${{monthName}} ${{YEAR}} — ${{numDays}} days`;

  document.querySelectorAll('.cb').forEach(cb => {{
    cb.addEventListener('click', () => {{
      const newVal = !getChecked(cb.dataset.month, cb.dataset.metric, cb.dataset.day);
      setChecked(cb.dataset.month, cb.dataset.metric, cb.dataset.day, newVal);
      render(monthIdx);
    }});
  }});
}}

const select = document.getElementById('monthSelect');
MONTHS.forEach((m, i) => {{ const o = document.createElement('option'); o.value = i; o.textContent = m; select.appendChild(o); }});
const now = new Date();
select.value = (now.getFullYear() === YEAR) ? now.getMonth() : 0;
select.addEventListener('change', () => render(parseInt(select.value)));
render(parseInt(select.value));
</script>
</body>
</html>"""

    os.makedirs("tracker", exist_ok=True)
    output_path = os.path.join("tracker", "index.html")
    with open(output_path, "w") as f:
        f.write(html)
    return output_path


def main():
    print("Fetching metrics from Notion...")
    metrics = fetch_metrics()
    print(f"  Found {len(metrics)} active metrics:")
    for m in metrics:
        print(f"    - {m['name']} ({m['category']})")

    print("\nFetching tracker data from Notion...")
    tracker_data = fetch_tracker_data()
    total_checks = sum(
        sum(len(days) for days in month.values())
        for month in tracker_data.values()
    )
    print(f"  {total_checks} checked days across {len(tracker_data)} months")

    print("\nGenerating tracker widget...")
    path = generate_html(metrics, tracker_data)
    print(f"Done! Open {path} in your browser.")
    print(f"  file://{os.path.abspath(path)}")
    print(f"\nPush to GitHub to update the embedded widget:")
    print(f"  git add tracker/index.html && git commit -m 'Sync tracker' && git push")


if __name__ == "__main__":
    main()
