"""Login, logout and role-based access control."""
from functools import wraps

from flask import Blueprint, abort, flash, g, redirect, render_template, request, session, url_for

from .models import Role, User, db

bp = Blueprint("auth", __name__)

# Where each role lands after login
HOME_BY_ROLE = {
    Role.NURSE: "nurse.worklist",
    Role.DOCTOR: "doctor.worklist",
    Role.HEAD_DOCTOR: "doctor.worklist",
    Role.ADMIN: "admin.dashboard",
}


def load_user():
    uid = session.get("user_id")
    g.user = db.session.get(User, uid) if uid else None
    if g.user is not None and not g.user.active:
        session.clear()
        g.user = None


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def roles_required(*roles):
    """Allow only the listed roles; everyone else gets 403."""
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if g.user.role not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()
        if user is None or not user.check_password(password) or not user.active:
            flash("Invalid username or password.", "error")
        else:
            session.clear()
            session["user_id"] = user.id
            nxt = request.args.get("next")
            if nxt and nxt.startswith("/") and not nxt.startswith("//"):
                return redirect(nxt)
            return redirect(url_for(HOME_BY_ROLE[user.role]))
    demo_users = User.query.order_by(User.id).all()
    return render_template("login.html", demo_users=demo_users)


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
