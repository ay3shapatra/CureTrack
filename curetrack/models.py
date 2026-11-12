"""Database tables."""
from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Role:
    NURSE = "nurse"
    DOCTOR = "doctor"
    HEAD_DOCTOR = "head_doctor"
    ADMIN = "admin"

    LABELS = {
        NURSE: "Nurse",
        DOCTOR: "Doctor",
        HEAD_DOCTOR: "Head Doctor",
        ADMIN: "Admin Staff",
    }


class PatientStatus:
    ADMITTED = "admitted"
    DISCHARGED = "discharged"    # recovered
    DECEASED = "deceased"


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_doctor(self):
        return self.role in (Role.DOCTOR, Role.HEAD_DOCTOR)

    @property
    def role_label(self):
        return Role.LABELS.get(self.role, self.role)


class Patient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    age = db.Column(db.Integer, nullable=False)
    sex = db.Column(db.String(10), nullable=False)
    room_number = db.Column(db.Integer, nullable=False)
    admitted_on = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), default=PatientStatus.ADMITTED, nullable=False, index=True)
    closed_on = db.Column(db.Date)                       # discharge or death date
    closed_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    closing_note = db.Column(db.Text)
    admitted_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))

    readings = db.relationship(
        "TemperatureReading", backref="patient", lazy="selectin",
        order_by="TemperatureReading.reading_date", cascade="all, delete-orphan",
    )
    visits = db.relationship(
        "DoctorVisit", backref="patient", lazy="selectin",
        order_by="DoctorVisit.visit_date", cascade="all, delete-orphan",
    )
    closed_by = db.relationship("User", foreign_keys=[closed_by_id])

    @property
    def is_active(self):
        return self.status == PatientStatus.ADMITTED

    @property
    def code(self):
        return f"P-{self.id:04d}"


class TemperatureReading(db.Model):
    """At most ONE reading per patient per calendar day (enforced by the DB)."""
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patient.id"), nullable=False, index=True)
    reading_date = db.Column(db.Date, nullable=False)
    temperature_c = db.Column(db.Float, nullable=False)
    recorded_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    recorded_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    corrected_at = db.Column(db.DateTime)
    correction_reason = db.Column(db.String(200))

    recorded_by = db.relationship("User")

    __table_args__ = (db.UniqueConstraint("patient_id", "reading_date", name="uq_one_reading_per_day"),)


class DoctorVisit(db.Model):
    """At most ONE doctor visit per patient per calendar day."""
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patient.id"), nullable=False, index=True)
    visit_date = db.Column(db.Date, nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    notes = db.Column(db.Text)
    treatment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    doctor = db.relationship("User")

    __table_args__ = (db.UniqueConstraint("patient_id", "visit_date", name="uq_one_visit_per_day"),)


class AuditLog(db.Model):
    """Who did what, when. Clinical records should never change silently."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    patient_id = db.Column(db.Integer, db.ForeignKey("patient.id"))
    action = db.Column(db.String(50), nullable=False)
    detail = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    user = db.relationship("User")
    patient = db.relationship("Patient")


class Setting(db.Model):
    key = db.Column(db.String(50), primary_key=True)
    value = db.Column(db.String(200))
