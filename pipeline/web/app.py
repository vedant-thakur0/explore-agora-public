"""Flask app for NER annotation and entity dictionary management."""

from __future__ import annotations

import time
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, redirect, render_template, url_for

load_dotenv()


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

    # Inject a cache-busting token (server start time) into every template
    _start_time = str(int(time.time()))

    @app.context_processor
    def inject_cache_bust():
        return {"cache_bust": _start_time}

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
