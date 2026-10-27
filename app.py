
import os
from datetime import datetime, timezone

from flask import Flask, jsonify, request, render_template
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import SQLAlchemyError


db = SQLAlchemy()

ALLOWED_STATUSES = {
    "queued",
    "running",
    "success",
    "failed",
}


class Deployment(db.Model):
    __tablename__ = "deployments"

    id = db.Column(db.Integer, primary_key=True)
    project_name = db.Column(db.String(100), nullable=False)
    version = db.Column(db.String(100), nullable=False)
    status = db.Column(
        db.String(30),
        nullable=False,
        default="queued",
    )
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


def deployment_to_dict(item):
    return {
        "id": item.id,
        "project_name": item.project_name,
        "version": item.version,
        "status": item.status,
        "created_at": (
            item.created_at.isoformat()
            if item.created_at
            else None
        ),
    }


def create_app(test_config=None):
    app = Flask(__name__)

    app.config.update(
        SECRET_KEY=os.getenv(
            "SECRET_KEY",
            "local-development-only-change-before-production",
        ),
        SQLALCHEMY_DATABASE_URI=os.getenv(
            "DATABASE_URL",
            "sqlite:///devops_platform.db",
        ),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )

    if test_config:
        app.config.update(test_config)

    db.init_app(app)
    @app.get("/")
    def home():
        return render_template("dashboard.html")

    @app.get("/health")
    def health():
        return jsonify(status="healthy"), 200

    @app.post("/api/deployments")
    def create_deployment():
        data = request.get_json(silent=True)

        if not isinstance(data, dict):
            return jsonify(error="Send a valid JSON object"), 400

        project_name = data.get("project_name")
        version = data.get("version")

        if not isinstance(project_name, str) or not project_name.strip():
            return jsonify(error="project_name is required"), 400

        if not isinstance(version, str) or not version.strip():
            return jsonify(error="version is required"), 400

        project_name = project_name.strip()
        version = version.strip()

        if len(project_name) > 100 or len(version) > 100:
            return jsonify(
                error="Input must be 100 characters or fewer"
            ), 400

        deployment = Deployment(
            project_name=project_name,
            version=version,
            status="queued",
        )

        try:
            db.session.add(deployment)
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception("Failed to save deployment")
            return jsonify(error="Could not save deployment"), 500

        return jsonify(deployment_to_dict(deployment)), 201

    @app.get("/api/deployments")
    def list_deployments():
        try:
            page = request.args.get("page", default=1, type=int)
            per_page = request.args.get("per_page", default=10, type=int)
            status = request.args.get("status", type=str)

            if page is None or page < 1:
                return jsonify(error="page must be at least 1"), 400

            if per_page is None or not 1 <= per_page <= 100:
                return jsonify(
                    error="per_page must be between 1 and 100"
                ), 400

            query = db.select(Deployment)

            if status:
                if status not in ALLOWED_STATUSES:
                    return jsonify(error="Invalid status"), 400
                query = query.where(Deployment.status == status)

            total = db.session.scalar(
                db.select(db.func.count()).select_from(query.subquery())
            )

            items = db.session.execute(
                query.order_by(Deployment.id.desc())
                .offset((page - 1) * per_page)
                .limit(per_page)
            ).scalars().all()

            return jsonify(
                items=[deployment_to_dict(item) for item in items],
                page=page,
                per_page=per_page,
                total=total,
            ), 200

        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception("Failed to list deployments")
            return jsonify(error="Could not fetch deployments"), 500

    @app.get("/api/deployments/<int:deployment_id>")
    def get_deployment(deployment_id):
        item = db.session.get(Deployment, deployment_id)

        if item is None:
            return jsonify(error="Deployment not found"), 404

        return jsonify(deployment_to_dict(item)), 200

    @app.patch("/api/deployments/<int:deployment_id>")
    def update_deployment(deployment_id):
        item = db.session.get(Deployment, deployment_id)

        if item is None:
            return jsonify(error="Deployment not found"), 404

        data = request.get_json(silent=True)

        if not isinstance(data, dict):
            return jsonify(error="Send a valid JSON object"), 400

        if not data:
            return jsonify(error="Provide at least one field"), 400

        allowed_fields = {"project_name", "version", "status"}
        unknown_fields = set(data) - allowed_fields

        if unknown_fields:
            return jsonify(
                error="Unsupported fields: " + ", ".join(sorted(unknown_fields))
            ), 400

        if "project_name" in data:
            value = data["project_name"]
            if (
                not isinstance(value, str)
                or not value.strip()
                or len(value.strip()) > 100
            ):
                return jsonify(error="Invalid project_name"), 400
            item.project_name = value.strip()

        if "version" in data:
            value = data["version"]
            if (
                not isinstance(value, str)
                or not value.strip()
                or len(value.strip()) > 100
            ):
                return jsonify(error="Invalid version"), 400
            item.version = value.strip()

        if "status" in data:
            value = data["status"]
            if not isinstance(value, str) or value not in ALLOWED_STATUSES:
                return jsonify(
                    error="status must be queued, running, success, or failed"
                ), 400
            item.status = value

        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception("Failed to update deployment")
            return jsonify(error="Could not update deployment"), 500

        return jsonify(deployment_to_dict(item)), 200

    @app.delete("/api/deployments/<int:deployment_id>")
    def delete_deployment(deployment_id):
        item = db.session.get(Deployment, deployment_id)

        if item is None:
            return jsonify(error="Deployment not found"), 404

        try:
            db.session.delete(item)
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception("Failed to delete deployment")
            return jsonify(error="Could not delete deployment"), 500

        return "", 204

    @app.errorhandler(404)
    def not_found(_error):
        return jsonify(error="Resource not found"), 404

    @app.errorhandler(500)
    def internal_error(_error):
        db.session.rollback()
        return jsonify(error="Internal server error"), 500

    return app


app = create_app()


if __name__ == "__main__":
    with app.app_context():
        db.create_all()

    app.run(
        host="127.0.0.1",
        port=int(os.getenv("PORT", "5000")),
        debug=False,
    )
