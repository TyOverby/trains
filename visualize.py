#!/usr/bin/env python3
"""Generate a PNG visualization of train schedules from JSON data using bitmap rendering."""

import json
import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from PIL import Image  # type: ignore

NYC_TZ = ZoneInfo("America/New_York")

# Visualization settings (800x480 for e-ink display)
HOURS_TO_SHOW = 3
WIDTH = 800
HEIGHT = 480
LEFT_MARGIN = 50
RIGHT_MARGIN = 40
TOP_MARGIN = 0
BOTTOM_MARGIN = 40

# Colors (1-bit: 0=black, 1=white)
BLACK = 0
WHITE = 1


def load_font(font_path: str) -> dict:
    """Load bitmap font from JSON file."""
    with open(font_path) as f:
        font_data = json.load(f)

    font = {}
    for char_info in font_data:
        char = char_info["char"]
        # Convert 'X' and ' ' to boolean rows
        pixels = []
        for row in char_info["pixels"]:
            pixels.append([c == 'X' for c in row])
        font[char] = {
            "pixels": pixels,
            "width": char_info["width"],
        }

    # Map uppercase to lowercase since font only has lowercase
    for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        lower = c.lower()
        if lower in font and c not in font:
            font[c] = font[lower]

    # Add space character if not present
    if ' ' not in font:
        font[' '] = {
            "pixels": [[False] * 7 for _ in range(11)],
            "width": 7,
        }

    # Add colon if not present (for time display)
    if ':' not in font:
        font[':'] = {
            "pixels": [
                [False, False, False, False, False, False, False],
                [False, False, False, False, False, False, False],
                [False, False, False, True, False, False, False],
                [False, False, False, True, False, False, False],
                [False, False, False, False, False, False, False],
                [False, False, False, False, False, False, False],
                [False, False, False, True, False, False, False],
                [False, False, False, True, False, False, False],
                [False, False, False, False, False, False, False],
                [False, False, False, False, False, False, False],
                [False, False, False, False, False, False, False],
            ],
            "width": 7,
        }

    # Add hyphen/dash if not present
    if '-' not in font:
        font['-'] = {
            "pixels": [
                [False, False, False, False, False, False, False],
                [False, False, False, False, False, False, False],
                [False, False, False, False, False, False, False],
                [False, False, False, False, False, False, False],
                [False, True, True, True, True, True, False],
                [False, False, False, False, False, False, False],
                [False, False, False, False, False, False, False],
                [False, False, False, False, False, False, False],
                [False, False, False, False, False, False, False],
                [False, False, False, False, False, False, False],
                [False, False, False, False, False, False, False],
            ],
            "width": 7,
        }

    # Add > if not present
    if '>' not in font:
        font['>'] = {
            "pixels": [
                [False, False, False, False, False, False, False],
                [False, True, False, False, False, False, False],
                [False, False, True, False, False, False, False],
                [False, False, False, True, False, False, False],
                [False, False, False, False, True, False, False],
                [False, False, False, True, False, False, False],
                [False, False, True, False, False, False, False],
                [False, True, False, False, False, False, False],
                [False, False, False, False, False, False, False],
                [False, False, False, False, False, False, False],
                [False, False, False, False, False, False, False],
            ],
            "width": 7,
        }

    # Add # if not present
    if '#' not in font:
        font['#'] = {
            "pixels": [
                [False, False, False, False, False, False, False],
                [False, False, True, False, True, False, False],
                [False, False, True, False, True, False, False],
                [False, True, True, True, True, True, False],
                [False, False, True, False, True, False, False],
                [False, True, True, True, True, True, False],
                [False, False, True, False, True, False, False],
                [False, False, True, False, True, False, False],
                [False, False, False, False, False, False, False],
                [False, False, False, False, False, False, False],
                [False, False, False, False, False, False, False],
            ],
            "width": 7,
        }

    return font


# Load font from departure.json
FONT_PATH = os.path.join(os.path.dirname(__file__), "departure.json")
FONT_DATA = load_font(FONT_PATH)
CHAR_WIDTH = 7
CHAR_HEIGHT = 11
CHAR_SPACING = 1
FONT_SCALE = 2  # Each font pixel becomes a 2x2 block


def draw_char(img, x: int, y: int, char: str, color: int, scale: int = FONT_SCALE) -> int:
    """Draw a single character at the given position. Returns the scaled width drawn."""
    if char not in FONT_DATA:
        char = ' '
    if char not in FONT_DATA:
        return CHAR_WIDTH * scale

    char_data = FONT_DATA[char]
    pixels = char_data["pixels"]
    width = char_data["width"]

    for row_idx, row in enumerate(pixels):
        for col_idx, is_set in enumerate(row):
            if is_set:
                # Draw a scale x scale block for each pixel
                for dy in range(scale):
                    for dx in range(scale):
                        px = x + col_idx * scale + dx
                        py = y + row_idx * scale + dy
                        if 0 <= px < WIDTH and 0 <= py < HEIGHT:
                            img.putpixel((px, py), color)

    return width * scale


