"""Doctor: visit worklist, visit notes, recording a death."""
from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for
from sqlalchemy.exc import IntegrityError

from ..auth import roles_required
from ..models import DoctorVisit, Patient, PatientStatus, Role, db
from ..rules import Stage, get_today, patient_day_status
from . import active_patients, audit

bp = Blueprint("doctor", __name__, url_prefix="/doctor")

DOCTORS = (Role.DOCTOR, Role.HEAD_DOCTOR)


def _priority(row):
    """Sort ready patients: high fever first, then fever, then highest temperature."""
    t = row["reading_today"].temperature_c if row["reading_today"] else 0
    return (not row["high_fever"], not row["fever_today"], -t, row["patient"].room_number)


@bp.route("/")
@roles_required(*DOCTORS)
def worklist():
    today = get_today()
    rows = [patient_day_status(p, today) for p in active_patients()]
    ready = sorted([r for r in rows if r["stage"] == Stage.READY_FOR_DOCTOR], key=_priority)
    waiting = [r for r in rows if r["stage"] == Stage.NEEDS_TEMP]
    done = [r for r in rows if r["stage"] == Stage.DONE]
    cured = [r for r in rows if r["eligible"]]
    return render_template("doctor/worklist.html", ready=ready, waiting=waiting, done=done,
                           cured=cured, total=len(rows))


@bp.route("/patients/<int:patient_id>/visit", methods=["GET", "POST"])
@roles_required(*DOCTORS)
def visit(patient_id):
    patient = db.session.get(Patient, patient_id) or abort(404)
    today = get_today()
    s = patient_day_status(patient, today)

    if not patient.is_active:
        flash(f"{patient.name} is no longer admitted.", "error")
        return redirect(url_for("doctor.worklist"))
    if s["reading_today"] is None:
        # Core rule: never visit before today's temperature is taken
        flash(f"Room {patient.room_number}: today's temperature has not been recorded yet. "
              "The patient is on the nurses' pending list – please visit after it is taken.", "error")
        return redirect(url_for("doctor.worklist"))

    existing = s["visit_today"]
    if existing and existing.doctor_id != g.user.id:
        flash(f"{existing.doctor.name} already visited this patient today. You can read the notes below.", "info")
        return redirect(url_for("main.patient_detail", patient_id=patient.id))

    if request.method == "POST":
        notes = request.form.get("notes", "").strip()
        treatment = request.form.get("treatment", "").strip()
        if not notes:
            flash("Clinical notes are required to complete a visit.", "error")
            return render_template("doctor/visit.html", p=patient, s=s, notes=notes, treatment=treatment)
        if existing:
            existing.notes, existing.treatment = notes, treatment
            audit("visit_updated", patient)
            db.session.commit()
            flash("Visit notes updated.", "success")
        else:
            db.session.add(DoctorVisit(patient_id=patient.id, visit_date=today, doctor_id=g.user.id,
                                       notes=notes, treatment=treatment))
            audit("visit_recorded", patient)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                flash("Another doctor just completed a visit for this patient today.", "error")
                return redirect(url_for("doctor.worklist"))
            flash(f"Visit for Room {patient.room_number} – {patient.name} completed.", "success")
        return redirect(url_for("doctor.worklist"))

    last_visit = next((v for v in reversed(patient.visits) if v.visit_date < today), None)
    return render_template("doctor/visit.html", p=patient, s=s,
                           notes=existing.notes if existing else "",
                           treatment=existing.treatment if existing else (last_visit.treatment if last_visit else ""),
                           last_visit=last_visit)


@bp.route("/patients/<int:patient_id>/deceased", methods=["POST"])
@roles_required(*DOCTORS)
def record_death(patient_id):
    patient = db.session.get(Patient, patient_id) or abort(404)
    if not patient.is_active:
        flash("This patient's case is already closed.", "error")
        return redirect(url_for("main.patient_detail", patient_id=patient.id))
    if request.form.get("confirm_name", "").strip().lower() != patient.name.lower():
        flash("To record a death, type the patient's full name exactly to confirm.", "error")
        return redirect(url_for("main.patient_detail", patient_id=patient.id))
    note = request.form.get("note", "").strip()
    if not note:
        flash("Cause / note is required.", "error")
        return redirect(url_for("main.patient_detail", patient_id=patient.id))
    patient.status = PatientStatus.DECEASED
    patient.closed_on = get_today()
    patient.closed_by_id = g.user.id
    patient.closing_note = note
    audit("death_recorded", patient, note)
    db.session.commit()
    flash(f"Death recorded for {patient.name}. Room {patient.room_number} is now free for admission.", "info")
    return redirect(url_for("doctor.worklist"))
