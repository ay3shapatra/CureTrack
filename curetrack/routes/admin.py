"""Admin staff: occupancy, admissions, discharge queue, history."""
from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, url_for

from ..auth import roles_required
from ..models import Patient, PatientStatus, Role, db
from ..rules import free_rooms, get_today, is_discharge_eligible, patient_day_status
from . import active_patients, audit

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.route("/")
@roles_required(Role.ADMIN)
def dashboard():
    today = get_today()
    patients = active_patients()
    rows = [patient_day_status(p, today) for p in patients]
    by_room = {r["patient"].room_number: r for r in rows}
    queue = sorted([r for r in rows if r["eligible"]], key=lambda r: r["patient"].room_number)
    recent = (Patient.query.filter(Patient.status != PatientStatus.ADMITTED)
              .order_by(Patient.closed_on.desc(), Patient.id.desc()).limit(8).all())
    return render_template("admin/dashboard.html", by_room=by_room, queue=queue, recent=recent,
                           occupied=len(patients), free=len(free_rooms(patients)))


@bp.route("/admit", methods=["GET", "POST"])
@roles_required(Role.ADMIN)
def admit():
    rooms = free_rooms(active_patients())
    form = request.form if request.method == "POST" else {}
    if request.method == "POST":
        errors = []
        name = form.get("name", "").strip()
        sex = form.get("sex", "")
        try:
            age = int(form.get("age", ""))
            if not 0 <= age <= 120:
                raise ValueError
        except ValueError:
            age = None
            errors.append("Age must be a whole number between 0 and 120.")
        try:
            room = int(form.get("room", ""))
        except ValueError:
            room = None
        if not rooms:
            errors.append("Facility is at full capacity. Discharge a patient before admitting.")
        if len(name) < 2:
            errors.append("Enter the patient's full name.")
        if sex not in ("Female", "Male", "Other"):
            errors.append("Select the patient's sex.")
        if room not in rooms:
            errors.append("Selected room is not available. Choose a free room.")
        if not errors:
            p = Patient(name=name, age=age, sex=sex, room_number=room, admitted_on=get_today(),
                        admitted_by_id=g.user.id)
            db.session.add(p)
            db.session.flush()
            audit("admitted", p, f"Room {room}")
            db.session.commit()
            flash(f"{name} admitted to Room {room}. They now appear on the nurses' list for today's "
                  "temperature check.", "success")
            return redirect(url_for("admin.dashboard"))
        for e in errors:
            flash(e, "error")
    preselect = request.args.get("room", type=int)
    return render_template("admin/admit.html", rooms=rooms, form=form, preselect=preselect)


@bp.route("/patients/<int:patient_id>/discharge", methods=["POST"])
@roles_required(Role.ADMIN)
def discharge(patient_id):
    patient = db.session.get(Patient, patient_id) or abort(404)
    today = get_today()
    if not patient.is_active:
        flash("This patient's case is already closed.", "error")
        return redirect(url_for("admin.dashboard"))
    # Re-check the rule on the server: the UI could be stale (e.g. a fever was just recorded)
    if not is_discharge_eligible(patient, today):
        flash(f"{patient.name} does not meet the discharge criterion "
              f"({current_app.config['CURE_DAYS']} consecutive fever-free days). Discharge blocked.", "error")
        return redirect(url_for("admin.dashboard"))
    patient.status = PatientStatus.DISCHARGED
    patient.closed_on = today
    patient.closed_by_id = g.user.id
    patient.closing_note = "Recovered – met fever-free criterion"
    audit("discharged", patient)
    db.session.commit()
    flash(f"{patient.name} discharged. Room {patient.room_number} is now free.", "success")
    return redirect(url_for("admin.dashboard"))


@bp.route("/history")
@roles_required(Role.ADMIN, Role.HEAD_DOCTOR)
def history():
    closed = (Patient.query.filter(Patient.status != PatientStatus.ADMITTED)
              .order_by(Patient.closed_on.desc(), Patient.id.desc()).all())
    return render_template("admin/history.html", closed=closed)