def draw_text(img, x: int, y: int, text: str, color: int, anchor: str = "left", scale: int = FONT_SCALE) -> None:
    """Draw text at the given position with the specified anchor."""
    text_width = get_text_width(text, scale)

    if anchor == "center":
        x = x - text_width // 2
    elif anchor == "right":
        x = x - text_width

    for char in text:
        char_width = draw_char(img, x, y, char, color, scale)
        x += char_width + CHAR_SPACING * scale


def get_text_width(text: str, scale: int = FONT_SCALE) -> int:
    """Get the pixel width of a text string (scaled)."""
    if not text:
        return 0
    total = 0
    for char in text:
        if char in FONT_DATA:
            total += FONT_DATA[char]["width"] * scale
        else:
            total += CHAR_WIDTH * scale
    total += (len(text) - 1) * CHAR_SPACING * scale
    return total


def draw_rect(img, x1: int, y1: int, x2: int, y2: int, color: int) -> None:
    """Draw a filled rectangle."""
    for py in range(max(0, y1), min(HEIGHT, y2)):
        for px in range(max(0, x1), min(WIDTH, x2)):
            img.putpixel((px, py), color)


def draw_checkerboard(img, x1: int, y1: int, x2: int, y2: int) -> None:
    """Draw a checkerboard pattern (1px alternating black and white) with black border."""
    for py in range(max(0, y1), min(HEIGHT, y2)):
        for px in range(max(0, x1), min(WIDTH, x2)):
            # Black border on edges
            if py == y1 or py == y2 - 1 or px == x1 or px == x2 - 1:
                img.putpixel((px, py), BLACK)
            else:
                # 1px checkerboard pattern
                color = BLACK if (px + py) % 2 == 0 else WHITE
                img.putpixel((px, py), color)


def draw_hline(img, x1: int, x2: int, y: int, color: int) -> None:
    """Draw a horizontal line."""
    if 0 <= y < HEIGHT:
        for px in range(max(0, x1), min(WIDTH, x2)):
            img.putpixel((px, y), color)


