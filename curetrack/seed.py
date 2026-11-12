"""Demo data: 74/74 rooms occupied (full, as in the brief), plus closed cases
so the outcomes report has history. Deterministic (fixed random seed).

Built-in demo scenarios:
  * 5 patients already cured (3 fever-free days) -> in admin discharge queue
  * 6 patients with 2 fever-free days -> a normal reading today cures them
  * ~55% of patients still need today's temperature
  * some readings >= 40 C -> urgent flag for doctors
  * past mortality slightly above 15% -> head doctor sees the alert
"""
import random
from datetime import timedelta

from flask import current_app

from .models import DoctorVisit, Patient, PatientStatus, Role, TemperatureReading, User, db
from .rules import get_today

DEMO_PASSWORD = "demo123"

DEMO_USERS = [
    ("nurse1", "Nurse Priya Sharma", Role.NURSE),
    ("nurse2", "Nurse Arjun Nair", Role.NURSE),
    ("doctor1", "Dr. Kavya Rao", Role.DOCTOR),
    ("doctor2", "Dr. Rahul Menon", Role.DOCTOR),
    ("head", "Dr. Anil Mehta", Role.HEAD_DOCTOR),
    ("admin", "Sunita Iyer", Role.ADMIN),
]

FIRST = ["Aarav", "Vivaan", "Aditya", "Ishaan", "Kabir", "Rohan", "Sai", "Arnav", "Dev", "Vihaan",
         "Ananya", "Diya", "Saanvi", "Meera", "Isha", "Kiara", "Riya", "Neha", "Pooja", "Tara",
         "Rahim", "Joseph", "Maria", "Fatima", "Imran", "Lakshmi", "Gopal", "Harini", "Suresh", "Nisha"]
LAST = ["Sharma", "Verma", "Reddy", "Iyer", "Patel", "Khan", "Das", "Gupta", "Singh", "Joshi",
        "Kulkarni", "Pillai", "Bose", "Naidu", "Fernandes", "Chopra", "Mishra", "Rao", "Shetty", "Ghosh"]
TREATMENTS = ["Paracetamol 650mg TDS, oral fluids", "IV fluids 1L NS, antipyretics",
              "Antiviral course day {n}, monitor SpO2", "Supportive care, oral rehydration",
              "Oxygen 2L/min via nasal cannula, antipyretics"]


def _fever(rng):
    return round(rng.uniform(38.1, 40.6), 1)


def _normal(rng):
    return round(rng.uniform(36.3, 37.5), 1)


def seed_demo_data():
    rng = random.Random(42)
    today = get_today()

    users = []
    for username, name, role in DEMO_USERS:
        u = User(username=username, name=name, role=role)
        u.set_password(DEMO_PASSWORD)
        db.session.add(u)
        users.append(u)
    db.session.flush()
    nurses = [u for u in users if u.role == Role.NURSE]
    doctors = [u for u in users if u.is_doctor]
    admin = next(u for u in users if u.role == Role.ADMIN)

    used_names = set()

    def new_name():
        while True:
            n = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
            if n not in used_names:
                used_names.add(n)
                return n

    def add_reading(p, d, temp):
        db.session.add(TemperatureReading(
            patient=p, reading_date=d, temperature_c=temp, recorded_by_id=rng.choice(nurses).id))

    def add_visit(p, d, day_no):
        db.session.add(DoctorVisit(
            patient=p, visit_date=d, doctor_id=rng.choice(doctors).id,
            notes=rng.choice(["Febrile, alert, oriented.", "Stable. Mild fatigue.",
                              "Responding to treatment.", "Afebrile, eating well.",
                              "Persistent fever, monitor closely."]),
            treatment=rng.choice(TREATMENTS).format(n=day_no)))

    # ---------------- closed cases (history for the outcomes report)
    outcomes = [PatientStatus.DISCHARGED] * 41 + [PatientStatus.DECEASED] * 8
    rng.shuffle(outcomes)
    for outcome in outcomes:
        adm = today - timedelta(days=rng.randint(14, 50))
        p = Patient(name=new_name(), age=rng.randint(18, 85), sex=rng.choice(["Female", "Male"]),
                    room_number=rng.randint(1, current_app.config["TOTAL_ROOMS"]), admitted_on=adm,
                    status=outcome, admitted_by_id=admin.id)
        db.session.add(p)
        if outcome == PatientStatus.DISCHARGED:
            fever_days = rng.randint(2, 8)
            delay = rng.choice([0, 0, 1, 1, 2])      # the old, paper-based delays
            total = fever_days + 3 + delay
            for d in range(total):
                day = adm + timedelta(days=d)
                add_reading(p, day, _fever(rng) if d < fever_days else _normal(rng))
                add_visit(p, day, d + 1)
            p.closed_on = adm + timedelta(days=total - 1)
            p.closing_note = "Recovered – met fever-free criterion"
            p.closed_by_id = admin.id
        else:
            days = rng.randint(3, 10)
            for d in range(days):
                day = adm + timedelta(days=d)
                add_reading(p, day, _fever(rng))
                add_visit(p, day, d + 1)
            p.closed_on = adm + timedelta(days=days - 1)
            p.closing_note = "Respiratory failure"
            p.closed_by_id = rng.choice(doctors).id

    # ---------------- active patients: all 74 rooms full
    rooms = list(range(1, current_app.config["TOTAL_ROOMS"] + 1))
    rng.shuffle(rooms)
    for i, room in enumerate(rooms):
        if i < 5:                       # cured, waiting for discharge
            D = rng.randint(6, 9)
            fever_until = D - 3
        elif i < 11:                    # 2 fever-free days so far
            D = rng.randint(5, 8)
            fever_until = D - 2
        else:                           # still sick / recently admitted
            D = rng.randint(0, 10)
            fever_until = rng.randint(max(0, D - 1), D + 4)
        adm = today - timedelta(days=D)
        p = Patient(name=new_name(), age=rng.randint(5, 88), sex=rng.choice(["Female", "Male"]),
                    room_number=room, admitted_on=adm, admitted_by_id=admin.id)
        db.session.add(p)
        for d in range(D):              # past days (not today)
            day = adm + timedelta(days=d)
            in_fever = d < fever_until
            if i >= 11 and in_fever and rng.random() < 0.08:
                continue                # a missed reading from the paper era
            add_reading(p, day, _fever(rng) if in_fever else _normal(rng))
            if rng.random() < 0.85:
                add_visit(p, day, d + 1)
        # today: some temps already done, some visits already done
        if i >= 11 and rng.random() < 0.45:
            add_reading(p, today, _fever(rng) if D < fever_until else _normal(rng))
            if rng.random() < 0.4:
                add_visit(p, today, D + 1)

    db.session.commit()
