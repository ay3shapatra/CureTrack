# 🌡️ CureTrack

Temperature tracking, doctor rounds and timely discharges for a 74-room virus
quarantine & treatment centre. Built with Python (Flask + SQLAlchemy).

## Who uses it

| Role | Lands on | Can do |
|---|---|---|
| Nurse | Temperature rounds | See who still needs today's reading, record temperature (°C/°F), correct today's reading with a reason |
| Doctor | Doctor rounds | See who is ready (temp taken), sorted by urgency; record visit notes & treatment; record a death |
| Head Doctor | Doctor rounds + Outcomes | Everything a doctor can, plus mortality/success vs the 85% benchmark, discharge delay, closed cases |
| Admin Staff | Beds & discharges | Room grid (x/74), discharge queue (auto-filled), discharge, admit into free room, closed cases |

Demo logins (password `demo123`): `nurse1`, `nurse2`, `doctor1`, `doctor2`, `head`, `admin`.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py                      # http://127.0.0.1:5000
pip install pytest && pytest -q    # 15 tests
```

The first run creates `instance/curetrack.db` and loads demo data (74/74 rooms full).

## Deploy to Vercel

1. Push this folder to a GitHub repo.
2. Create a free Postgres database (e.g. Neon, or Vercel Marketplace > Neon) and copy its connection string.
3. vercel.com > Add New Project > import the repo (Flask is detected automatically, no build settings).
4. Environment variables: `DATABASE_URL` = the Postgres URL, `SECRET_KEY` = any long random string.
5. Deploy. The first request creates the tables and loads demo data.

Without `DATABASE_URL` the app still runs on Vercel using SQLite in `/tmp`, but
data resets whenever the function cold-starts, so use Postgres for a stable demo.

## Demo script (5 minutes)

1. **Admin**: 74/74 full, "Admit" disabled, 5 cured patients in the discharge queue → discharge one → admit a new patient into the freed room.
2. **Nurse**: record a temperature (try 40.3 → high-fever alert; try 55 → rejected; record twice → blocked). Record 36.9 for a patient showing a 2/3 streak → they move to the discharge queue.
3. **Doctor**: patients without today's temperature can't be visited; ready list is sorted by urgency; complete a visit.
4. **Head doctor**: mortality 16.3% vs 15% → alert; average discharge delay.
5. Use **Advance to next day** in the yellow demo bar to show daily tasks resetting and cure streaks progressing.

## Project layout

```
app.py                  entry point (Vercel looks for `app` here)
curetrack/
  __init__.py           app factory, auto-seeding, error pages
  config.py             all clinical rules (fever 38.0 °C, 3 days, 74 rooms, 15%)
  models.py             User, Patient, TemperatureReading, DoctorVisit, AuditLog, Setting
  rules.py              cure streak, daily stage, eligibility, outcome metrics (pure logic)
  auth.py               login/logout, role-based access
  seed.py               demo data
  routes/               nurse.py, doctor.py, admin.py, reports.py, main.py
  templates/            Jinja HTML screens
  static/               CSS + Chart.js
tests/                  rule unit tests + workflow tests
```
