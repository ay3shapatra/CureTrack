"""Nurse: daily temperature worklist and recording."""
from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request
from sqlalchemy.exc import IntegrityError

from ..auth import roles_required
from ..models import Patient, Role, TemperatureReading, db, utcnow
from ..rules import Stage, c_to_f, fever_free_streak, get_today, is_fever, patient_day_status, validate_temperature
from . import active_patients, audit, safe_next

bp = Blueprint("nurse", __name__, url_prefix="/nurse")


@bp.route("/")
@roles_required(Role.NURSE)
def worklist():
    today = get_today()
    rows = [patient_day_status(p, today) for p in active_patients()]
    pending = [r for r in rows if r["stage"] == Stage.NEEDS_TEMP]
    done = [r for r in rows if r["stage"] != Stage.NEEDS_TEMP]
    tab = request.args.get("tab", "pending")
    return render_template("nurse/worklist.html", pending=pending, done=done, tab=tab,
                           total=len(rows))


@bp.route("/patients/<int:patient_id>/temperature", methods=["POST"])
@roles_required(Role.NURSE)
def record_temperature(patient_id):
    patient = db.session.get(Patient, patient_id) or abort(404)
    today = get_today()
    back = safe_next("nurse.worklist")

    if not patient.is_active:
        flash(f"{patient.name} is no longer admitted - temperature not recorded.", "error")
        return redirect(back)

    temp_c, error = validate_temperature(request.form.get("temperature"), request.form.get("unit", "C"))
    if error:
        flash(error, "error")
        return redirect(back)

    existing = TemperatureReading.query.filter_by(patient_id=patient.id, reading_date=today).first()
    is_correction = request.form.get("correction") == "1"

    if existing and not is_correction:
        flash(f"Room {patient.room_number}: temperature already recorded today "
              f"({existing.temperature_c} °C by {existing.recorded_by.name} at "
              f"{existing.recorded_at:%H:%M} UTC). Use 'Correct' if the earlier entry was wrong.", "error")
        return redirect(back)

    if is_correction:
        if not existing:
            flash("Nothing to correct - no reading recorded today.", "error")
            return redirect(back)
        reason = request.form.get("reason", "").strip()
        if len(reason) < 3:
            flash("A reason is required to correct a reading.", "error")
            return redirect(back)
        old = existing.temperature_c
        existing.temperature_c = temp_c
        existing.corrected_at = utcnow()
        existing.correction_reason = reason
        audit("temperature_corrected", patient, f"{old} -> {temp_c} C. Reason: {reason}")
        db.session.commit()
        flash(f"Room {patient.room_number}: reading corrected from {old} °C to {temp_c} °C.", "success")
    else:
        db.session.add(TemperatureReading(patient_id=patient.id, reading_date=today,
                                          temperature_c=temp_c, recorded_by_id=g.user.id))
        audit("temperature_recorded", patient, f"{temp_c} C")
        try:
            db.session.commit()
        except IntegrityError:          # two nurses submitted at the same moment
            db.session.rollback()
            flash(f"Room {patient.room_number}: another nurse just recorded this patient's temperature.", "error")
            return redirect(back)
        flash(f"Room {patient.room_number} – {patient.name}: {temp_c} °C ({c_to_f(temp_c)} °F) recorded. "
              "Patient is now ready for the doctor's visit.", "success")

    # Clinical alerts for the nurse
    if temp_c >= current_app.config["HIGH_FEVER_C"]:
        flash(f"HIGH FEVER ({temp_c} °C) for {patient.name}. Patient is flagged urgent on the doctors' list – "
              "also inform the doctor on duty.", "warning")
    elif is_fever(temp_c):
        flash(f"{patient.name} has a fever ({temp_c} °C). Cure streak reset to 0 days.", "warning")
    else:
        db.session.refresh(patient)
        streak = fever_free_streak(patient.readings, as_of=today)
        if streak >= current_app.config["CURE_DAYS"]:
            flash(f"{patient.name} has completed {streak} fever-free days and is now in the "
                  "admin discharge queue.", "success")
    return redirect(back)
