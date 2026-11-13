from datetime import date, datetime, timedelta, timezone

import pytest

from app.services import risk_engine as re
from app.services.risk_engine import CAUTION, SAFE, UNSAFE
from app.thresholds import THRESHOLDS as TH

IST = timezone(timedelta(hours=5, minutes=30))
DAY = date(2026, 11, 12)
POINT = (8.635, 76.775)


def row(hour=8, day=DAY, **overrides):
    base = {
        "time": datetime(day.year, day.month, day.day, hour, tzinfo=IST),
        "wave_height": 0.4, "wave_period": 9.0, "wind_wave_height": 0.2, "swell_wave_height": 0.3,
        "wind_speed": 8.0, "wind_gust": 12.0, "precipitation": 0.0, "weather_code": 1, "is_day": 1,
    }
    base.update(overrides)
    return base


def level(boat="non_motorised", warnings=None, reports=None, point=None, **overrides):
    return re.evaluate_hour(row(**overrides), boat, TH, warnings, reports, point).level


def warning(start_hour=0, hours=24, lat=POINT[0], lon=POINT[1], radius=50):
    start = datetime(2026, 11, 12, start_hour, tzinfo=IST)
    return {"title": "Cyclone alert", "center_lat": lat, "center_lon": lon, "radius_km": radius,
            "starts_at": start, "expires_at": start + timedelta(hours=hours)}


def report(type="rough_sea", up=0, down=0, lat=POINT[0], lon=POINT[1], created_hour=6, hours=6, user_id=1):
    created = datetime(2026, 11, 12, created_hour, tzinfo=IST)
    return {"type": type, "lat": lat, "lon": lon, "created_at": created,
            "expires_at": created + timedelta(hours=hours), "up": up, "down": down, "user_id": user_id}


# ---- threshold boundaries, per boat type -------------------------------------------------

@pytest.mark.parametrize("boat", ["non_motorised", "motorised", "mechanised"])
def test_wave_boundaries(boat):
    th = TH[boat]
    assert level(boat, wave_height=th["wave_caution"]) == SAFE          # at the limit is still fine
    assert level(boat, wave_height=th["wave_caution"] + 0.01) == CAUTION
    assert level(boat, wave_height=th["wave_unsafe"]) == CAUTION
    assert level(boat, wave_height=th["wave_unsafe"] + 0.01) == UNSAFE


@pytest.mark.parametrize("boat", ["non_motorised", "motorised", "mechanised"])
def test_wind_boundaries(boat):
    th = TH[boat]
    assert level(boat, wind_speed=th["wind_caution"]) == SAFE
    assert level(boat, wind_speed=th["wind_caution"] + 0.1) == CAUTION
    assert level(boat, wind_speed=th["wind_unsafe"]) == CAUTION
    assert level(boat, wind_speed=th["wind_unsafe"] + 0.1) == UNSAFE


@pytest.mark.parametrize("boat", ["non_motorised", "motorised", "mechanised"])
def test_gust_boundary(boat):
    th = TH[boat]
    assert level(boat, wind_gust=th["gust_unsafe"] - 0.1) == SAFE
    assert level(boat, wind_gust=th["gust_unsafe"]) == UNSAFE


def test_thresholds_match_the_plan_table():
    assert (TH["non_motorised"]["wave_caution"], TH["non_motorised"]["wave_unsafe"], TH["non_motorised"]["wind_unsafe"]) == (1.0, 1.5, 30)
    assert (TH["motorised"]["wave_caution"], TH["motorised"]["wave_unsafe"], TH["motorised"]["wind_unsafe"]) == (1.5, 2.5, 40)
    assert (TH["mechanised"]["wave_caution"], TH["mechanised"]["wave_unsafe"], TH["mechanised"]["wind_unsafe"]) == (2.5, 3.5, 50)


def test_same_conditions_differ_by_boat():
    conditions = dict(wave_height=2.0, wind_speed=25.0, wind_gust=35.0)
    assert level("mechanised", **conditions) == SAFE
    assert level("motorised", **conditions) == CAUTION
    assert level("non_motorised", **conditions) == UNSAFE


# ---- other factors ------------------------------------------------------------------------

def test_steep_sea_raises_to_caution():
    # 0.8 m is under the 1.0 m caution limit, but >= 0.7 x 1.0 with a short period.
    assert level("non_motorised", wave_height=0.8, wave_period=9) == SAFE
    assert level("non_motorised", wave_height=0.8, wave_period=5) == CAUTION
    assert level("non_motorised", wave_height=0.6, wave_period=5) == SAFE


@pytest.mark.parametrize("code", [95, 96, 99])
def test_thunderstorm_is_unsafe_for_every_boat(code):
    for boat in ("non_motorised", "motorised", "mechanised"):
        hour = re.evaluate_hour(row(weather_code=code), boat, TH)
        assert hour.level == UNSAFE
        assert any(r.text_key == "thunderstorm" for r in hour.reasons)


