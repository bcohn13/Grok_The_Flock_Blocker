from flock_blocker.geo import bbox_from_point, compass_bearing, densify_path, destination_point, haversine_meters


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


def test_destination_point_north():
    lat, lon = destination_point(0, 0, 1000, 0)
    assert lat > 0
    assert abs(lon) < 0.0001
    assert 990 < haversine_meters(0, 0, lat, lon) < 1010


def test_densify_keeps_steps_short():
    points = densify_path([(37.780882, -122.399749), (37.782633, -122.401933)], 20)
    assert len(points) > 2
    for start, end in zip(points, points[1:]):
        assert haversine_meters(start[0], start[1], end[0], end[1]) <= 22
