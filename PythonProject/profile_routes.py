"""Profile page routes for all signed-in PyPondo roles."""

from flask import Blueprint, Response, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required


MAX_PROFILE_IMAGE_BYTES = 2 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


def detect_image_type(data):
    """Return a supported MIME type only when the file signature matches."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def create_profile_blueprint(db, user_model):
    """Create profile endpoints without coupling their logic to app.py."""
    profile = Blueprint("profile", __name__)

    @profile.route("/profile", methods=["GET", "POST"])
    @login_required
    def profile_page():
        if request.method == "POST":
            action = request.form.get("action", "upload_picture")

            if action == "change_password":
                current_password = request.form.get("current_password", "")
                new_password = request.form.get("new_password", "")
                confirm_password = request.form.get("confirm_password", "")

                if not current_user.check_password(current_password):
                    flash("Your current password is incorrect.", "error")
                elif len(new_password) < 8:
                    flash("Your new password must be at least 8 characters.", "error")
                elif new_password != confirm_password:
                    flash("The new passwords do not match.", "error")
                elif new_password == current_password:
                    flash("Choose a password different from your current one.", "error")
                else:
                    current_user.set_password(new_password)
                    db.session.commit()
                    flash("Your password has been changed.", "success")
                return redirect(url_for("profile.profile_page"))

            if action == "remove_picture":
                current_user.profile_picture = None
                current_user.profile_picture_mime = None
                db.session.commit()
                flash("Your profile picture has been removed.", "success")
                return redirect(url_for("profile.profile_page"))

            image = request.files.get("profile_picture")
            if not image or not image.filename:
                flash("Choose a JPG, PNG, or WebP image to upload.", "error")
                return redirect(url_for("profile.profile_page"))

            image_data = image.stream.read(MAX_PROFILE_IMAGE_BYTES + 1)
            if len(image_data) > MAX_PROFILE_IMAGE_BYTES:
                flash("Profile pictures must be 2 MB or smaller.", "error")
                return redirect(url_for("profile.profile_page"))

            image_type = detect_image_type(image_data)
            if image_type not in ALLOWED_IMAGE_TYPES:
                flash("Upload a valid JPG, PNG, or WebP image.", "error")
                return redirect(url_for("profile.profile_page"))

            current_user.profile_picture = image_data
            current_user.profile_picture_mime = image_type
            db.session.commit()
            flash("Your profile picture has been saved.", "success")
            return redirect(url_for("profile.profile_page"))

        role_name = "Administrator" if current_user.is_admin else (current_user.role or "student").replace("_", " ").title()
        return render_template(
            "profile.html",
            profile_user=current_user,
            profile_name=current_user.full_name or current_user.username,
            profile_role=role_name,
        )

    @profile.route("/profile/picture")
    @login_required
    def profile_picture():
        user = db.session.get(user_model, int(current_user.get_id()))
        if not user or not user.profile_picture or user.profile_picture_mime not in ALLOWED_IMAGE_TYPES:
            abort(404)
        response = Response(user.profile_picture, mimetype=user.profile_picture_mime)
        response.headers["Cache-Control"] = "private, max-age=300"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    return profile
