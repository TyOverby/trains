#!/usr/bin/env python3
"""Web server for train schedule visualization."""

import io
import threading
import time
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from zoneinfo import ZoneInfo

from main import find_connecting_trains
from visualize import create_image

# Cache for train data: {route_key: (timestamp, data)}
train_cache: dict[str, tuple[float, dict]] = {}
# All known routes that the background thread should keep fresh
registered_routes: dict[str, list[str]] = {}
cache_lock = threading.Lock()
REFRESH_INTERVAL = 5 * 60  # refresh every 5 minutes


def refresh_route(cache_key: str, stations: list[str]) -> dict:
    """Fetch fresh data for a route and update the cache."""
    print(f"Refreshing data for {cache_key}...")
    trains = find_connecting_trains(stations)
    data = {
        "stations": stations,
        "trains": trains,
    }
    with cache_lock:
        train_cache[cache_key] = (time.time(), data)
    return data


def background_refresh():
    """Background thread that periodically refreshes all registered routes."""
    while True:
        time.sleep(REFRESH_INTERVAL)
        with cache_lock:
            routes = dict(registered_routes)
        for cache_key, stations in routes.items():
            try:
                refresh_route(cache_key, stations)
            except Exception as e:
                print(f"Background refresh failed for {cache_key}: {e}")


def max_cache_age() -> float:
    """Return the age in seconds of the most stale item in the cache, or 0 if empty."""
    with cache_lock:
        if not train_cache:
            return 0.0
        now = time.time()
        return max(now - ts for ts, _ in train_cache.values())


def get_trains(stations: list[str]) -> dict:
    """Get train data. Always returns cached data if available; fetches synchronously on first request."""
    cache_key = "_".join(stations)

    with cache_lock:
        cached = train_cache.get(cache_key)
        registered_routes[cache_key] = stations

    if cached is not None:
        cached_time, cached_data = cached
        age = time.time() - cached_time
        print(f"Cache hit for {cache_key} (age: {age:.0f}s)")
        return cached_data

    # Cold start: no data yet, fetch synchronously
    print(f"Cold start for {cache_key}, fetching...")
    return refresh_route(cache_key, stations)


class TrainHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        # Expect /trains?stations=NYP,NWK,PHL or /trains/NYP/NWK/PHL
        if parsed.path == "/trains":
            # Query parameter style: /trains?stations=NYP,NWK,PHL
            stations_param = params.get("stations", [""])[0]
            if not stations_param:
                self.send_error(400, "Missing 'stations' parameter")
                return
            stations = [s.strip().upper() for s in stations_param.split(",")]
        elif parsed.path.startswith("/trains/"):
            # Path style: /trains/NYP/NWK/PHL
            path_parts = parsed.path.split("/")[2:]  # Skip empty and "trains"
            stations = [s.upper() for s in path_parts if s]
        else:
            self.send_error(404, "Not found. Use /trains?stations=NYP,NWK,PHL or /trains/NYP/NWK/PHL")
            return

        if len(stations) < 2:
            self.send_error(400, "Need at least 2 stations")
            return

        # Parse buffer parameters (in minutes)
        try:
            buffer_before = int(params.get("buffer_before", ["0"])[0])
            buffer_after = int(params.get("buffer_after", ["0"])[0])
        except ValueError:
            self.send_error(400, "buffer_before and buffer_after must be integers")
            return

        # Get train data (cached)
        data = get_trains(stations)

        if not data["trains"]:
            self.send_error(404, f"No trains found for route: {' -> '.join(stations)}")
            return

        # Generate PNG (always fresh)
        now = datetime.now(ZoneInfo("America/New_York"))
        img = create_image(data["trains"], data["stations"], now,
                          buffer_before=buffer_before, buffer_after=buffer_after,
                          cache_age_seconds=max_cache_age())

        # Convert to PNG bytes
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_data = buf.getvalue()

        # Send response
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", len(png_data))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(png_data)

    def log_message(self, format, *args):
        print(f"{self.address_string()} - {format % args}")


def main():
    port = 8080

    # Start background refresh thread
    refresh_thread = threading.Thread(target=background_refresh, daemon=True)
    refresh_thread.start()
    print(f"Background refresh thread started (interval: {REFRESH_INTERVAL}s)")

    server = HTTPServer(("", port), TrainHandler)
    print(f"Server running on http://localhost:{port}")
    print(f"Example: http://localhost:{port}/trains?stations=NYP,NWK,PHL")
    print(f"     or: http://localhost:{port}/trains/NYP/NWK/PHL")
    print(f"Buffer:  http://localhost:{port}/trains/NYP/NWK/PHL?buffer_before=15&buffer_after=20")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
