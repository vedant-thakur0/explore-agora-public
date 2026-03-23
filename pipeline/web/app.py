"""Flask app for NER annotation and entity dictionary management."""

from __future__ import annotations

from pathlib import Path

from flask import Flask, redirect, render_template, url_for


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).parent / "templates"),
        static_folder=str(Path(__file__).parent / "static"),
    )
    app.secret_key = "agora-ner-annotation-dev"

    # Register blueprints
    from pipeline.web.routes.documents import bp as documents_bp
    from pipeline.web.routes.annotation import bp as annotation_bp
    from pipeline.web.routes.auto_extract import bp as auto_extract_bp
    from pipeline.web.routes.dictionary import bp as dictionary_bp

    app.register_blueprint(documents_bp)
    app.register_blueprint(annotation_bp)
    app.register_blueprint(auto_extract_bp)
    app.register_blueprint(dictionary_bp)

    @app.route("/")
    def index():
        return redirect(url_for("documents.document_list"))

    @app.route("/annotate/<agora_id>")
    def annotate(agora_id: str):
        return render_template("annotate.html", agora_id=agora_id)

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, port=5000)
