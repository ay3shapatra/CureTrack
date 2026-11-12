"""Head doctor: treatment quality vs the 85% success benchmark."""
from flask import Blueprint, render_template

from ..auth import roles_required
from ..models import Patient, Role
from ..rules import get_today, outcome_metrics

bp = Blueprint("reports", __name__, url_prefix="/reports")


@bp.route("/")
@roles_required(Role.HEAD_DOCTOR)
def outcomes():
    m = outcome_metrics(Patient.query.all(), get_today())
    return render_template("reports/outcomes.html", m=m)
