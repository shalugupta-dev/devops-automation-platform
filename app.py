
import os
from datetime import datetime, timezone

from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import SQLAlchemyError


db = SQLAlchemy()


# Model ko create_app() ke bahar rakha hai.
# Isse tests ke dauran duplicate table registration nahi hogi.
class Deployment(db.Model):
    __tablename__ = "deployments"

    id = db.Column(db.Integer, primary_key=True)

    project_name = db.Column(
        db.String(100),
        nullable=False,
    )

    version = db.Column(
        db.String(100),
        nullable=False,
    )

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

    # Tests ke liye alag database configuration support.
    if test_config:
        app.config.update(test_config)

    db.init_app(app)

    # Home endpoint
    @app.get("/")
    def home():
        return jsonify(
            project="DevOps Automation & Deployment Platform",
            status="running",
            endpoints=[
                "GET /health",
                "POST /api/deployments",
                "GET /api/deployments",
            ],
        ), 200

    # Health-check endpoint
    @app.get("/health")
    def health():
        return jsonify(status="healthy"), 200

    # Naya deployment record create karna
    @app.post("/api/deployments")
    def create_deployment():
        data = request.get_json(silent=True)

        if not isinstance(data, dict):
            return jsonify(
                error="Send a valid JSON object"
            ), 400

        project_name = data.get("project_name")
        version = data.get("version")

        if not isinstance(project_name, str) or not project_name.strip():
            return jsonify(
                error="project_name is required"
            ), 400

        if not isinstance(version, str) or not version.strip():
            return jsonify(
                error="version is required"
            ), 400

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

            app.logger.exception(
                "Failed to save deployment record"
            )

            return jsonify(
                error="Could not save deployment"
            ), 500

        return jsonify(
            id=deployment.id,
            project_name=deployment.project_name,
            version=deployment.version,
            status=deployment.status,
        ), 201

    # Recent deployment records list karna
    @app.get("/api/deployments")
    def list_deployments():
        try:
            deployments = db.session.execute(
                db.select(Deployment)
                .order_by(Deployment.id.desc())
                .limit(100)
            ).scalars().all()

        except SQLAlchemyError:
            db.session.rollback()

            app.logger.exception(
                "Failed to fetch deployments"
            )

            return jsonify(
                error="Could not fetch deployments"
            ), 500

        return jsonify([
            {
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
            for item in deployments
        ]), 200

    # Unknown URL
    @app.errorhandler(404)
    def not_found(_error):
        return jsonify(
            error="Resource not found"
        ), 404

    # Unexpected server error
    @app.errorhandler(500)
    def internal_error(_error):
        db.session.rollback()

        return jsonify(
            error="Internal server error"
        ), 500

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
