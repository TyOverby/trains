#!/usr/bin/env python3
"""Amtrak train status utility - find trains connecting multiple stations."""

import json
import sys
import httpx

API_BASE = "https://api-v3.amtraker.com/v3"


def fetch_station(station_code: str) -> dict | None:
    """Fetch station info including list of trains serving it."""
    url = f"{API_BASE}/stations/{station_code}"
    response = httpx.get(url)
    if response.status_code != 200:
        return None
    data = response.json()
    return data.get(station_code)


def fetch_train(train_id: str) -> dict | None:
    """Fetch train details including all station stops."""
    url = f"{API_BASE}/trains/{train_id}"
    response = httpx.get(url)
    if response.status_code != 200:
        return None
    data = response.json()
    # The response is keyed by train number, and contains an array
    # We need to find our specific train by trainID
    for train_num, trains in data.items():
        for train in trains:
            if train.get("trainID") == train_id:
                return train
    return None


def find_connecting_trains(stations: list[str]) -> list[dict]:
    """Find all trains that pass through at least two consecutive stations in order."""
    if len(stations) < 2:
        return []

    # Collect train IDs from ALL requested stations to catch partial routes
    all_train_ids = set()
    for station in stations:
        station_info = fetch_station(station)
        if station_info:
            all_train_ids.update(station_info.get("trains", []))

    if not all_train_ids:
        print(f"Error: Could not fetch station info for any station")
        return []

    connecting_trains = []

    for train_id in all_train_ids:
        train = fetch_train(train_id)
        if not train:
            continue

        train_stations = train.get("stations", [])
        station_codes = [s.get("code") for s in train_stations]

        # Find which requested stations are on this route and their indices
        station_indices = {}
        for station in stations:
            if station in station_codes:
                station_indices[station] = station_codes.index(station)

        # Build segments for consecutive station pairs that this train covers
        segments = []
        for i in range(len(stations) - 1):
            from_station = stations[i]
            to_station = stations[i + 1]

            # Both stations must be on this train's route
            if from_station not in station_indices or to_station not in station_indices:
                continue

            from_idx = station_indices[from_station]
            to_idx = station_indices[to_station]

            # Stations must be in the correct order on this train
            if from_idx >= to_idx:
                continue

            from_stop = train_stations[from_idx]
            to_stop = train_stations[to_idx]
            segments.append({
                "from": {
                    "station_code": from_station,
                    "station_name": from_stop.get("name"),
                    "scheduled": from_stop.get("schDep"),
                    "actual": from_stop.get("dep"),
                },
                "to": {
                    "station_code": to_station,
                    "station_name": to_stop.get("name"),
                    "scheduled": to_stop.get("schArr"),
                    "actual": to_stop.get("arr"),
                },
            })

        # Only include trains that cover at least one segment
        if segments:
            connecting_trains.append({
                "train_id": train_id,
                "train_num": train.get("trainNum"),
                "route_name": train.get("routeName"),
                "status": train.get("trainState"),
                "segments": segments,
            })

    return connecting_trains


def format_time(time_str: str | None) -> str:
    """Format a time string for display."""
    if not time_str:
        return "N/A"
    if "T" in time_str:
        time_part = time_str.split("T")[1]
        if "-" in time_part:
            time_part = time_part.rsplit("-", 1)[0]
        elif "+" in time_part:
            time_part = time_part.rsplit("+", 1)[0]
        return time_part[:5]
    return time_str


def build_json_output(trains: list[dict], stations: list[str]) -> dict:
    """Build a clean JSON structure for output."""
    return {
        "stations": stations,
        "trains": trains,
    }


def save_json(data: dict, stations: list[str]):
    """Save the train data to a JSON file."""
    filename = f"trains_{'_'.join(stations)}.json"
    with open(filename, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Saved results to {filename}")


def display_trains(trains: list[dict], stations: list[str]):
    """Display the list of connecting trains."""
    if not trains:
        print(f"\nNo trains found connecting {' -> '.join(stations)}")
        return

    print(f"\nTrains: {' -> '.join(stations)}")
    print("-" * 70)

    # Sort by first segment's scheduled departure time
    trains.sort(key=lambda t: t["segments"][0]["from"].get("scheduled", "") or "")

    for train in trains:
        route = train["route_name"] or "Unknown"
        train_num = train["train_num"]
        status = train.get("status", "Unknown")

        print(f"{route} #{train_num} ({status})")
        for seg in train["segments"]:
            dep = format_time(seg["from"].get("actual") or seg["from"].get("scheduled"))
            arr = format_time(seg["to"].get("actual") or seg["to"].get("scheduled"))
            print(f"  {seg['from']['station_code']} {dep} -> {seg['to']['station_code']} {arr}")
        print()


def main():
    if len(sys.argv) < 3:
        print("Usage: uv run main.py <station1> <station2> [station3] ...")
        print("Example: uv run main.py NYP NWK PHL")
        sys.exit(1)

    stations = [s.upper() for s in sys.argv[1:]]

    print(f"Searching for trains: {' -> '.join(stations)}...")

    trains = find_connecting_trains(stations)
    display_trains(trains, stations)

    # Save JSON output
    json_data = build_json_output(trains, stations)
    save_json(json_data, stations)


if __name__ == "__main__":
    main()
