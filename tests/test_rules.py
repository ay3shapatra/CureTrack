"""Unit tests for the cure / fever rules."""
from datetime import date, timedelta
from types import SimpleNamespace as R

from curetrack.rules import cure_date, fever_free_streak, validate_temperature

D0 = date(2026, 1, 1)


def readings(*temps, skip=()):
    return [R(reading_date=D0 + timedelta(days=i), temperature_c=t)
            for i, t in enumerate(temps) if i not in skip]


def test_three_normal_days_is_cured(app):
    rs = readings(39.0, 38.5, 37.0, 36.8, 37.1)
    assert fever_free_streak(rs) == 3
    assert cure_date(rs) == D0 + timedelta(days=4)


def test_fever_resets_streak(app):
    assert fever_free_streak(readings(37.0, 37.0, 38.0)) == 0   # 38.0 counts as fever


def test_missing_day_breaks_streak(app):
    rs = readings(37.0, 37.0, 37.0, 37.0, skip=(2,))           # day 2 not measured
    assert fever_free_streak(rs) == 1


def test_as_of_ignores_future(app):
    rs = readings(39, 37, 37, 37)
    assert fever_free_streak(rs, as_of=D0 + timedelta(days=2)) == 2


def test_temperature_validation(app):
    assert validate_temperature("37.2", "C") == (37.2, None)
    assert validate_temperature("100.4", "F")[0] == 38.0
    assert validate_temperature("55", "C")[1] is not None       # out of range
    assert validate_temperature("abc", "C")[1] is not None
