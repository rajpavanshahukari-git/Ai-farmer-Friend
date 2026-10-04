"""Weather layer (Open-Meteo: free, no key). Turns raw forecast into farming risk signals."""
import time

import httpx

WEATHER_CODES = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast", 45: "fog", 48: "fog",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle", 61: "light rain", 63: "moderate rain",
    65: "heavy rain", 66: "freezing rain", 67: "freezing rain", 71: "snow", 73: "snow", 75: "snow",
    80: "rain showers", 81: "heavy rain showers", 82: "violent rain showers",
    95: "thunderstorm", 96: "thunderstorm with hail", 99: "thunderstorm with hail",
}

_cache: dict[tuple, tuple[float, dict]] = {}
CACHE_SECONDS = 15 * 60


async def geocode(place: str) -> tuple[float, float] | None:
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": place, "count": 1, "country": "IN"},
        )
    results = r.json().get("results") or []
    return (results[0]["latitude"], results[0]["longitude"]) if results else None


async def get_weather(lat: float, lon: float) -> dict:
    key = (round(lat, 2), round(lon, 2))
    if key in _cache and time.time() - _cache[key][0] < CACHE_SECONDS:
        return _cache[key][1]

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code,precipitation",
                "hourly": "precipitation_probability",
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,wind_speed_10m_max,weather_code,et0_fao_evapotranspiration",
                "forecast_days": 4,
                "timezone": "auto",
            },
        )
        r.raise_for_status()
    d = r.json()
    c, dl = d["current"], d["daily"]
    days = [
        {
            "date": dl["time"][i],
            "max_c": dl["temperature_2m_max"][i],
            "min_c": dl["temperature_2m_min"][i],
            "rain_mm": dl["precipitation_sum"][i],
            "rain_chance": dl["precipitation_probability_max"][i] or 0,
            "wind_max_kmh": dl["wind_speed_10m_max"][i],
            "et0_mm": dl["et0_fao_evapotranspiration"][i],
            "sky": WEATHER_CODES.get(dl["weather_code"][i], "mixed"),
            "code": dl["weather_code"][i],
        }
        for i in range(len(dl["time"]))
    ]
    # rain chance over the next 6 hours matters most for spraying
    hourly_rain = d["hourly"]["precipitation_probability"]
    now_idx = next((i for i, t in enumerate(d["hourly"]["time"]) if t >= c["time"]), 0)
    rain_next_6h = max(hourly_rain[now_idx : now_idx + 6] or [0])

    current = {
        "temp_c": c["temperature_2m"],
        "humidity": c["relative_humidity_2m"],
        "wind_kmh": c["wind_speed_10m"],
        "precip_mm": c["precipitation"],
        "sky": WEATHER_CODES.get(c["weather_code"], "mixed"),
        "code": c["weather_code"],
        "rain_next_6h": rain_next_6h,
    }
    result = {"current": current, "days": days, "risks": assess_risks(current, days)}
    _cache[key] = (time.time(), result)
    return result


def assess_risks(current: dict, days: list[dict]) -> dict:
    today, tomorrow = days[0], days[1] if len(days) > 1 else days[0]

    # codes let the frontend show the reasons in the farmer's language
    spray_reasons, spray_codes = [], []
    if current["rain_next_6h"] >= 40:
        spray_reasons.append(f"rain chance {current['rain_next_6h']}% in the next 6 hours")
        spray_codes.append({"code": "rain", "value": current["rain_next_6h"]})
    if current["wind_kmh"] > 15:
        spray_reasons.append(f"wind {current['wind_kmh']:.0f} km/h (spray drifts above ~15 km/h)")
        spray_codes.append({"code": "wind", "value": round(current["wind_kmh"])})
    if current["temp_c"] >= 35:
        spray_reasons.append(f"temperature {current['temp_c']:.0f}°C (spray only early morning/evening)")
        spray_codes.append({"code": "heat", "value": round(current["temp_c"])})

    heavy_rain = max(today["rain_mm"], tomorrow["rain_mm"]) >= 50 or "heavy" in tomorrow["sky"] or "violent" in tomorrow["sky"]
    heat = max(d["max_c"] for d in days[:3]) >= 38
    rain_coming = any(d["rain_chance"] >= 60 for d in days[:2])
    storm = any("thunderstorm" in d["sky"] for d in days[:2]) or any(d["wind_max_kmh"] >= 40 for d in days[:2])

    if rain_coming:
        irrigation_code = "rain_expected"
        irrigation = "Rain is likely within 2 days - you can probably skip or reduce irrigation. Check soil moisture first."
    elif today["et0_mm"] and today["et0_mm"] >= 5:
        irrigation_code = "high_loss"
        irrigation = "High water loss today (hot/dry). Check soil moisture; irrigate early morning or evening if the topsoil is dry."
    else:
        irrigation_code = "check"
        irrigation = "Check soil moisture by hand at root depth before irrigating."

    return {
        "spray_suitable": not spray_reasons,
        "spray_reasons": spray_reasons,
        "spray_reason_codes": spray_codes,
        "rain_expected": rain_coming,
        "heavy_rain_risk": heavy_rain,
        "heat_risk": heat,
        "storm_risk": storm,
        "humidity_disease_risk": current["humidity"] >= 85,
        "irrigation_advice": irrigation,
        "irrigation_code": irrigation_code,
    }


def weather_brief(w: dict) -> str:
    """Compact English description for the Gemini context."""
    c, r = w["current"], w["risks"]
    days = "; ".join(
        f"{d['date']}: {d['min_c']:.0f}-{d['max_c']:.0f}°C, {d['sky']}, rain {d['rain_chance']}%/{d['rain_mm']}mm, wind max {d['wind_max_kmh']:.0f}km/h"
        for d in w["days"][:3]
    )
    flags = [k for k in ("heavy_rain_risk", "heat_risk", "storm_risk", "humidity_disease_risk") if r[k]]
    return (
        f"Now: {c['temp_c']:.0f}°C, {c['sky']}, humidity {c['humidity']}%, wind {c['wind_kmh']:.0f} km/h, "
        f"rain chance next 6h {c['rain_next_6h']}%. Forecast: {days}. "
        f"Spraying suitable now: {'yes' if r['spray_suitable'] else 'no - ' + ', '.join(r['spray_reasons'])}. "
        f"Risk flags: {', '.join(flags) or 'none'}. Irrigation: {r['irrigation_advice']}"
    )
