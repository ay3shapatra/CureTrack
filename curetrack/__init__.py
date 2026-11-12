"""CureTrack - temperature tracking & discharge management for a quarantine centre."""
from flask import Flask, g, render_template

from .config import Config
from .models import Role, User, db
from .rules import c_to_f, get_today


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    db.init_app(app)

    from . import auth
    from .routes import admin, doctor, main, nurse, reports
    app.before_request(auth.load_user)
    for bp in (auth.bp, main.bp, nurse.bp, doctor.bp, admin.bp, reports.bp):
        app.register_blueprint(bp)

    @app.context_processor
    def inject_globals():
        return {
            "today": get_today(),
            "current_user": g.get("user"),
            "Role": Role,
            "c_to_f": c_to_f,
            "cfg": app.config,
        }

    @app.template_filter("pct")
    def pct(value, digits=1):
        return "—" if value is None else f"{value * 100:.{digits}f}%"

    @app.errorhandler(403)
    def forbidden(_):
        return render_template("errors/error.html", code=403,
                               message="Your role does not have access to this page."), 403

    @app.errorhandler(404)
    def not_found(_):
        return render_template("errors/error.html", code=404, message="Page not found."), 404

    with app.app_context():
        db.create_all()
        if User.query.count() == 0:       # first run -> load demo data
            from .seed import seed_demo_data
            seed_demo_data()

    return app
