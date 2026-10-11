"""Profile page routes for all signed-in PyPondo roles."""

import hashlib
import logging

from flask import Blueprint, Response, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import SQLAlchemyError


MAX_PROFILE_IMAGE_BYTES = 2 * 1024 * 1024
MAX_PROFILE_UPLOAD_OVERHEAD_BYTES = 64 * 1024
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
logger = logging.getLogger(__name__)


def detect_image_type(data):
    """Return a supported MIME type only when the file signature matches."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def read_profile_image(image):
    """Read and validate one bounded profile image upload."""
    if not image or not image.filename:
        return None, None, "missing"

    image_data = image.stream.read(MAX_PROFILE_IMAGE_BYTES + 1)
    if len(image_data) > MAX_PROFILE_IMAGE_BYTES:
        return None, None, "too_large"

    image_type = detect_image_type(image_data)
    if image_type not in ALLOWED_IMAGE_TYPES:
        return None, None, "invalid_type"
    return image_data, image_type, None


def create_profile_blueprint(db, user_model):
    """Create profile endpoints without coupling their logic to app.py."""
    profile = Blueprint("profile", __name__)

    @profile.app_context_processor
    def inject_profile_picture_version():
        image_data = current_user.profile_picture if current_user.is_authenticated else None
        version = hashlib.sha256(image_data).hexdigest() if image_data else ""
        return {"profile_picture_version": version}

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
            try:
                image_data, image_type, error = read_profile_image(image)
            except OSError as error:
                logger.error(
                    "Profile picture upload could not be read",
                    extra={
                        "user_id": current_user.get_id(),
                        "reason": "read_error",
                        "error_type": type(error).__name__,
                    },
                )
                flash("The uploaded picture could not be read. Please try again.", "error")
                return redirect(url_for("profile.profile_page"))

            if error == "missing":
                logger.warning(
                    "Profile picture upload rejected",
                    extra={"user_id": current_user.get_id(), "reason": error},
                )
                flash("Choose a JPG, PNG, or WebP image to upload.", "error")
                return redirect(url_for("profile.profile_page"))
            if error == "too_large":
                logger.warning(
                    "Profile picture upload rejected",
                    extra={"user_id": current_user.get_id(), "reason": error},
                )
                flash("Profile pictures must be 2 MB or smaller.", "error")
                return redirect(url_for("profile.profile_page"))
            if error == "invalid_type":
                logger.warning(
                    "Profile picture upload rejected",
                    extra={"user_id": current_user.get_id(), "reason": error},
                )
                flash("Upload a valid JPG, PNG, or WebP image.", "error")
                return redirect(url_for("profile.profile_page"))

            current_user.profile_picture = image_data
            current_user.profile_picture_mime = image_type
            try:
                db.session.commit()
            except SQLAlchemyError as error:
                db.session.rollback()
                logger.error(
                    "Profile picture upload could not be saved",
                    extra={
                        "user_id": current_user.get_id(),
                        "reason": "database_error",
                        "error_type": type(error).__name__,
                    },
                )
                flash("The picture could not be saved. Please try again.", "error")
                return redirect(url_for("profile.profile_page"))
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
