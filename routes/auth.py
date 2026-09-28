from functools import wraps

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from werkzeug.security import check_password_hash


auth_bp = Blueprint("auth", __name__)


def login_required(view):

    @wraps(view)
    def wrapped(*args, **kwargs):

        if not session.get("admin_authenticated"):

            return redirect(
                url_for(
                    "auth.login",
                    next=request.path
                )
            )

        return view(*args, **kwargs)

    return wrapped


@auth_bp.route("/login", methods=["GET", "POST"])
def login():

    if session.get("admin_authenticated"):

        return redirect(
            url_for("admin.dashboard")
        )


    if request.method == "POST":

        username = (
            request.form.get("username") or ""
        ).strip()

        password = (
            request.form.get("password") or ""
        )


        expected_user = current_app.config.get(
            "PULSEWATCH_USERNAME",
            ""
        )

        password_hash = current_app.config.get(
            "PULSEWATCH_PASSWORD_HASH",
            ""
        )


        if username == expected_user and password_hash:

            try:

                if check_password_hash(
                    password_hash,
                    password
                ):

                    session.clear()

                    session["admin_authenticated"] = True

                    session["admin_username"] = username

                    session.permanent = True


                    next_url = (
                        request.args.get("next")
                        or url_for("admin.dashboard")
                    )


                    if (
                        not next_url.startswith("/")
                        or next_url.startswith("//")
                    ):

                        next_url = url_for(
                            "admin.dashboard"
                        )


                    return redirect(next_url)


            except (ValueError, TypeError):

                pass


        flash(
            "Invalid username or password.",
            "error"
        )


    return render_template("login.html")


@auth_bp.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("public.landing")
    )