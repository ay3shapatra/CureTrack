"""Home redirect, patient list/detail (all roles) and demo controls."""
from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, url_for

from ..auth import HOME_BY_ROLE, login_required
from ..models import Patient, PatientStatus, Role, Setting, db
from ..rules import get_day_offset, get_today, patient_day_status
from . import active_patients, safe_next

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    if g.user is None:
        return redirect(url_for("auth.login"))
    return redirect(url_for(HOME_BY_ROLE[g.user.role]))


@bp.route("/patients")
@login_required
def patient_list():
    q = request.args.get("q", "").strip()
    show = request.args.get("show", "active")
    query = Patient.query
    if show == "active":
        query = query.filter_by(status=PatientStatus.ADMITTED)
    if q:
        if q.isdigit():
            query = query.filter((Patient.room_number == int(q)) | (Patient.id == int(q)))
        else:
            query = query.filter(Patient.name.ilike(f"%{q}%"))
    patients = query.order_by(Patient.status, Patient.room_number).all()
    today = get_today()
    rows = [patient_day_status(p, today) for p in patients]
    return render_template("patients/list.html", rows=rows, q=q, show=show)


@bp.route("/patients/<int:patient_id>")
@login_required
def patient_detail(patient_id):
    patient = db.session.get(Patient, patient_id) or abort(404)
    today = get_today()
    status = patient_day_status(patient, today)
    chart = [{"date": r.reading_date.isoformat(), "temp": r.temperature_c} for r in patient.readings]
    # Clinical notes are visible to doctors only
    show_notes = g.user.is_doctor
    return render_template("patients/detail.html", p=patient, s=status, chart=chart,
                           show_notes=show_notes)


# ------------------------------------------------------------------ demo controls
def _require_demo():
    if not current_app.config.get("DEMO_MODE"):
        abort(404)


@bp.route("/demo/advance-day", methods=["POST"])
@login_required
def demo_advance_day():
    _require_demo()
    s = db.session.get(Setting, "day_offset") or Setting(key="day_offset", value="0")
    s.value = str(get_day_offset() + 1)
    db.session.add(s)
    db.session.commit()
    flash(f"Simulated date moved forward to {get_today():%a %d %b %Y}. "
          "All daily tasks are pending again.", "info")
    return redirect(safe_next("main.index"))


@bp.route("/demo/reset", methods=["POST"])
@login_required
def demo_reset():
    _require_demo()
    from ..seed import seed_demo_data
    db.drop_all()
    db.create_all()
    seed_demo_data()
    flash("Demo data has been reset. Please log in again.", "info")
    return redirect(url_for("auth.logout"))
