#!/usr/bin/env python3
"""Generate a PNG visualization of train schedules from JSON data using bitmap rendering."""

import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from PIL import Image  # type: ignore

NYC_TZ = ZoneInfo("America/New_York")

# Time window displayed (independent of resolution).
HOURS_TO_SHOW = 3

# Colors (1-bit: 0=black, 1=white)
BLACK = 0
WHITE = 1


@dataclass(frozen=True)
class RenderConfig:
    """Resolution-dependent layout knobs.

    The renderer draws natively at ``width`` x ``height``. Text stays crisp at
    any size because the bitmap font is always drawn at an integer scale
    (``font_scale`` / ``label_scale``). ``ui`` multiplies every fixed pixel
    padding/offset so spacing grows with the resolution. The high-res config is
    a clean 2x of the base design (font_scale/label_scale/ui all doubled), so
    the two outputs are proportionally identical -- only sharper.
    """

    width: int
    height: int
    left_margin: int
    right_margin: int
    top_margin: int
    bottom_margin: int
    font_scale: int   # large text: train names and axis labels
    label_scale: int  # small text: times, station codes, timestamp
    ui: int           # multiplier for fixed paddings/offsets (base = 1)


# Native 800x480 e-ink target (original design).
BASE_CONFIG = RenderConfig(
    width=800, height=480,
    left_margin=50, right_margin=40, top_margin=0, bottom_margin=40,
    font_scale=2, label_scale=1, ui=1,
)

# Native 1872x1404 e-ink target: a 2x scale-up of the base design, rendered
# natively so the bitmap font never picks up fractional-scaling artifacts.
HIRES_CONFIG = RenderConfig(
    width=1872, height=1404,
    left_margin=100, right_margin=80, top_margin=0, bottom_margin=80,
    font_scale=4, label_scale=2, ui=2,
)


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
FONT_SCALE = 2  # Default large-text scale (base config); each font pixel -> 2x2 block


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
                        if 0 <= px < img.width and 0 <= py < img.height:
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
    for py in range(max(0, y1), min(img.height, y2)):
        for px in range(max(0, x1), min(img.width, x2)):
            img.putpixel((px, py), color)


def draw_checkerboard(img, x1: int, y1: int, x2: int, y2: int) -> None:
    """Draw a checkerboard pattern (1px alternating black and white) with black border."""
    for py in range(max(0, y1), min(img.height, y2)):
        for px in range(max(0, x1), min(img.width, x2)):
            # Black border on edges
            if py == y1 or py == y2 - 1 or px == x1 or px == x2 - 1:
                img.putpixel((px, py), BLACK)
            else:
                # 1px checkerboard pattern
                color = BLACK if (px + py) % 2 == 0 else WHITE
                img.putpixel((px, py), color)


def draw_hline(img, x1: int, x2: int, y: int, color: int) -> None:
    """Draw a horizontal line."""
    if 0 <= y < img.height:
        for px in range(max(0, x1), min(img.width, x2)):
            img.putpixel((px, y), color)


