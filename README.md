# amtrak-status

A general-purpose server for hosting black-and-white images for e-ink
displays. It started as an Amtrak schedule renderer (query real-time train
schedules between stations and render them as 1-bit PNGs) and is growing into
a home for other e-ink image endpoints.

Endpoints:

- `/trains` -- real-time Amtrak schedules, rendered at 800x480.
- `/workdays` -- a square per workday between Aug 10 2026 and Dec 9 2029,
  filled in up to today, rendered at 1872x1404.

![Example output showing trains from NYP to NWK to PHL](output.png)

## Quick start

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync                            # install dependencies
uv run main.py NYP NWK PHL         # fetch trains, writes trains_NYP_NWK_PHL.json
uv run visualize.py trains_NYP_NWK_PHL.json   # render to PNG
uv run server.py                   # start web server on :8080
```

## Project structure

```
main.py          Amtrak API client and train-finding logic
visualize.py     1-bit PNG renderer with bitmap font engine
workdays.py      1-bit PNG renderer for the workday-grid endpoint
server.py        HTTP server that combines the above
departure.json   Bitmap font data (pixel definitions for each character)
deploy.sh        Deploys to production via SSH + systemd
```

## How it works

### Data pipeline

1. **Fetch** -- `main.py` hits the [Amtraker API](https://api-v3.amtraker.com/v3)
   to get every train serving the requested stations.
2. **Filter** -- For each train, check whether it stops at the requested stations
   in the correct order. Build "segments" for each consecutive station pair.
3. **Visualize** -- `visualize.py` takes the JSON output and renders a timeline
   where each train is a horizontal bar across a 3-hour window. Station codes,
   departure/arrival times, and route names are drawn with a custom bitmap font.

### Key data model

Trains are represented as a list of **segments** between consecutive requested
stations:

```json
{
  "train_id": "89-1",
  "train_num": "89",
  "route_name": "Palmetto",
  "status": "Active",
  "segments": [
    {
      "from": { "station_code": "NYP", "station_name": "New York Penn",
                "scheduled": "2026-02-01T06:02:00-05:00",
                "actual": "2026-02-01T06:02:00-05:00" },
      "to":   { "station_code": "NWK", "station_name": "Newark Penn",
                "scheduled": "2026-02-01T06:16:00-05:00",
                "actual": "2026-02-01T06:17:00-05:00" }
    }
  ]
}
```

The JSON files written by `main.py` wrap this in `{ "stations": [...], "trains": [...] }`.

## Modules in detail

### `main.py`

CLI entry point and API client. Core functions:

| Function | Purpose |
|---|---|
| `fetch_station(code)` | GET `/stations/{code}` -- returns station info with train IDs |
| `fetch_train(id)` | GET `/trains/{id}` -- returns full route with all stops |
| `find_connecting_trains(stations)` | Orchestrates the above, returns filtered train list |
| `build_json_output(trains, stations)` | Wraps results for JSON serialization |

`find_connecting_trains` is also imported by `server.py` -- it's the main
programmatic entry point for fetching data.

### `visualize.py`

Renders train data to a 1-bit PIL `Image`. Resolution-dependent layout lives
in a `RenderConfig` dataclass, with two instances:

```python
BASE_CONFIG   # native 800x480  (font_scale=2, label_scale=1, ui=1)
HIRES_CONFIG  # native 1872x1404 -- a clean 2x of the base design
```

`HOURS_TO_SHOW = 3` (the time window) is resolution-independent. All layout
math is expressed in terms of the config: `width`/`height`, the four margins,
`font_scale`/`label_scale` (integer font scales for large/small text), and
`ui` (a multiplier for fixed pixel paddings). Because the bitmap font is always
drawn at an integer scale, text stays crisp at any resolution -- rendering
natively at 1872x1404 avoids the fractional-scaling artifacts an upscale would
introduce.

The bitmap font is loaded from `departure.json` at module import time.
Missing characters (uppercase, `:`, `-`, `>`, `#`, space) are synthesized
in `load_font()`.

`create_image(trains, stations, now, buffer_before=0, buffer_after=0,
cache_age_seconds=None, cfg=BASE_CONFIG)` is the main entry point, also
imported by `server.py`. The optional buffer parameters add checkerboard
patterns before/after each train bar; `cfg` selects the resolution.

### `server.py`

Minimal HTTP server (stdlib `BaseHTTPRequestHandler`) on port 8080. Two URL
styles:

```
GET /trains?stations=NYP,NWK,PHL
GET /trains/NYP/NWK/PHL
```

Optional query params: `buffer_before` and `buffer_after` (minutes), and
`hires` (off by default). When `hires` is truthy (`1`/`true`/`yes`/`on`), the
schedule is rendered natively at 1872x1404 (`visualize.HIRES_CONFIG`) instead
of the default 800x480 (`visualize.BASE_CONFIG`). The bitmap font is always
drawn at an integer scale, so hi-res text stays crisp -- the high-res config is
a clean 2x of the base design.

There is also `GET /workdays`, which serves the workday grid (see
`workdays.py`) and takes no query params.

Train data is cached for 5 minutes (`CACHE_TTL`); the PNG is always regenerated
with the current time so the "now" line stays accurate.

## Deployment

`deploy.sh` pushes to a remote server over SSH:

```
ssh root@ares.io
  -> git pull (as trains user)
  -> uv sync
  -> copy trains.service to systemd
  -> systemctl restart trains
```

The service runs as the `trains` user under systemd.

## Dependencies

| Package | Used for |
|---|---|
| `httpx` | HTTP client for Amtrak API calls |
| `pillow` | Image creation and pixel manipulation |
| `cairosvg` | SVG-to-PNG conversion (currently unused, may be removed) |
| `svgwrite` | SVG generation (currently unused, may be removed) |
