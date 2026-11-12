"""Business rules, kept free of Flask/HTTP so they are easy to test.

Key definitions (agreed with the head doctor):
  * Fever           = reading >= FEVER_THRESHOLD_C (38.0 C / 100.4 F)
  * Fever-free day  = a calendar day with a recorded reading below the threshold
  * Cured           = CURE_DAYS (3) CONSECUTIVE fever-free days. A day with no
                      reading is "unknown" and breaks the streak - we never
                      assume a patient was fever-free on a day nobody checked.
"""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from flask import current_app

from .models import PatientStatus, Setting, db


# ---------------------------------------------------------------- dates
def get_day_offset():
    s = db.session.get(Setting, "day_offset")
    return int(s.value) if s else 0


def get_today():
    """Facility's current date (+ demo offset when demo mode is on)."""
    tz = ZoneInfo(current_app.config.get("FACILITY_TZ", "Asia/Kolkata"))
    today = datetime.now(tz).date()
    if current_app.config.get("DEMO_MODE"):
        today += timedelta(days=get_day_offset())
    return today


# ---------------------------------------------------------------- temperatures
def c_to_f(c):
    return round(c * 9 / 5 + 32, 1)


def is_fever(temp_c, threshold=None):
    threshold = threshold if threshold is not None else current_app.config["FEVER_THRESHOLD_C"]
    return temp_c >= threshold


def validate_temperature(raw_value, unit="C"):
    """Return (temp_c, error_message). Accepts Celsius or Fahrenheit input."""
    cfg = current_app.config
    try:
        value = float(str(raw_value).strip())
    except (TypeError, ValueError):
        return None, "Enter the temperature as a number, e.g. 37.2"
    temp_c = (value - 32) * 5 / 9 if unit == "F" else value
    temp_c = round(temp_c, 1)
    if not (cfg["MIN_VALID_TEMP_C"] <= temp_c <= cfg["MAX_VALID_TEMP_C"]):
        lo, hi = cfg["MIN_VALID_TEMP_C"], cfg["MAX_VALID_TEMP_C"]
        return None, (f"{value}°{unit} is outside the valid range "
                      f"({lo}–{hi} °C / {c_to_f(lo)}–{c_to_f(hi)} °F). Re-measure and check the unit.")
    return temp_c, None


# ---------------------------------------------------------------- cure logic
def fever_free_streak(readings, as_of=None, threshold=None):
    """Consecutive fever-free calendar days ending at the latest reading (<= as_of)."""
    rs = sorted((r for r in readings if as_of is None or r.reading_date <= as_of),
                key=lambda r: r.reading_date)
    streak, expected_date = 0, None
    for r in reversed(rs):
        if is_fever(r.temperature_c, threshold):
            break
        if expected_date is not None and r.reading_date != expected_date:
            break  # a missing day breaks the streak
        streak += 1
        expected_date = r.reading_date - timedelta(days=1)
    return streak


def cure_date(readings, threshold=None, cure_days=None):
    """Date the patient met the cure criterion in their *latest* fever-free run
    (used to measure discharge delay). None if not met."""
    cure_days = cure_days or current_app.config["CURE_DAYS"]
    run, prev, met_on = 0, None, None
    for r in sorted(readings, key=lambda r: r.reading_date):
        if is_fever(r.temperature_c, threshold):
            run, met_on = 0, None
        elif prev is not None and r.reading_date == prev + timedelta(days=1):
            run += 1
        else:
            run, met_on = 1, None  # first reading or gap -> new run
        if run == cure_days and met_on is None:
            met_on = r.reading_date
        prev = r.reading_date
    return met_on


def is_discharge_eligible(patient, today):
    return (patient.status == PatientStatus.ADMITTED
            and fever_free_streak(patient.readings, as_of=today) >= current_app.config["CURE_DAYS"])


# ---------------------------------------------------------------- daily status
class Stage:
    NEEDS_TEMP = "needs_temp"            # nurse must measure
    READY_FOR_DOCTOR = "ready_for_doctor"
    DONE = "done"                        # temp + doctor visit complete today