def test_non_thunderstorm_code_is_ignored():
    assert level("non_motorised", weather_code=61) == SAFE


def test_heavy_rain_is_caution():
    assert level("mechanised", precipitation=7.4) == SAFE
    assert level("mechanised", precipitation=7.5) == CAUTION


def test_night_rule_only_for_non_motorised():
    assert level("non_motorised", hour=2, is_day=0) == CAUTION
    assert level("motorised", hour=2, is_day=0) == SAFE
    assert level("mechanised", hour=2, is_day=0) == SAFE
    assert level("non_motorised", hour=8, is_day=1) == SAFE


def test_missing_wave_data_is_never_safe():
    assert level("mechanised", wave_height=None) == CAUTION


def test_reasons_are_structured():
    hour = re.evaluate_hour(row(wave_height=2.1), "non_motorised", TH)
    r = hour.reasons[0].to_dict()
    assert r["factor"] == "wave_height" and r["value"] == 2.1 and r["unit"] == "m"
    assert r["threshold"] == 1.5 and r["level"] == UNSAFE and r["text_key"] == "wave_height"


# ---- official warnings ---------------------------------------------------------------------

def test_warning_forces_unsafe_in_calm_weather():
    for boat in ("non_motorised", "motorised", "mechanised"):
        assert level(boat, warnings=[warning()], point=POINT) == UNSAFE


def test_warning_outside_time_or_area_does_not_apply():
    assert level("mechanised", warnings=[warning(start_hour=12, hours=6)], point=POINT) == SAFE  # row is 08:00
    assert level("mechanised", warnings=[warning(lat=25.13, lon=56.36, radius=40)], point=POINT) == SAFE


# ---- community reports ----------------------------------------------------------------------

def test_confirmed_report_raises_safe_to_caution():
    assert level("mechanised", reports=[report(up=1)], point=POINT) == CAUTION                           # someone confirmed it
    assert level("mechanised", reports=[report(user_id=1), report(user_id=2)], point=POINT) == CAUTION   # two fishers agree


def test_one_unconfirmed_report_is_shown_but_changes_nothing():
    hour = re.evaluate_hour(row(), "mechanised", TH, None, [report()], POINT)
    assert hour.level == SAFE
    assert hour.reasons[0].text_key == "reports_unconfirmed" and hour.reasons[0].level == SAFE
    # The same fisher posting twice is still one voice.
    assert level("mechanised", reports=[report(user_id=7), report("storm", user_id=7)], point=POINT) == SAFE


def test_stale_forecast_is_never_safe():
    assert level("mechanised") == SAFE
    hour = re.evaluate_hour(row(), "mechanised", TH, data_stale=True)
    assert hour.level == CAUTION and hour.reasons[0].factor == "data_stale"
    assert re.evaluate_hour(row(wave_height=4.0), "mechanised", TH, data_stale=True).level == UNSAFE


def test_trip_check_without_forecast_is_not_safe():
    check = re.trip_check([], datetime(2026, 11, 12, 9, 10, tzinfo=IST))
    assert check["level"] == CAUTION and check["reasons"][0].factor == "data_missing"


def test_many_reports_stay_caution():
    reports = [report("rough_sea", user_id=1), report("storm", user_id=2), report("harbour_mouth_rough", user_id=3)]
    hour = re.evaluate_hour(row(), "mechanised", TH, None, reports, POINT)
    assert hour.level == CAUTION
    assert hour.reasons[0].text_key == "reports_rough" and hour.reasons[0].value == 3


def test_reports_never_lower_unsafe():
    assert level("non_motorised", reports=[report(up=10)], point=POINT, wave_height=3.0) == UNSAFE
    assert level("non_motorised", reports=[report("no_fish", up=10)], point=POINT, wave_height=3.0) == UNSAFE


def test_ignored_reports():
    assert level("mechanised", reports=[report(down=1)], point=POINT) == SAFE                      # voted down
    assert level("mechanised", reports=[report(lat=9.965, lon=76.235)], point=POINT) == SAFE       # too far
    assert level("mechanised", reports=[report(created_hour=0, hours=6)], point=POINT) == SAFE     # expired by 08:00
    assert level("mechanised", reports=[report("no_fish")], point=POINT) == SAFE                   # not a hazard


# ---- windows and summaries -----------------------------------------------------------------

def day_rows(waves_by_hour, **overrides):
    return [row(hour=h, wave_height=waves_by_hour(h), is_day=1 if 6 <= h < 18 else 0, **overrides) for h in range(24)]