def draw_vline(img, x: int, y1: int, y2: int, color: int, dashed: bool = False, dash: int = 4) -> None:
    """Draw a vertical line, optionally dashed (dash = on/off run length in px)."""
    if 0 <= x < img.width:
        for py in range(max(0, y1), min(img.height, y2)):
            if dashed and (py // dash) % 2 == 1:
                continue
            img.putpixel((x, py), color)


def round_down_to_30min(t: datetime) -> datetime:
    """Round a datetime down to the nearest 30-minute increment."""
    minute = t.minute
    rounded_minute = (minute // 30) * 30
    return t.replace(minute=rounded_minute, second=0, microsecond=0)


def round_up_to_30min(t: datetime) -> datetime:
    """Round a datetime up to the nearest 30-minute increment."""
    if t.minute % 30 == 0 and t.second == 0 and t.microsecond == 0:
        return t
    return round_down_to_30min(t) + timedelta(minutes=30)


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

    # If arrival is before departure (e.g. delayed departure but stale arrival
    # estimate), reconstruct arrival using the scheduled duration.
    if dep and arr and arr < dep:
        sched_dep = parse_time(segment["from"].get("scheduled"))
        sched_arr = parse_time(segment["to"].get("scheduled"))
        if sched_dep and sched_arr and sched_arr >= sched_dep:
            arr = dep + (sched_arr - sched_dep)

    return dep, arr


def filter_trains_in_window(trains: list[dict], start_time: datetime, end: datetime, now: datetime) -> list[dict]:
    """Filter trains that are still en route or upcoming and within the time window."""
    filtered = []
    for train in trains:
        segments = train.get("segments", [])
        if not segments:
            continue

        first_dep, _ = get_segment_times(segments[0])
        _, last_arr = get_segment_times(segments[-1])
        if first_dep is None or last_arr is None:
            continue

        # Show train if it hasn't completed its journey and departs within the window
        if last_arr >= now and first_dep <= end:
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


def time_to_x(t: datetime, start_time: datetime, end: datetime, cfg: RenderConfig) -> int:
    """Convert a time to an x coordinate."""
    total_seconds = (end - start_time).total_seconds()
    elapsed_seconds = (t - start_time).total_seconds()
    ratio = elapsed_seconds / total_seconds
    return int(cfg.left_margin + ratio * (cfg.width - cfg.left_margin - cfg.right_margin))


def format_time_label(t: datetime) -> str:
    """Format time for axis labels (12-hour format, no am/pm)."""
    return t.strftime("%-I:%M")


def create_image(trains: list[dict], stations: list[str], now: datetime,
                 buffer_before: int = 0, buffer_after: int = 0,
                 cache_age_seconds: float | None = None,
                 cfg: RenderConfig = BASE_CONFIG) -> Image.Image:
    """Create a 1-bit image visualization of the train schedule.

    Args:
        buffer_before: Minutes of checkerboard buffer before each train bar
        buffer_after: Minutes of checkerboard buffer after each train bar
        cache_age_seconds: Age of the most stale cache entry, shown below the timestamp
        cfg: Resolution/layout config (BASE_CONFIG or HIRES_CONFIG)
    """
    # Local aliases keep the layout math readable.
    fs, ls, ui = cfg.font_scale, cfg.label_scale, cfg.ui

    img = Image.new("1", (cfg.width, cfg.height), WHITE)

    start_time = round_down_to_30min(now)
    end = round_up_to_30min(now + timedelta(hours=HOURS_TO_SHOW))

    visible_trains = filter_trains_in_window(trains, start_time, end, now)
    compact = len(visible_trains) > 8

    if not visible_trains:
        msg = f"No trains in next {HOURS_TO_SHOW} hours"
        draw_text(img, cfg.width // 2, cfg.height // 2 - CHAR_HEIGHT * fs // 2, msg, BLACK,
                  anchor="center", scale=fs)
        return img

    # Calculate row height
    available_height = cfg.height - cfg.top_margin - cfg.bottom_margin
    row_height = available_height // len(visible_trains)
    # Bar height depends on rendering mode
    if compact:
        bar_height = CHAR_HEIGHT * fs + 6 * ui  # just train name + padding
    else:
        bar_height = CHAR_HEIGHT * ls + 2 * ui + CHAR_HEIGHT * fs + 4 * ui  # station codes + train name + padding

    chart_left = cfg.left_margin
    chart_right = cfg.width - cfg.right_margin
    chart_top = cfg.top_margin
    chart_bottom = cfg.height - cfg.bottom_margin

    # Draw generation timestamp in top right corner
    timestamp_str = now.strftime("%b %-d, %Y %-I:%M%p").lower()
    timestamp_width = get_text_width(timestamp_str, scale=ls)
    timestamp_x = cfg.width - 4 * ui  # 4px from right edge
    timestamp_y = 4 * ui  # 4px from top
    # White background
    draw_rect(img, timestamp_x - timestamp_width - 2 * ui, timestamp_y - 1 * ui,
              timestamp_x + 2 * ui, timestamp_y + CHAR_HEIGHT * ls + 1 * ui, WHITE)
    draw_text(img, timestamp_x, timestamp_y, timestamp_str, BLACK, anchor="right", scale=ls)

    # Cache age below the timestamp
    if cache_age_seconds is not None:
        age_minutes = int(cache_age_seconds) // 60
        age_seconds = int(cache_age_seconds) % 60
        if age_minutes > 0:
            age_str = f"data: {age_minutes}m {age_seconds}s old"
        else:
            age_str = f"data: {age_seconds}s old"
        age_y = timestamp_y + CHAR_HEIGHT * ls + 3 * ui
        age_width = get_text_width(age_str, scale=ls)
        draw_rect(img, timestamp_x - age_width - 2 * ui, age_y - 1 * ui,
                  timestamp_x + 2 * ui, age_y + CHAR_HEIGHT * ls + 1 * ui, WHITE)
        draw_text(img, timestamp_x, age_y, age_str, BLACK, anchor="right", scale=ls)

    # Bottom axis line (full width)
    draw_hline(img, 0, cfg.width, chart_bottom, BLACK)

    # Time markers (every 30 minutes)
    marker_time = start_time
    while marker_time <= end:
        x = time_to_x(marker_time, start_time, end, cfg)

        # Vertical grid line (light - draw every other pixel)
        for py in range(chart_top, chart_bottom):
            if py % 3 == 0:
                img.putpixel((x, py), BLACK)

        # Time label
        label = format_time_label(marker_time)
        draw_text(img, x, chart_bottom + 8 * ui, label, BLACK, anchor="center", scale=fs)

        marker_time += timedelta(minutes=30)

    # "Now" indicator (line only)
    now_x = time_to_x(now, start_time, end, cfg)
    draw_vline(img, now_x, chart_top - 5 * ui, chart_bottom, BLACK, dashed=True, dash=4 * ui)

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
            x1 = time_to_x(visible_dep, start_time, end, cfg)
            x2 = time_to_x(visible_arr, start_time, end, cfg)
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

            # Extend bars to the edge of the image when they overflow the window
            x1 = 0 if dep <= start_time else time_to_x(visible_dep, start_time, end, cfg)
            x2 = cfg.width if arr >= end else time_to_x(visible_arr, start_time, end, cfg)
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
                buffer_start_x = time_to_x(max(buffer_start_time, start_time), start_time, end, cfg)
                if buffer_start_x < block_x1:
                    draw_checkerboard(img, buffer_start_x, bar_top, block_x1, bar_bottom)

            if buffer_after > 0:
                last_arr = segment_positions[-1][3]  # arr time of last segment
                buffer_end_time = last_arr + timedelta(minutes=buffer_after)
                buffer_end_x = time_to_x(min(buffer_end_time, end), start_time, end, cfg)
                # If the bar extends to edge, start checkerboard from there
                if block_x2 >= cfg.width:
                    pass  # No room for buffer after
                elif buffer_end_x > block_x2:
                    draw_checkerboard(img, block_x2, bar_top, min(buffer_end_x, cfg.width), bar_bottom)

        if compact:
            # Compact mode: station+time labels before/after bar, train name inside
            if segment_positions:
                label_scale = ls
                label_h = CHAR_HEIGHT * label_scale
                label_bg_y = y_center - label_h // 2  # background centered on bar
                label_text_y = label_bg_y + 2 * ui  # text shifted down within box for visual centering
                bar_top = y_center - bar_height // 2
                bar_bottom = y_center + bar_height // 2
                label_pad = 4 * ui
                bg_pad = 2 * ui

                # Before first segment: "FROM DEP_TIME"
                first_pos = segment_positions[0]
                first_seg = first_pos[5]
                if first_pos[0] > 0:
                    from_station = first_seg["from"]["station_code"]
                    dep_time_str = format_time_label(first_pos[2])
                    before_label = f"{from_station} {dep_time_str}"
                    before_w = get_text_width(before_label, scale=label_scale)
                    bx = first_pos[0] - label_pad
                    draw_rect(img, bx - before_w - bg_pad, label_bg_y - bg_pad,
                              bx + bg_pad, label_bg_y + label_h + bg_pad, WHITE)
                    draw_text(img, bx, label_text_y, before_label, BLACK, anchor="right", scale=label_scale)

                # After last segment: "ARR_TIME TO"
                last_pos = segment_positions[-1]
                last_seg = last_pos[5]
                if last_pos[1] < cfg.width:
                    to_station = last_seg["to"]["station_code"]
                    arr_time_str = format_time_label(last_pos[3])
                    after_label = f"{arr_time_str} {to_station}"
                    after_w = get_text_width(after_label, scale=label_scale)
                    ax = last_pos[1] + label_pad
                    draw_rect(img, ax - bg_pad, label_bg_y - bg_pad,
                              ax + after_w + bg_pad, label_bg_y + label_h + bg_pad, WHITE)
                    draw_text(img, ax, label_text_y, after_label, BLACK, anchor="left", scale=label_scale)

                # Intermediate station labels in gaps between segments
                for pos_idx in range(len(segment_positions) - 1):
                    curr_pos = segment_positions[pos_idx]
                    next_pos = segment_positions[pos_idx + 1]
                    gap_center = (curr_pos[1] + next_pos[0]) // 2
                    station_code = curr_pos[5]["to"]["station_code"]
                    int_time_str = format_time_label(curr_pos[3])
                    int_label = f"{station_code} {int_time_str}"
                    int_w = get_text_width(int_label, scale=label_scale)
                    draw_rect(img, gap_center - int_w // 2 - bg_pad, label_bg_y - bg_pad,
                              gap_center + int_w // 2 + bg_pad, label_bg_y + label_h + bg_pad, WHITE)
                    draw_text(img, gap_center, label_text_y, int_label, BLACK, anchor="center", scale=label_scale)

                # Train name centered inside the bar
                route = train.get("route_name") or "Train"
                if route == "Northeast Regional":
                    route = "NE Regional"
                train_num = train.get("train_num", "")
                label = f"{route} {train_num}"
                label_width = get_text_width(label, scale=fs)
                center_x = (block_x1 + block_x2) // 2
                train_name_y = y_center - CHAR_HEIGHT * fs // 2 + 2 * ui  # +2 to compensate for font descender space
                train_padding = 8 * ui

                if center_x + label_width // 2 > cfg.width:
                    draw_text(img, block_x1 + train_padding, train_name_y, label, WHITE, anchor="left", scale=fs)
                elif center_x - label_width // 2 < 0:
                    draw_text(img, block_x2 - train_padding, train_name_y, label, WHITE, anchor="right", scale=fs)
                else:
                    draw_text(img, center_x, train_name_y, label, WHITE, anchor="center", scale=fs)
        else:
            # Normal mode: time labels above bars, station codes + train name inside
            time_y = y_center - bar_height // 2 - CHAR_HEIGHT * ls - 3 * ui

            time_labels = []

            for pos_idx, (x1, x2, dep, arr, seg_idx, seg) in enumerate(segment_positions):
                is_first = pos_idx == 0
                is_last = pos_idx == len(segment_positions) - 1

                if is_first:
                    label = format_time_label(dep)
                    label_width = get_text_width(label, scale=ls)
                    time_labels.append((x1, x1 + label_width, label))

                if not is_last:
                    next_x1 = segment_positions[pos_idx + 1][0]
                    gap_center = (x2 + next_x1) // 2
                    label = format_time_label(arr)
                    label_width = get_text_width(label, scale=ls)
                    time_labels.append((gap_center - label_width // 2, gap_center + label_width // 2, label))

                if is_last and arr <= end:
                    label = format_time_label(arr)
                    label_width = get_text_width(label, scale=ls)
                    time_labels.append((x2 - label_width, x2, label))

            min_gap = 4 * ui
            last_right = -1000
            for left, right, label in time_labels:
                if left > last_right + min_gap:
                    bg_pad = 1 * ui
                    draw_rect(img, left - bg_pad, time_y - bg_pad, right + bg_pad, time_y + CHAR_HEIGHT * ls + bg_pad, WHITE)
                    if left == time_labels[0][0] and time_labels[0][2] == label:
                        draw_text(img, left, time_y, label, BLACK, anchor="left", scale=ls)
                    else:
                        center = (left + right) // 2
                        draw_text(img, center, time_y, label, BLACK, anchor="center", scale=ls)
                    last_right = right

            bar_top = y_center - bar_height // 2
            bar_bottom = y_center + bar_height // 2
            text_padding = 2 * ui
            padding = 4 * ui
            station_y = bar_top + text_padding
            train_name_y = bar_bottom - CHAR_HEIGHT * fs - text_padding

            for pos_idx, (x1, x2, dep, arr, seg_idx, seg) in enumerate(segment_positions):
                bar_width = x2 - x1
                is_first = pos_idx == 0
                is_last = pos_idx == len(segment_positions) - 1

                from_station = seg["from"]["station_code"]
                to_station = seg["to"]["station_code"]

                min_width_for_station = get_text_width("XXX", scale=ls) + padding * 2
                if bar_width > min_width_for_station:
                    if is_first:
                        draw_text(img, x1 + padding, station_y, from_station, WHITE, anchor="left", scale=ls)
                    if is_last:
                        draw_text(img, x2 - padding, station_y, to_station, WHITE, anchor="right", scale=ls)

                if not is_last:
                    next_x1 = segment_positions[pos_idx + 1][0]
                    gap_center = (x2 + next_x1) // 2

                    code_width = get_text_width(to_station, scale=ls)
                    bg_padding = 2 * ui
                    bg_x1 = gap_center - code_width // 2 - bg_padding
                    bg_x2 = gap_center + code_width // 2 + bg_padding
                    bg_y1 = station_y - 1 * ui
                    bg_y2 = station_y + CHAR_HEIGHT * ls + 1 * ui
                    draw_rect(img, bg_x1, bg_y1, bg_x2, bg_y2, BLACK)

                    draw_text(img, gap_center, station_y, to_station, WHITE, anchor="center", scale=ls)

            if segment_positions:
                route = train.get("route_name") or "Train"
                if route == "Northeast Regional":
                    route = "NE Regional"
                train_num = train.get("train_num", "")
                label = f"{route} {train_num}"
                label_width = get_text_width(label, scale=fs)
                center_x = (block_x1 + block_x2) // 2
                train_padding = 8 * ui

                if center_x + label_width // 2 > cfg.width:
                    draw_text(img, block_x1 + train_padding, train_name_y, label, WHITE, anchor="left", scale=fs)
                elif center_x - label_width // 2 < 0:
                    draw_text(img, block_x2 - train_padding, train_name_y, label, WHITE, anchor="right", scale=fs)
                else:
                    draw_text(img, center_x, train_name_y, label, WHITE, anchor="center", scale=fs)

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
