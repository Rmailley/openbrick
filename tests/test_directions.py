import pytest
import requests

from openbrick.directions import Directions, Geocoder, PlaceNotFound, TripPlanner, format_itinerary


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self.body


class FakeSession:
    def __init__(self, body):
        self.body = body
        self.calls = []

    def get(self, url, **kw):
        self.calls.append((url, kw))
        return FakeResponse(self.body)

    post = get


ITINERARY = {
    "start": "2026-11-19T14:10:00-05:00",
    "end": "2026-11-19T14:41:00-05:00",
    "duration": 1860,
    "legs": [
        {"mode": "WALK", "transitLeg": False, "duration": 290, "to": {"name": "Dupont Circle"},
         "start": {"scheduledTime": "2026-11-19T14:10:00-05:00"}, "end": {"scheduledTime": "2026-11-19T14:15:00-05:00"}},
        {"mode": "SUBWAY", "transitLeg": True, "duration": 600, "headsign": "Glenmont",
         "route": {"shortName": "RED", "longName": "Red Line"}, "to": {"name": "Union Station"},
         "start": {"scheduledTime": "2026-11-19T14:17:00-05:00", "estimated": {"time": "2026-11-19T14:19:00-05:00"}},
         "end": {"scheduledTime": "2026-11-19T14:29:00-05:00", "estimated": None}},
        {"mode": "BUS", "transitLeg": True, "duration": 480, "headsign": None,
         "route": {"shortName": "D6", "longName": None}, "to": {"name": "Benning Rd & 21st St NE"},
         "start": {"scheduledTime": "2026-11-19T14:31:00-05:00"}, "end": {"scheduledTime": "2026-11-19T14:39:00-05:00"}},
        {"mode": "WALK", "transitLeg": False, "duration": 20, "to": {"name": "work"},
         "start": {"scheduledTime": "2026-11-19T14:39:00-05:00"}, "end": {"scheduledTime": "2026-11-19T14:41:00-05:00"}},
    ],
}


def test_format_itinerary_uses_realtime_and_keeps_it_short():
    assert format_itinerary(ITINERARY) == (
        "Leave 2:10pm, arrive 2:41pm (31 min)\n"
        "Walk 5 min to Dupont Circle\n"
        "2:19pm Metro RED toward Glenmont. Off at Union Station 2:29pm\n"
        "2:31pm Bus D6. Off at Benning Rd & 21st St NE 2:39pm\n"
        "Walk 1 min to work"
    )


def test_geocoder_passes_coordinates_through():
    session = FakeSession([])
    assert Geocoder("https://geo", session=session).locate(" 38.9, -77.03 ") == (38.9, -77.03)
    assert session.calls == []


def test_geocoder_searches_inside_viewbox():
    session = FakeSession([{"lat": "38.8977", "lon": "-77.0365"}])
    geo = Geocoder("https://geo/", viewbox="-77.6,39.2,-76.6,38.6", session=session)
    assert geo.locate("white house") == (38.8977, -77.0365)
    url, kw = session.calls[0]
    assert url == "https://geo/search"
    assert kw["params"] == {"q": "white house", "format": "jsonv2", "limit": 1,
                            "viewbox": "-77.6,39.2,-76.6,38.6", "bounded": 1}
    assert kw["headers"]["User-Agent"].startswith("openBrick/")


def test_geocoder_not_found():
    with pytest.raises(PlaceNotFound, match="atlantis"):
        Geocoder("https://geo", session=FakeSession([])).locate("atlantis")


def test_trip_planner_sends_labeled_coordinates():
    session = FakeSession({"data": {"planConnection": {"edges": [{"node": ITINERARY}]}}})
    planner = TripPlanner("http://otp:8080", session=session)
    assert planner.plan(("home", (38.9, -77.0)), ("work", (38.8, -76.9))) == ITINERARY
    url, kw = session.calls[0]
    assert url == "http://otp:8080/otp/gtfs/v1"
    assert kw["json"]["variables"]["origin"] == {
        "label": "home", "location": {"coordinate": {"latitude": 38.9, "longitude": -77.0}}
    }


def test_trip_planner_no_route_and_errors():
    empty = FakeSession({"data": {"planConnection": {"edges": []}}})
    assert TripPlanner("http://otp", session=empty).plan(("a", (0, 0)), ("b", (1, 1))) is None
    broken = FakeSession({"errors": [{"message": "graph not loaded"}]})
    with pytest.raises(requests.RequestException, match="graph not loaded"):
        TripPlanner("http://otp", session=broken).plan(("a", (0, 0)), ("b", (1, 1)))


class FakeGeocoder:
    def __init__(self):
        self.queries = []

    def locate(self, query):
        self.queries.append(query)
        return (1.0, 2.0)


class FakePlanner:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def plan(self, origin, destination):
        self.calls.append((origin, destination))
        return self.result


def test_directions_uses_saved_places_and_labels():
    geo, planner = FakeGeocoder(), FakePlanner(ITINERARY)
    d = Directions(geo, planner, {"home": "1600 Pennsylvania Ave NW"})
    assert d.route("Home", "Union Station").startswith("Leave 2:10pm")
    assert geo.queries == ["1600 Pennsylvania Ave NW", "Union Station"]
    assert planner.calls == [(("Home", (1.0, 2.0)), ("Union Station", (1.0, 2.0)))]


def test_directions_no_route():
    d = Directions(FakeGeocoder(), FakePlanner(None), {})
    assert d.route("a", "b") == "No route from a to b right now."
