import re
from datetime import datetime

import requests

USER_AGENT = "openBrick/0.1 (+https://github.com/Rmailley/openbrick)"
COORDINATES = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")

PLAN_QUERY = """
query Plan($origin: PlanLabeledLocationInput!, $destination: PlanLabeledLocationInput!) {
  planConnection(origin: $origin, destination: $destination, first: 1) {
    edges { node {
      start end duration
      legs {
        mode transitLeg duration headsign
        start { scheduledTime estimated { time } }
        end { scheduledTime estimated { time } }
        to { name }
        route { shortName longName }
      }
    } }
  }
}
"""

MODE_NAMES = {"BUS": "Bus", "SUBWAY": "Metro", "RAIL": "Train", "TRAM": "Streetcar", "FERRY": "Ferry"}


class PlaceNotFound(Exception):
    pass


class Geocoder:
    def __init__(self, url: str, viewbox: str | None = None, session: requests.Session | None = None):
        self.url = url.rstrip("/")
        self.viewbox = viewbox
        self.session = session or requests.Session()

    def locate(self, query: str) -> tuple[float, float]:
        if m := COORDINATES.match(query):
            return float(m[1]), float(m[2])
        params = {"q": query, "format": "jsonv2", "limit": 1}
        if self.viewbox:
            params |= {"viewbox": self.viewbox, "bounded": 1}
        r = self.session.get(f"{self.url}/search", params=params, headers={"User-Agent": USER_AGENT}, timeout=15)
        r.raise_for_status()
        results = r.json()
        if not results:
            raise PlaceNotFound(query)
        return float(results[0]["lat"]), float(results[0]["lon"])


class TripPlanner:
    def __init__(self, url: str, session: requests.Session | None = None):
        self.url = url.rstrip("/")
        self.session = session or requests.Session()

    def plan(self, origin: tuple[str, tuple[float, float]], destination: tuple[str, tuple[float, float]]) -> dict | None:
        def place(label, coords):
            return {"label": label, "location": {"coordinate": {"latitude": coords[0], "longitude": coords[1]}}}

        r = self.session.post(
            f"{self.url}/otp/gtfs/v1",
            json={"query": PLAN_QUERY, "variables": {"origin": place(*origin), "destination": place(*destination)}},
            timeout=30,
        )
        r.raise_for_status()
        body = r.json()
        if body.get("errors"):
            raise requests.RequestException(body["errors"][0].get("message", "trip planner error"))
        edges = body["data"]["planConnection"]["edges"]
        return edges[0]["node"] if edges else None


def _clock(dt: datetime) -> str:
    return f"{dt.hour % 12 or 12}:{dt.minute:02d}{'am' if dt.hour < 12 else 'pm'}"


def _leg_time(t: dict) -> datetime:
    return datetime.fromisoformat((t.get("estimated") or {}).get("time") or t["scheduledTime"])


def format_itinerary(it: dict) -> str:
    start, end = datetime.fromisoformat(it["start"]), datetime.fromisoformat(it["end"])
    lines = [f"Leave {_clock(start)}, arrive {_clock(end)} ({round(it['duration'] / 60)} min)"]
    for leg in it["legs"]:
        if leg["transitLeg"]:
            route = leg.get("route") or {}
            parts = [_clock(_leg_time(leg["start"])), MODE_NAMES.get(leg["mode"], leg["mode"].title())]
            if name := route.get("shortName") or route.get("longName"):
                parts.append(name)
            if leg.get("headsign"):
                parts.append(f"toward {leg['headsign']}")
            lines.append(f"{' '.join(parts)}. Off at {leg['to']['name']} {_clock(_leg_time(leg['end']))}")
        else:
            lines.append(f"Walk {max(1, round(leg['duration'] / 60))} min to {leg['to']['name']}")
    return "\n".join(lines)


class Directions:
    def __init__(self, geocoder: Geocoder, planner: TripPlanner, places: dict[str, str]):
        self.geocoder = geocoder
        self.planner = planner
        self.places = places

    def _resolve(self, name: str) -> tuple[str, tuple[float, float]]:
        name = name.strip()
        return name, self.geocoder.locate(self.places.get(name.lower(), name))

    def route(self, origin: str, destination: str) -> str:
        itinerary = self.planner.plan(self._resolve(origin), self._resolve(destination))
        if itinerary is None:
            return f"No route from {origin} to {destination} right now."
        return format_itinerary(itinerary)
