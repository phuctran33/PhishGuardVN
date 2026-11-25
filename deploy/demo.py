"""Serve the compiled Web demo and released Teacher on one origin."""
from pathlib import Path

from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from phishguard_vn.api import create_app

ROOT = Path(__file__).resolve().parents[1]
app = create_app(bundle_format="teacher", teacher_root=ROOT)


@app.get("/ready", include_in_schema=False)
def readiness() -> Response:
    return Response(status_code=204 if app.state.teacher is not None else 503)


class DemoStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        # Preserve the API's 404 for unimplemented POST routes.
        if scope["method"] not in {"GET", "HEAD"}:
            raise HTTPException(status_code=404)
        return await super().get_response(path, scope)


app.mount("/", DemoStaticFiles(directory=ROOT / "apps/web/build/web", html=True), name="web")
