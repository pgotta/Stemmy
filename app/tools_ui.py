"""Inject Stemmy's optional musician tools without modifying the main studio template.

Keeping the tuner and chord creator in isolated static files makes the feature easy
to remove or revise and avoids coupling it to the large, carefully tuned studio UI.
"""

from __future__ import annotations

from pathlib import Path

from flask import Flask, Response


_CSS_TAG = (
    '<link rel="stylesheet" href="/static/stemmy-tools.css?v=1" '
    'data-stemmy-tools="css">'
)
_JS_TAG = (
    '<script src="/stemmy-tools.js?v=1" defer '
    'data-stemmy-tools="js"></script>'
)


def install_tools(app: Flask) -> Flask:
    """Attach the tuner/chord-creator UI to HTML responses exactly once."""

    parts_dir = Path(__file__).resolve().parent / "static" / "stemmy-tools"

    @app.get("/stemmy-tools.js")
    def _stemmy_tools_bundle():
        parts = sorted(parts_dir.glob("part-*.js"))
        source = "\n".join(part.read_text(encoding="utf-8") for part in parts)
        return Response(
            source,
            content_type="application/javascript; charset=utf-8",
            headers={"Cache-Control": "no-cache"},
        )

    @app.after_request
    def _inject_musician_tools(response):
        if response.status_code != 200 or response.direct_passthrough:
            return response
        content_type = response.headers.get("Content-Type", "")
        if "text/html" not in content_type:
            return response

        html = response.get_data(as_text=True)
        if 'data-stemmy-tools="js"' in html:
            return response
        if "</head>" not in html or "</body>" not in html:
            return response

        html = html.replace("</head>", f"{_CSS_TAG}</head>", 1)
        html = html.replace("</body>", f"{_JS_TAG}</body>", 1)
        response.set_data(html)
        response.headers["Content-Length"] = str(len(response.get_data()))
        return response

    return app
