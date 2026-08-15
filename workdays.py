#!/usr/bin/env python3
"""Render a grid of workdays as a 1-bit PNG for e-ink displays.

Each square is one workday (Mon-Fri) between a start date and an end date.
Workdays up to and including the current date are filled in solid black; the
rest are drawn as empty outlines. The layout mimics a GitHub contribution
graph: 5 rows (Mon-Fri), columns are weeks, and weeks wrap into stacked
"bands" to fill the image.
"""

import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw  # type: ignore

NYC_TZ = ZoneInfo("America/New_York")

# Image dimensions (1872x1404 e-ink target)
WIDTH = 1872
HEIGHT = 1404
MARGIN = 48

# Date range to display
START_DATE = date(2026, 8, 10)   # a Monday
END_DATE = date(2029, 12, 9)

# Colors (1-bit: 0=black, 1=white)
BLACK = 0
WHITE = 1

WORKDAYS_PER_WEEK = 5  # Mon-Fri


def build_workdays(start: date, end: date) -> list[date]:
    """Return every workday (Mon-Fri) in [start, end], inclusive."""
    days = []
    d = start
    while d <= end:
        if d.weekday() < WORKDAYS_PER_WEEK:
            days.append(d)
        d += timedelta(days=1)
    return days


def week_index(d: date, start: date) -> int:
    """Number of whole weeks between the start date's Monday and d's Monday."""
    start_monday = start - timedelta(days=start.weekday())
    d_monday = d - timedelta(days=d.weekday())
    return (d_monday - start_monday).days // 7


def choose_layout(num_weeks: int) -> dict:
    """Pick a layout that packs `num_weeks` week-columns into the image.

    Searches over the number of weeks per band and keeps the largest cell
    size whose resulting grid still fits within the usable area. Larger cells
    read better on e-ink, so we maximize cell size subject to fitting.
    """
    usable_w = WIDTH - 2 * MARGIN
    usable_h = HEIGHT - 2 * MARGIN

    best = None
    for weeks_per_band in range(4, num_weeks + 1):
        bands = -(-num_weeks // weeks_per_band)  # ceil

        # Gap between adjacent cells is a fraction of the cell size; the gap
        # between bands is larger so the week-rows read as distinct groups.
        # Solve for the cell size `c` that fills the width exactly.
        # width  = weeks_per_band * c + (weeks_per_band - 1) * gap,  gap = 0.28c
        # height = bands * (5c + 4*gap) + (bands - 1) * band_gap,    band_gap = 1.4c
        gap_ratio = 0.28
        band_gap_ratio = 1.4

        w_units = weeks_per_band + gap_ratio * (weeks_per_band - 1)
        cell_from_w = usable_w / w_units

        band_units = bands * (WORKDAYS_PER_WEEK + 4 * gap_ratio) + (bands - 1) * band_gap_ratio
        cell_from_h = usable_h / band_units

        cell = min(cell_from_w, cell_from_h)
        if cell < 3:
            continue

        candidate = {
            "weeks_per_band": weeks_per_band,
            "bands": bands,
            "cell": cell,
            "gap": cell * gap_ratio,
            "band_gap": cell * band_gap_ratio,
        }
        if best is None or cell > best["cell"]:
            best = candidate

    if best is None:
        raise RuntimeError("Could not find a workable layout")
    return best


def create_image(now: datetime, start: date = START_DATE, end: date = END_DATE) -> Image.Image:
    """Render the workday grid, filling in workdays up to `now`."""
    img = Image.new("1", (WIDTH, HEIGHT), WHITE)
    draw = ImageDraw.Draw(img)

    workdays = build_workdays(start, end)
    today = now.date()

    num_weeks = week_index(end, start) + 1
    layout = choose_layout(num_weeks)

    weeks_per_band = layout["weeks_per_band"]
    cell = layout["cell"]
    gap = layout["gap"]
    band_gap = layout["band_gap"]

    step = cell + gap                       # center-to-center within a band
    band_height = WORKDAYS_PER_WEEK * cell + (WORKDAYS_PER_WEEK - 1) * gap
    band_step = band_height + band_gap

    # Center the whole grid in the usable area.
    grid_w = weeks_per_band * cell + (weeks_per_band - 1) * gap
    grid_h = layout["bands"] * band_height + (layout["bands"] - 1) * band_gap
    origin_x = (WIDTH - grid_w) / 2
    origin_y = (HEIGHT - grid_h) / 2

    for d in workdays:
        wk = week_index(d, start)
        band = wk // weeks_per_band
        col = wk % weeks_per_band
        row = d.weekday()  # 0=Mon .. 4=Fri

        x0 = origin_x + col * step
        y0 = origin_y + band * band_step + row * step
        x1 = x0 + cell
        y1 = y0 + cell

        box = [round(x0), round(y0), round(x1) - 1, round(y1) - 1]
        if d <= today:
            draw.rectangle(box, fill=BLACK)
        else:
            draw.rectangle(box, outline=BLACK, width=1)

    return img


def main():
    output_file = sys.argv[1] if len(sys.argv) > 1 else "workdays.png"
    now = datetime.now(NYC_TZ)
    img = create_image(now)
    img.save(output_file)
    print(f"Generated {output_file}")


if __name__ == "__main__":
    main()
