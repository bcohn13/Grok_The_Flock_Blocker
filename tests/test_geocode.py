from flock_blocker.tools.geocode import _photon_label, geocode_place, search_places


def test_photon_label_includes_city():
    label = _photon_label({"name": "Ferry Building", "city": "San Francisco", "state": "California"}, "Ferry")
    assert "Ferry Building" in label
    assert "San Francisco" in label


def test_search_places_uses_photon(monkeypatch):
    monkeypatch.setattr(
        "flock_blocker.tools.geocode._search_photon",
        lambda query, lat, lon, limit: [
            {"lat": 37.7955, "lon": -122.3937, "label": "Ferry Building, San Francisco"}
        ],
    )
    hits = search_places("Ferry Building", lat=37.78, lon=-122.4)
    assert hits[0]["lat"] == 37.7955
    assert geocode_place("Ferry Building")["lon"] == -122.3937


def test_search_places_falls_back_to_nominatim(monkeypatch):
    monkeypatch.setattr("flock_blocker.tools.geocode._search_photon", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("down")))
    monkeypatch.setattr(
        "flock_blocker.tools.geocode._search_nominatim",
        lambda query, lat, lon, limit: [{"lat": 37.7793, "lon": -122.4193, "label": "Civic Center"}],
    )
    hits = search_places("Civic Center")
    assert hits[0]["label"] == "Civic Center"