def test_best_window_finds_longest_run():
    # motorised: SAFE 04-06 (2 h), rough at 06, SAFE 07-11 (4 h), rough from 11.
    def waves(h):
        return 0.5 if h in (4, 5, 7, 8, 9, 10) else 2.0
    hours = re.evaluate_range(day_rows(waves), "motorised", TH)
    w = re.best_window(hours, DAY)
    assert w["start"] == datetime(2026, 11, 12, 7, tzinfo=IST)
    assert w["end"] == datetime(2026, 11, 12, 11, tzinfo=IST)
    assert w["return_by"] == datetime(2026, 11, 12, 10, 30, tzinfo=IST)
    assert w["hours"] == 4


def test_best_window_respects_earliest_latest_and_min_hours():
    hours = re.evaluate_range(day_rows(lambda h: 0.5), "motorised", TH)
    w = re.best_window(hours, DAY)
    assert w["start"].hour == 3 and w["end"].hour == 19
    one_hour = re.evaluate_range(day_rows(lambda h: 0.5 if h == 9 else 3.0), "motorised", TH)
    assert re.best_window(one_hour, DAY) is None


def test_best_window_none_when_no_safe_hour():
    hours = re.evaluate_range(day_rows(lambda h: 3.0), "motorised", TH)
    assert re.best_window(hours, DAY) is None
    assert re.best_window(hours, date(2026, 11, 13)) is None  # no data that day


def test_best_window_drops_hours_already_over():
    hours = re.evaluate_range(day_rows(lambda h: 0.5), "motorised", TH)
    now = datetime(2026, 11, 12, 12, 20, tzinfo=IST)
    w = re.best_window(hours, DAY, now=now)
    assert w["start"] == now and w["end"].hour == 19


def test_day_summary_verdicts():
    calm = re.evaluate_range(day_rows(lambda h: 0.5), "non_motorised", TH)
    s = re.day_summary(calm, DAY)
    assert s["verdict"] == SAFE and s["window"]["start"].hour == 6  # night hours are CAUTION for small boats

    middling = re.evaluate_range(day_rows(lambda h: 1.2), "non_motorised", TH)
    s = re.day_summary(middling, DAY)
    assert s["verdict"] == CAUTION and s["window"] is None and s["reasons"][0].factor == "wave_height"

    storm = re.evaluate_range(day_rows(lambda h: 3.0), "non_motorised", TH)
    s = re.day_summary(storm, DAY)
    assert s["verdict"] == UNSAFE and s["safe_hours"] == 0


def test_day_summary_warning_makes_whole_day_unsafe():
    hours = re.evaluate_range(day_rows(lambda h: 0.3), "mechanised", TH, [warning(start_hour=14, hours=3)], None, POINT)
    s = re.day_summary(hours, DAY)
    assert s["verdict"] == UNSAFE and s["window"] is None
    assert s["reasons"][0].factor == "official_warning"


def test_best_days_ranks_by_safe_daylight_hours():
    d2 = date(2026, 11, 13)
    rows = day_rows(lambda h: 3.0) + [
        row(hour=h, day=d2, wave_height=0.5, is_day=1 if 6 <= h < 18 else 0) for h in range(24)
    ]
    ranked = re.best_days(re.evaluate_range(rows, "motorised", TH))
    assert ranked[0]["date"] == d2 and ranked[0]["safe_daylight_hours"] == 12
    assert ranked[1]["date"] == DAY and ranked[1]["safe_daylight_hours"] == 0


def test_confidence():
    now = datetime(2026, 11, 12, 6, tzinfo=IST)
    assert re.confidence(now + timedelta(hours=5), now) == "high"
    assert re.confidence(now + timedelta(hours=24), now) == "medium"
    assert re.confidence(now + timedelta(hours=71), now) == "medium"
    assert re.confidence(now + timedelta(hours=72), now) == "low"


def test_trip_check_looks_two_hours_ahead():
    hours = re.evaluate_range(day_rows(lambda h: 3.0 if h >= 11 else 0.5), "motorised", TH)
    assert re.trip_check(hours, datetime(2026, 11, 12, 8, 10, tzinfo=IST))["level"] == SAFE
    check = re.trip_check(hours, datetime(2026, 11, 12, 9, 10, tzinfo=IST))
    assert check["level"] == UNSAFE and check["reasons"][0].factor == "wave_height"
    # Returning before the bad weather: nothing to warn about.
    back_early = datetime(2026, 11, 12, 10, 30, tzinfo=IST)
    assert re.trip_check(hours, datetime(2026, 11, 12, 9, 10, tzinfo=IST), back_early)["level"] == SAFE


def test_engine_is_deterministic_and_does_not_mutate_input():
    rows = day_rows(lambda h: 1.2)
    snapshot = [dict(r) for r in rows]
    a = [h.to_dict() for h in re.evaluate_range(rows, "non_motorised", TH)]
    b = [h.to_dict() for h in re.evaluate_range(rows, "non_motorised", TH)]
    assert a == b and rows == snapshot
