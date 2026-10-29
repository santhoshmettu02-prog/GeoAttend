import math

EARTH_RADIUS_M = 6_371_000


def haversine_m(lat1, lon1, lat2, lon2):
    """Great-circle distance in meters between two latitude/longitude pairs."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def valid_coordinates(lat, lon):
    return -90 <= float(lat) <= 90 and -180 <= float(lon) <= 180