def patient_day_status(patient, today):
    cfg = current_app.config
    reading_today = next((r for r in patient.readings if r.reading_date == today), None)
    visit_today = next((v for v in patient.visits if v.visit_date == today), None)
    past = [r for r in patient.readings if r.reading_date <= today]
    last = past[-1] if past else None
    yesterday = today - timedelta(days=1)

    if reading_today is None:
        stage = Stage.NEEDS_TEMP
    elif visit_today is None:
        stage = Stage.READY_FOR_DOCTOR
    else:
        stage = Stage.DONE

    streak = fever_free_streak(patient.readings, as_of=today)
    return {
        "patient": patient,
        "reading_today": reading_today,
        "visit_today": visit_today,
        "stage": stage,
        "last_reading": last,
        "streak": streak,
        "cure_days": cfg["CURE_DAYS"],
        "eligible": patient.status == PatientStatus.ADMITTED and streak >= cfg["CURE_DAYS"],
        "fever_today": bool(reading_today and is_fever(reading_today.temperature_c)),
        "high_fever": bool(last and last.temperature_c >= cfg["HIGH_FEVER_C"]),
        "missed_yesterday": (patient.admitted_on <= yesterday
                             and not any(r.reading_date == yesterday for r in patient.readings)),
        "day_in_care": (today - patient.admitted_on).days + 1,
    }


# ---------------------------------------------------------------- rooms
def free_rooms(active_patients):
    taken = {p.room_number for p in active_patients}
    return [n for n in range(1, current_app.config["TOTAL_ROOMS"] + 1) if n not in taken]


# ---------------------------------------------------------------- outcome metrics
def outcome_metrics(all_patients, today):
    cfg = current_app.config
    discharged = [p for p in all_patients if p.status == PatientStatus.DISCHARGED]
    deceased = [p for p in all_patients if p.status == PatientStatus.DECEASED]
    active = [p for p in all_patients if p.status == PatientStatus.ADMITTED]
    closed = len(discharged) + len(deceased)

    mortality = len(deceased) / closed if closed else None
    recovery = len(discharged) / closed if closed else None

    stays = [(p.closed_on - p.admitted_on).days for p in discharged if p.closed_on]
    delays = []
    for p in discharged:
        cd = cure_date(p.readings)
        if cd and p.closed_on:
            delays.append(max(0, (p.closed_on - cd).days))

    statuses = [patient_day_status(p, today) for p in active]
    n = len(active) or 1

    # cumulative mortality over time (by close date) for the trend chart
    closed_sorted = sorted((p for p in discharged + deceased if p.closed_on), key=lambda p: p.closed_on)
    trend, d_count, total = [], 0, 0
    for p in closed_sorted:
        total += 1
        d_count += p.status == PatientStatus.DECEASED
        if trend and trend[-1]["date"] == p.closed_on.isoformat():
            trend.pop()
        trend.append({"date": p.closed_on.isoformat(), "rate": round(100 * d_count / total, 1)})

    return {
        "active": len(active),
        "discharged": len(discharged),
        "deceased": len(deceased),
        "closed": closed,
        "mortality": mortality,
        "recovery": recovery,
        "expected_mortality": cfg["EXPECTED_MORTALITY"],
        "mortality_alert": mortality is not None and mortality > cfg["EXPECTED_MORTALITY"],
        "small_sample": closed < cfg["MIN_CASES_FOR_STATS"],
        "avg_stay": round(sum(stays) / len(stays), 1) if stays else None,
        "avg_discharge_delay": round(sum(delays) / len(delays), 2) if delays else None,
        "delayed_discharges": sum(1 for d in delays if d > 0),
        "temps_done_pct": round(100 * sum(s["reading_today"] is not None for s in statuses) / n),
        "visits_done_pct": round(100 * sum(s["visit_today"] is not None for s in statuses) / n),
        "eligible_waiting": sum(s["eligible"] for s in statuses),
        "occupancy": len(active),
        "total_rooms": cfg["TOTAL_ROOMS"],
        "trend": trend,
    }
