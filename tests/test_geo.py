from flock_blocker.geo import bbox_from_point, compass_bearing, haversine_meters


def test_haversine_zero():
    assert haversine_meters(37.77, -122.42, 37.77, -122.42) == 0


def test_haversine_known_distance():
    # Roughly 1km east at this latitude
    distance = haversine_meters(37.7749, -122.4194, 37.7749, -122.4080)
    assert 900 < distance < 1100


def test_bearing_east():
    assert compass_bearing(0, 0, 0, 1) == "E"


def test_bbox_contains_point():
    south, west, north, east = bbox_from_point(37.77, -122.42, 500)
    assert south < 37.77 < north
    assert west < -122.42 < east
