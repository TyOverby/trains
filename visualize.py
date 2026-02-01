#!/usr/bin/env python3
"""Generate a PNG visualization of train schedules from JSON data."""

import json
import sys
from datetime import datetime, timedelta, timezone
from io import BytesIO

import cairosvg
import svgwrite
from PIL import Image

# Visualization settings (800x480 for e-ink display)
HOURS_TO_SHOW = 3
WIDTH = 800
HEIGHT = 480
LEFT_MARGIN = 50  # Space for axis
RIGHT_MARGIN = 20
TOP_MARGIN = 50
BOTTOM_MARGIN = 40

# Colors (black and white for e-ink)
BAR_COLOR = "#000000"
TEXT_COLOR = "#000000"
TEXT_ON_BAR_COLOR = "#ffffff"
GRID_COLOR = "#cccccc"
NOW_LINE_COLOR = "#000000"


def round_down_to_30min(t: datetime) -> datetime:
    """Round a datetime down to the nearest 30-minute increment."""
    minute = t.minute
    rounded_minute = (minute // 30) * 30
    return t.replace(minute=rounded_minute, second=0, microsecond=0)


def parse_time(time_str: str | None) -> datetime | None:
    """Parse ISO format time string to datetime."""
    if not time_str:
        return None
    try:
        return datetime.fromisoformat(time_str)
    except ValueError:
        return None


def get_segment_times(segment: dict) -> tuple[datetime | None, datetime | None]:
    """Get departure and arrival times for a segment."""
    dep = parse_time(segment["from"].get("actual") or segment["from"].get("scheduled"))
    arr = parse_time(segment["to"].get("actual") or segment["to"].get("scheduled"))
    return dep, arr


def filter_trains_in_window(trains: list[dict], start_time: datetime, end: datetime, now: datetime) -> list[dict]:
    """Filter trains that haven't departed yet and are within the time window."""
    filtered = []
    for train in trains:
        segments = train.get("segments", [])
        if not segments:
            continue

        # Get the first segment's departure time
        first_dep, _ = get_segment_times(segments[0])
        if first_dep is None:
            continue

        # Only include trains that haven't departed yet and depart before window ends
        if first_dep >= now and first_dep <= end:
            # Parse all segment times
            parsed_segments = []
            for seg in segments:
                dep, arr = get_segment_times(seg)
                if dep and arr:
                    parsed_segments.append({
                        **seg,
                        "_dep": dep,
                        "_arr": arr,
                    })

            if parsed_segments:
                filtered.append({
                    **train,
                    "_segments": parsed_segments,
                    "_first_dep": first_dep,
                })

    # Sort by first departure time
    filtered.sort(key=lambda t: t["_first_dep"])
    return filtered


def time_to_x(t: datetime, start_time: datetime, end: datetime) -> float:
    """Convert a time to an x coordinate."""
    total_seconds = (end - start_time).total_seconds()
    elapsed_seconds = (t - start_time).total_seconds()
    ratio = elapsed_seconds / total_seconds
    return LEFT_MARGIN + ratio * (WIDTH - LEFT_MARGIN - RIGHT_MARGIN)


def format_time_label(t: datetime) -> str:
    """Format time for axis labels (12-hour format, no am/pm)."""
    return t.strftime("%-I:%M")


def create_svg(trains: list[dict], stations: list[str], now: datetime) -> str:
    """Create an SVG visualization of the train schedule."""
    # Round start time down to nearest 30-minute increment
    start_time = round_down_to_30min(now)
    end = start_time + timedelta(hours=HOURS_TO_SHOW)

    # Filter trains in our time window (only those that haven't departed yet)
    visible_trains = filter_trains_in_window(trains, start_time, end, now)

    title = "Trains: " + " -> ".join(stations)

    if not visible_trains:
        # Create a simple "no trains" SVG
        dwg = svgwrite.Drawing(size=(WIDTH, HEIGHT))
        dwg.add(dwg.rect((0, 0), (WIDTH, HEIGHT), fill="#ffffff"))
        dwg.add(dwg.text(
            f"No trains for {' -> '.join(stations)} in the next {HOURS_TO_SHOW} hours",
            insert=(WIDTH / 2, HEIGHT / 2),
            text_anchor="middle",
            font_size="16px",
            font_family="sans-serif",
            fill=TEXT_COLOR,
        ))
        return dwg.tostring()

    # Calculate row height based on available space and number of trains
    available_height = HEIGHT - TOP_MARGIN - BOTTOM_MARGIN
    row_height = available_height / len(visible_trains)

    dwg = svgwrite.Drawing(size=(WIDTH, HEIGHT))

    # Background
    dwg.add(dwg.rect((0, 0), (WIDTH, HEIGHT), fill="#ffffff"))

    # Title
    dwg.add(dwg.text(
        title,
        insert=(WIDTH / 2, 25),
        text_anchor="middle",
        font_size="18px",
        font_family="sans-serif",
        font_weight="bold",
        fill=TEXT_COLOR,
    ))

    # Draw time axis
    chart_left = LEFT_MARGIN
    chart_right = WIDTH - RIGHT_MARGIN
    chart_top = TOP_MARGIN
    chart_bottom = HEIGHT - BOTTOM_MARGIN

    # Axis line
    dwg.add(dwg.line(
        (chart_left, chart_bottom),
        (chart_right, chart_bottom),
        stroke=TEXT_COLOR,
        stroke_width=1,
    ))

    # Time markers (every 30 minutes)
    marker_time = start_time
    while marker_time <= end:
        x = time_to_x(marker_time, start_time, end)

        # Vertical grid line
        dwg.add(dwg.line(
            (x, chart_top),
            (x, chart_bottom),
            stroke=GRID_COLOR,
            stroke_width=1,
        ))

        # Time label
        dwg.add(dwg.text(
            format_time_label(marker_time),
            insert=(x, chart_bottom + 20),
            text_anchor="middle",
            font_size="12px",
            font_family="sans-serif",
            fill=TEXT_COLOR,
        ))

        marker_time += timedelta(minutes=30)

    # "Now" indicator
    now_x = time_to_x(now, start_time, end)
    dwg.add(dwg.line(
        (now_x, chart_top - 5),
        (now_x, chart_bottom),
        stroke=NOW_LINE_COLOR,
        stroke_width=2,
        stroke_dasharray="4,2",
    ))
    dwg.add(dwg.text(
        "Now",
        insert=(now_x, chart_top - 10),
        text_anchor="middle",
        font_size="10px",
        font_family="sans-serif",
        fill=NOW_LINE_COLOR,
    ))

    # Draw train bars
    bar_height = row_height * 0.6

    for i, train in enumerate(visible_trains):
        y = chart_top + i * row_height + row_height / 2
        segments = train["_segments"]

        # Find the longest segment (by pixel width) to put the train name in
        segment_widths = []
        for seg in segments:
            dep = seg["_dep"]
            arr = seg["_arr"]
            visible_dep = max(dep, start_time)
            visible_arr = min(arr, end)
            x1 = time_to_x(visible_dep, start_time, end)
            x2 = time_to_x(visible_arr, start_time, end)
            segment_widths.append(x2 - x1)

        longest_segment_idx = segment_widths.index(max(segment_widths))

        # First pass: draw bars and collect positions for intermediate times
        segment_positions = []  # List of (x1, x2, dep, arr, seg_idx, seg) for visible segments

        for seg_idx, seg in enumerate(segments):
            dep = seg["_dep"]
            arr = seg["_arr"]

            # Clamp times to visible window
            visible_dep = max(dep, start_time)
            visible_arr = min(arr, end)

            # Skip if segment is entirely outside window
            if visible_arr <= start_time or visible_dep >= end:
                continue

            x1 = time_to_x(visible_dep, start_time, end)
            x2 = time_to_x(visible_arr, start_time, end)
            bar_width = x2 - x1

            segment_positions.append((x1, x2, dep, arr, seg_idx, seg))

            # Draw bar
            dwg.add(dwg.rect(
                (x1, y - bar_height / 2),
                (max(bar_width, 2), bar_height),
                fill=BAR_COLOR,
                rx=3,
                ry=3,
            ))

            # Train label only in the longest segment
            if seg_idx == longest_segment_idx and bar_width > 60:
                route = train.get("route_name") or "Train"
                train_num = train.get("train_num", "")
                label = f"{route} #{train_num}"
                bar_center_x = (x1 + x2) / 2

                dwg.add(dwg.text(
                    label,
                    insert=(bar_center_x, y + 5),
                    text_anchor="middle",
                    font_size="12px",
                    font_family="sans-serif",
                    font_weight="bold",
                    fill=TEXT_ON_BAR_COLOR,
                ))

        # Second pass: draw times above the bars and station codes inside the bars
        time_y = y - bar_height / 2 - 3

        for pos_idx, (x1, x2, dep, arr, seg_idx, seg) in enumerate(segment_positions):
            bar_width = x2 - x1
            is_first = pos_idx == 0
            is_last = pos_idx == len(segment_positions) - 1

            from_station = seg["from"]["station_code"]
            to_station = seg["to"]["station_code"]

            # Departure time above left edge of first bar
            if is_first:
                dwg.add(dwg.text(
                    format_time_label(dep),
                    insert=(x1, time_y),
                    text_anchor="start",
                    font_size="9px",
                    font_family="sans-serif",
                    fill=TEXT_COLOR,
                ))

            # Arrival time above right edge of last bar
            if is_last and arr <= end:
                dwg.add(dwg.text(
                    format_time_label(arr),
                    insert=(x2, time_y),
                    text_anchor="end",
                    font_size="9px",
                    font_family="sans-serif",
                    fill=TEXT_COLOR,
                ))

            # Intermediate time centered between this bar and the next
            if not is_last:
                next_x1 = segment_positions[pos_idx + 1][0]
                gap_center = (x2 + next_x1) / 2

                dwg.add(dwg.text(
                    format_time_label(arr),
                    insert=(gap_center, time_y),
                    text_anchor="middle",
                    font_size="9px",
                    font_family="sans-serif",
                    fill=TEXT_COLOR,
                ))

            # Station codes: from station on left of first bar, to station on right of last bar
            if bar_width > 30:
                # From station on left side of first bar only
                if is_first:
                    dwg.add(dwg.text(
                        from_station,
                        insert=(x1 + 3, y + 4),
                        font_size="9px",
                        font_family="sans-serif",
                        fill=TEXT_ON_BAR_COLOR,
                    ))

                # To station on right side of last bar only
                if is_last:
                    dwg.add(dwg.text(
                        to_station,
                        insert=(x2 - 3, y + 4),
                        text_anchor="end",
                        font_size="9px",
                        font_family="sans-serif",
                        fill=TEXT_ON_BAR_COLOR,
                    ))

            # Intermediate station code centered between bars, same y as other station codes
            if not is_last:
                next_x1 = segment_positions[pos_idx + 1][0]
                gap_center = (x2 + next_x1) / 2

                # Black background behind white text so it's visible in narrow gaps
                dwg.add(dwg.rect(
                    (gap_center - 15, y - 6),
                    (30, 14),
                    fill=BAR_COLOR,
                ))

                dwg.add(dwg.text(
                    to_station,
                    insert=(gap_center, y + 4),
                    text_anchor="middle",
                    font_size="9px",
                    font_family="sans-serif",
                    fill=TEXT_ON_BAR_COLOR,
                ))

    return dwg.tostring()


def main():
    if len(sys.argv) < 2:
        print("Usage: uv run visualize.py <json_file> [output.png]")
        print("Example: uv run visualize.py trains_NYP_NWK_PHL.json")
        sys.exit(1)

    json_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else json_file.replace(".json", ".png")

    # Load JSON data
    with open(json_file) as f:
        data = json.load(f)

    stations = data["stations"]
    trains = data["trains"]

    # Use current time
    now = datetime.now().astimezone()

    # Generate SVG
    svg_content = create_svg(trains, stations, now)

    # Convert to PNG at 3x resolution for better text quality
    png_buffer = BytesIO()
    cairosvg.svg2png(bytestring=svg_content.encode(), write_to=png_buffer, scale=3)

    # Resize down and convert to 1-bit black and white for e-ink
    png_buffer.seek(0)
    img = Image.open(png_buffer)
    img = img.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
    img = img.convert("L")  # Convert to grayscale first
    img = img.point(lambda x: 255 if x > 128 else 0, mode="1")  # Threshold to 1-bit
    img.save(output_file)
    print(f"Generated {output_file}")


if __name__ == "__main__":
    main()
