"""App configuration. Every clinical/business constant lives here so the
head doctor's rules can be changed in one place."""
import os

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _database_url():
    url = os.environ.get("DATABASE_URL")
    if url:
        # Some providers hand out postgres://, SQLAlchemy wants postgresql://
        # and SQLAlchemy 2.1 defaults to psycopg v3, so name the psycopg2 driver explicitly.
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+psycopg2://", 1)
        elif url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
        return url
    if os.environ.get("VERCEL"):
        # Vercel's filesystem is read-only except /tmp (data resets on cold start).
        return "sqlite:////tmp/curetrack.db"
    os.makedirs(os.path.join(BASE_DIR, "instance"), exist_ok=True)
    return "sqlite:///" + os.path.join(BASE_DIR, "instance", "curetrack.db")


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
    SQLALCHEMY_DATABASE_URI = _database_url()
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # ---- Facility & clinical rules ----
    FACILITY_TZ = os.environ.get("FACILITY_TZ", "Asia/Kolkata")
    TOTAL_ROOMS = 74                 # rooms numbered 1..74, one patient per room
    FEVER_THRESHOLD_C = 38.0         # reading >= this is a fever
    HIGH_FEVER_C = 40.0              # reading >= this is flagged urgent for doctors
    MIN_VALID_TEMP_C = 34.0          # anything outside this range is rejected
    MAX_VALID_TEMP_C = 43.0
    CURE_DAYS = 3                    # consecutive fever-free days to be cured
    EXPECTED_MORTALITY = 0.15        # benchmark (85% success)
    MIN_CASES_FOR_STATS = 20         # below this, show "small sample" caution

    # Demo mode adds a "simulated date" bar (advance day / reset data)
    DEMO_MODE = os.environ.get("DEMO_MODE", "1") == "1"
