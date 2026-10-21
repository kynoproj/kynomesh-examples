"""Worker tools: deterministic stubs over small built-in data.

Plain functions: ADK builds each tool's schema from the signature and docstring.
Each returns a dict, with `status` telling the model whether the call worked.
"""

from __future__ import annotations

_FLIGHTS: dict[str, tuple[str, ...]] = {
    "tokyo": ("NH7 08:50 -> 13:10+1, $1,120", "UA837 11:40 -> 15:55+1, $980"),
    "paris": ("AF83 17:05 -> 12:55+1, $870", "UA990 16:30 -> 12:20+1, $810"),
    "lisbon": ("TP238 15:20 -> 10:05+1, $740",),
}
_HOTELS: dict[str, tuple[str, ...]] = {
    "tokyo": ("Shinjuku Granbell, $140/night", "Park Hyatt Tokyo, $520/night"),
    "paris": ("Hotel du Louvre, $310/night", "Ibis Paris Bastille, $120/night"),
    "lisbon": ("Memmo Alfama, $210/night",),
}
_FORECASTS: dict[str, str] = {
    "tokyo": "Sat: sunny, 22C. Sun: light rain, 19C.",
    "paris": "Sat: cloudy, 16C. Sun: sunny, 18C.",
    "lisbon": "Sat: sunny, 24C. Sun: sunny, 25C.",
}


def flights_report(origin: str, destination: str) -> str:
    options = _FLIGHTS.get(destination.strip().lower())
    if not options:
        return f"No flights found to {destination!r}."
    return f"Flights {origin} -> {destination}:\n" + "\n".join(options)


def hotels_report(city: str) -> str:
    options = _HOTELS.get(city.strip().lower())
    if not options:
        return f"No hotels found in {city!r}."
    return f"Hotels in {city}:\n" + "\n".join(options)


def forecast_report(city: str) -> str:
    return _FORECASTS.get(city.strip().lower()) or f"No forecast available for {city!r}."


def ok(text: str) -> dict[str, str]:
    return {"status": "success", "result": text}


def failed(text: str) -> dict[str, str]:
    return {"status": "error", "error": text}


def search_flights(origin: str, destination: str) -> dict[str, str]:
    """Search flights from an origin city or airport to a destination city.

    Args:
        origin: The departure city or airport code.
        destination: The arrival city.
    """
    return ok(flights_report(origin, destination))


def search_hotels(city: str) -> dict[str, str]:
    """Search hotels in a city.

    Args:
        city: The city to search in.
    """
    return ok(hotels_report(city))


def get_forecast(city: str) -> dict[str, str]:
    """Get the weekend weather forecast for a city.

    Args:
        city: The city to forecast.
    """
    return ok(forecast_report(city))

_AMENITIES: dict[str, tuple[str, ...]] = {
    "Shinjuku Granbell": ("free wifi", "24-hour front desk", "breakfast not included ($15 add-on)"),
    "Park Hyatt Tokyo": ("free wifi", "indoor pool", "spa", "breakfast included"),
    "Hotel du Louvre": ("free wifi", "restaurant", "breakfast not included ($25 add-on)"),
    "Ibis Paris Bastille": ("free wifi", "24-hour bar", "breakfast not included ($12 add-on)"),
    "Memmo Alfama": ("free wifi", "rooftop pool", "breakfast included"),
}


def amenities_report(hotel: str) -> str:
    needle = hotel.strip().lower()
    if needle:
        for name, items in _AMENITIES.items():
            if name.lower() in needle or needle in name.lower():
                return f"{name}: " + ", ".join(items)
    return f"No amenity information for {hotel!r}."


def hotel_amenities(hotel: str) -> dict[str, str]:
    """List a hotel's amenities, such as breakfast, wifi and pool.

    Args:
        hotel: The hotel's name, for example "Shinjuku Granbell".
    """
    return ok(amenities_report(hotel))
