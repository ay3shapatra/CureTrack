"""Shared helpers for route modules."""
from flask import g, request, url_for

from ..models import AuditLog, Patient, PatientStatus, db


def active_patients():
    return (Patient.query.filter_by(status=PatientStatus.ADMITTED)
            .order_by(Patient.room_number).all())


def audit(action, patient=None, detail=""):
    db.session.add(AuditLog(user_id=g.user.id if g.get("user") else None,
                            patient_id=patient.id if patient else None,
                            action=action, detail=detail[:300]))


def safe_next(default_endpoint, **kwargs):
    nxt = request.form.get("next") or request.args.get("next")
    if nxt and nxt.startswith("/") and not nxt.startswith("//"):
        return nxt
    return url_for(default_endpoint, **kwargs)
