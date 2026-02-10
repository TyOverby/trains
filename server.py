#!/usr/bin/env python3
"""Web server for train schedule visualization."""

import io
import time
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from main import find_connecting_trains
from visualize import create_image

# Cache for train data: {route_key: (timestamp, data)}
train_cache: dict[str, tuple[float, dict]] = {}
CACHE_TTL = 5 * 60  # 5 minutes in seconds


def get_trains(stations: list[str]) -> dict:
    """Get train data, using cache if available and fresh."""
    cache_key = "_".join(stations)
    now = time.time()

    if cache_key in train_cache:
        cached_time, cached_data = train_cache[cache_key]
        if now - cached_time < CACHE_TTL:
            print(f"Cache hit for {cache_key}")
            return cached_data

    print(f"Cache miss for {cache_key}, fetching...")
    trains = find_connecting_trains(stations)
    data = {
        "stations": stations,
        "trains": trains,
    }
    train_cache[cache_key] = (now, data)
    return data


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
        now = datetime.now().astimezone()
        img = create_image(data["trains"], data["stations"], now,
                          buffer_before=buffer_before, buffer_after=buffer_after)

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
