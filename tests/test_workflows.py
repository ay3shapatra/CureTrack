"""End-to-end workflow tests through the HTTP layer."""
from conftest import login

from curetrack.models import Patient, PatientStatus, TemperatureReading
from curetrack.rules import Stage, get_today, is_discharge_eligible, patient_day_status


def _active():
    return Patient.query.filter_by(status=PatientStatus.ADMITTED).all()


def _pick(stage, eligible=None):
    today = get_today()
    for p in _active():
        s = patient_day_status(p, today)
        if s["stage"] == stage and (eligible is None or s["eligible"] == eligible):
            return p


def test_seed_full_occupancy(app):
    assert len(_active()) == 74


def test_roles_are_enforced(client):
    login(client, "nurse1")
    assert client.get("/admin/").status_code == 403
    assert client.get("/reports/").status_code == 403
    assert client.get("/nurse/").status_code == 200


def test_nurse_records_once_per_day(client, app):
    p = _pick(Stage.NEEDS_TEMP, eligible=False)
    login(client, "nurse1")
    client.post(f"/nurse/patients/{p.id}/temperature", data={"temperature": "38.6", "unit": "C"})
    assert TemperatureReading.query.filter_by(patient_id=p.id, reading_date=get_today()).count() == 1
    r = client.post(f"/nurse/patients/{p.id}/temperature", data={"temperature": "37.0", "unit": "C"},
                    follow_redirects=True)
    assert b"already recorded today" in r.data
    # correction needs a reason
    r = client.post(f"/nurse/patients/{p.id}/temperature",
                    data={"temperature": "37.0", "unit": "C", "correction": "1", "reason": ""},
                    follow_redirects=True)
    assert b"reason is required" in r.data


def test_doctor_cannot_visit_before_temperature(client):
    p = _pick(Stage.NEEDS_TEMP)
    login(client, "doctor1")
    r = client.get(f"/doctor/patients/{p.id}/visit", follow_redirects=True)
    assert b"has not been recorded yet" in r.data


def test_doctor_visit_after_temperature(client):
    p = _pick(Stage.READY_FOR_DOCTOR)
    login(client, "doctor1")
    r = client.post(f"/doctor/patients/{p.id}/visit", data={"notes": "Stable", "treatment": "Fluids"},
                    follow_redirects=True)
    assert b"completed" in r.data
    assert patient_day_status(p, get_today())["stage"] == Stage.DONE


def test_full_capacity_blocks_admission_then_discharge_frees_room(client):
    login(client, "admin")
    r = client.post("/admin/admit", data={"name": "New Person", "age": "40", "sex": "Male", "room": "1"},
                    follow_redirects=True)
    assert b"full capacity" in r.data
    cured = next(p for p in _active() if is_discharge_eligible(p, get_today()))
    client.post(f"/admin/patients/{cured.id}/discharge")
    assert cured.status == PatientStatus.DISCHARGED
    r = client.post("/admin/admit", data={"name": "New Person", "age": "40", "sex": "Male",
                                          "room": str(cured.room_number)}, follow_redirects=True)
    assert b"admitted to Room" in r.data
    assert len(_active()) == 74


def test_discharge_blocked_if_not_cured(client):
    p = next(p for p in _active() if not is_discharge_eligible(p, get_today()))
    login(client, "admin")
    r = client.post(f"/admin/patients/{p.id}/discharge", follow_redirects=True)
    assert b"Discharge blocked" in r.data
    assert p.status == PatientStatus.ADMITTED


def test_normal_reading_completes_cure(client):
    today = get_today()
    p = next(p for p in _active()
             if patient_day_status(p, today)["streak"] == 2 and patient_day_status(p, today)["stage"] == Stage.NEEDS_TEMP)
    login(client, "nurse1")
    r = client.post(f"/nurse/patients/{p.id}/temperature", data={"temperature": "36.9", "unit": "C"},
                    follow_redirects=True)
    assert b"discharge queue" in r.data
    assert is_discharge_eligible(p, today)


def test_head_doctor_sees_mortality_alert(client):
    login(client, "head")
    r = client.get("/reports/")
    assert r.status_code == 200 and b"above the expected" in r.data


def test_advance_day_resets_daily_tasks(client):
    login(client, "nurse1")
    client.post("/demo/advance-day")
    today = get_today()
    assert all(patient_day_status(p, today)["stage"] == Stage.NEEDS_TEMP for p in _active())
