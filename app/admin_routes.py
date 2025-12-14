from flask import Blueprint, redirect, render_template, session, url_for


admin = Blueprint("admin", __name__)


@admin.get("/admin")
def portal():
    if not session.get("user_id"):
        return redirect(url_for("auth.login_get"))
    if not session.get("is_admin"):
        return redirect(url_for("main.index"))
    return render_template("admin_portal.html")