def draw_vline(img, x: int, y1: int, y2: int, color: int, dashed: bool = False) -> None:
    """Draw a vertical line, optionally dashed."""
    if 0 <= x < WIDTH:
        for py in range(max(0, y1), min(HEIGHT, y2)):
            if dashed and (py // 4) % 2 == 1:
                continue
            img.putpixel((x, py), color)


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
        return datetime.fromisoformat(time_str).astimezone(NYC_TZ)
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

        first_dep, _ = get_segment_times(segments[0])
        if first_dep is None:
            continue

        if first_dep >= now and first_dep <= end:
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

    filtered.sort(key=lambda t: t["_first_dep"])
    return filtered


def time_to_x(t: datetime, start_time: datetime, end: datetime) -> int:
    """Convert a time to an x coordinate."""
    total_seconds = (end - start_time).total_seconds()
    elapsed_seconds = (t - start_time).total_seconds()
    ratio = elapsed_seconds / total_seconds
    return int(LEFT_MARGIN + ratio * (WIDTH - LEFT_MARGIN - RIGHT_MARGIN))


def format_time_label(t: datetime) -> str:
    """Format time for axis labels (12-hour format, no am/pm)."""
    return t.strftime("%-I:%M")


def create_image(trains: list[dict], stations: list[str], now: datetime,
                 buffer_before: int = 0, buffer_after: int = 0) -> Image.Image:
    """Create a 1-bit image visualization of the train schedule.

    Args:
        buffer_before: Minutes of checkerboard buffer before each train bar
        buffer_after: Minutes of checkerboard buffer after each train bar
    """
    img = Image.new("1", (WIDTH, HEIGHT), WHITE)

    start_time = round_down_to_30min(now)
    end = start_time + timedelta(hours=HOURS_TO_SHOW)

    visible_trains = filter_trains_in_window(trains, start_time, end, now)

    if not visible_trains:
        msg = f"No trains in next {HOURS_TO_SHOW} hours"
        draw_text(img, WIDTH // 2, HEIGHT // 2 - CHAR_HEIGHT * FONT_SCALE // 2, msg, BLACK, anchor="center")
        return img

    # Calculate row height
    available_height = HEIGHT - TOP_MARGIN - BOTTOM_MARGIN
    row_height = available_height // len(visible_trains)
    # Bar height: station codes (scale=1) + 2px gap + train name (scale=2) + padding
    bar_height = CHAR_HEIGHT + 2 + CHAR_HEIGHT * FONT_SCALE + 4  # top/bottom padding

    chart_left = LEFT_MARGIN
    chart_right = WIDTH - RIGHT_MARGIN
    chart_top = TOP_MARGIN
    chart_bottom = HEIGHT - BOTTOM_MARGIN

    # Draw generation timestamp in top right corner
    timestamp_str = now.strftime("%b %-d, %Y %-I:%M%p").lower()
    timestamp_width = get_text_width(timestamp_str, scale=1)
    timestamp_x = WIDTH - 4  # 4px from right edge
    timestamp_y = 4  # 4px from top
    # White background
    draw_rect(img, timestamp_x - timestamp_width - 2, timestamp_y - 1,
              timestamp_x + 2, timestamp_y + CHAR_HEIGHT + 1, WHITE)
    draw_text(img, timestamp_x, timestamp_y, timestamp_str, BLACK, anchor="right", scale=1)

    # Bottom axis line (full width)
    draw_hline(img, 0, WIDTH, chart_bottom, BLACK)

    # Time markers (every 30 minutes)
    marker_time = start_time
    while marker_time <= end:
        x = time_to_x(marker_time, start_time, end)

        # Vertical grid line (light - draw every other pixel)
        for py in range(chart_top, chart_bottom):
            if py % 3 == 0:
                img.putpixel((x, py), BLACK)

        # Time label
        label = format_time_label(marker_time)
        draw_text(img, x, chart_bottom + 8, label, BLACK, anchor="center")

        marker_time += timedelta(minutes=30)

    # "Now" indicator (line only)
    now_x = time_to_x(now, start_time, end)
    draw_vline(img, now_x, chart_top - 5, chart_bottom, BLACK, dashed=True)

    # Draw train bars
    for i, train in enumerate(visible_trains):
        y_center = chart_top + i * row_height + row_height // 2
        segments = train["_segments"]

        # Find longest segment for train name
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

        # Collect segment positions
        segment_positions = []

        for seg_idx, seg in enumerate(segments):
            dep = seg["_dep"]
            arr = seg["_arr"]

            visible_dep = max(dep, start_time)
            visible_arr = min(arr, end)

            if visible_arr <= start_time or visible_dep >= end:
                continue

            x1 = time_to_x(visible_dep, start_time, end)
            # Extend bars that reach the end of the window to the edge of the image
            x2 = WIDTH if arr >= end else time_to_x(visible_arr, start_time, end)
            bar_width = x2 - x1

            segment_positions.append((x1, x2, dep, arr, seg_idx, seg))

            # Draw bar
            bar_top = y_center - bar_height // 2
            bar_bottom = y_center + bar_height // 2
            draw_rect(img, x1, bar_top, x2, bar_bottom, BLACK)

        # Calculate full block extent for centering train name
        if segment_positions:
            block_x1 = segment_positions[0][0]  # First segment's left edge
            block_x2 = segment_positions[-1][1]  # Last segment's right edge

            # Draw checkerboard buffers before and after the train
            bar_top = y_center - bar_height // 2
            bar_bottom = y_center + bar_height // 2

            if buffer_before > 0:
                first_dep = segment_positions[0][2]  # dep time of first segment
                buffer_start_time = first_dep - timedelta(minutes=buffer_before)
                buffer_start_x = time_to_x(max(buffer_start_time, start_time), start_time, end)
                if buffer_start_x < block_x1:
                    draw_checkerboard(img, buffer_start_x, bar_top, block_x1, bar_bottom)

            if buffer_after > 0:
                last_arr = segment_positions[-1][3]  # arr time of last segment
                buffer_end_time = last_arr + timedelta(minutes=buffer_after)
                buffer_end_x = time_to_x(min(buffer_end_time, end), start_time, end)
                # If the bar extends to edge, start checkerboard from there
                if block_x2 >= WIDTH:
                    pass  # No room for buffer after
                elif buffer_end_x > block_x2:
                    draw_checkerboard(img, block_x2, bar_top, min(buffer_end_x, WIDTH), bar_bottom)

        # Draw times and station codes (scale=1 for times)
        time_y = y_center - bar_height // 2 - CHAR_HEIGHT - 3

        # Collect all time labels with their positions first, then check for overlaps
        time_labels = []

        for pos_idx, (x1, x2, dep, arr, seg_idx, seg) in enumerate(segment_positions):
            is_first = pos_idx == 0
            is_last = pos_idx == len(segment_positions) - 1

            # Departure time above first bar (left-aligned)
            if is_first:
                label = format_time_label(dep)
                label_width = get_text_width(label, scale=1)
                time_labels.append((x1, x1 + label_width, label))

            # Intermediate time (centered in gap)
            if not is_last:
                next_x1 = segment_positions[pos_idx + 1][0]
                gap_center = (x2 + next_x1) // 2
                label = format_time_label(arr)
                label_width = get_text_width(label, scale=1)
                time_labels.append((gap_center - label_width // 2, gap_center + label_width // 2, label))

            # Arrival time above last bar (right-aligned)
            if is_last and arr <= end:
                label = format_time_label(arr)
                label_width = get_text_width(label, scale=1)
                time_labels.append((x2 - label_width, x2, label))

        # Draw time labels, skipping overlaps
        min_gap = 4
        last_right = -1000
        for left, right, label in time_labels:
            if left > last_right + min_gap:
                # Draw white background to cover dashed lines
                bg_pad = 1
                draw_rect(img, left - bg_pad, time_y - bg_pad, right + bg_pad, time_y + CHAR_HEIGHT + bg_pad, WHITE)
                # Determine anchor based on position
                if left == time_labels[0][0] and time_labels[0][2] == label:
                    draw_text(img, left, time_y, label, BLACK, anchor="left", scale=1)
                else:
                    center = (left + right) // 2
                    draw_text(img, center, time_y, label, BLACK, anchor="center", scale=1)
                last_right = right

        # Calculate vertical positions for two rows of text
        bar_top = y_center - bar_height // 2
        bar_bottom = y_center + bar_height // 2
        text_padding = 2
        padding = 4
        station_y = bar_top + text_padding  # Station codes at top (scale=1)
        train_name_y = bar_bottom - CHAR_HEIGHT * FONT_SCALE - text_padding  # Train name at bottom (scale=2)

        for pos_idx, (x1, x2, dep, arr, seg_idx, seg) in enumerate(segment_positions):
            bar_width = x2 - x1
            is_first = pos_idx == 0
            is_last = pos_idx == len(segment_positions) - 1

            from_station = seg["from"]["station_code"]
            to_station = seg["to"]["station_code"]

            # Station codes at top of bars (scale=1)
            min_width_for_station = get_text_width("XXX", scale=1) + padding * 2
            if bar_width > min_width_for_station:
                if is_first:
                    draw_text(img, x1 + padding, station_y, from_station, WHITE, anchor="left", scale=1)
                if is_last:
                    draw_text(img, x2 - padding, station_y, to_station, WHITE, anchor="right", scale=1)

            # Intermediate station code
            if not is_last:
                next_x1 = segment_positions[pos_idx + 1][0]
                gap_center = (x2 + next_x1) // 2

                # Draw black background for station code
                code_width = get_text_width(to_station, scale=1)
                bg_padding = 2
                bg_x1 = gap_center - code_width // 2 - bg_padding
                bg_x2 = gap_center + code_width // 2 + bg_padding
                bg_y1 = station_y - 1
                bg_y2 = station_y + CHAR_HEIGHT + 1
                draw_rect(img, bg_x1, bg_y1, bg_x2, bg_y2, BLACK)

                draw_text(img, gap_center, station_y, to_station, WHITE, anchor="center", scale=1)

        # Train name centered across the full block (all segments combined, scale=2)
        if segment_positions:
            route = train.get("route_name") or "Train"
            if route == "Northeast Regional":
                route = "NE Regional"
            train_num = train.get("train_num", "")
            label = f"{route} {train_num}"
            label_width = get_text_width(label)  # defaults to scale=2
            center_x = (block_x1 + block_x2) // 2
            train_padding = 8  # larger padding for scale=2 text

            # Check if centering would clip on the right
            if center_x + label_width // 2 > WIDTH:
                # Left-align with padding
                draw_text(img, block_x1 + train_padding, train_name_y, label, WHITE, anchor="left")
            # Check if centering would clip on the left
            elif center_x - label_width // 2 < 0:
                # Right-align with padding
                draw_text(img, block_x2 - train_padding, train_name_y, label, WHITE, anchor="right")
            else:
                draw_text(img, center_x, train_name_y, label, WHITE, anchor="center")

    return img


def main():
    if len(sys.argv) < 2:
        print("Usage: uv run visualize.py <json_file> [output.png]")
        print("Example: uv run visualize.py trains_NYP_NWK_PHL.json")
        sys.exit(1)

    json_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else json_file.replace(".json", ".png")

    with open(json_file) as f:
        data = json.load(f)

    stations = data["stations"]
    trains = data["trains"]

    now = datetime.now(NYC_TZ)

    img = create_image(trains, stations, now)
    img.save(output_file)
    print(f"Generated {output_file}")


if __name__ == "__main__":
    main()
