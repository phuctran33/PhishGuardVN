"""Local Week 6 API. Offline features and existing inference only; never train/fetch URLs."""
from __future__ import annotations

from contextlib import asynccontextmanager
import hashlib
import os
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
import warnings

import joblib
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, StrictStr, field_validator, model_validator
from sklearn.exceptions import InconsistentVersionWarning
from starlette.exceptions import HTTPException
from threadpoolctl import threadpool_limits

from phishguard_vn.features import CANDIDATE_FEATURES
from phishguard_vn.prediction import predict_url
from phishguard_vn.url_parser import SCHEME_RE, parse_url

MAX_URL_LENGTH = 4096


class PredictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: StrictStr = Field(min_length=1, max_length=MAX_URL_LENGTH)

    @field_validator("url")
    @classmethod
    def nonempty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("empty_url")
        return value


class PredictionResponse(BaseModel):
    label: Literal["benign", "phishing"]
    model: str
    score: FiniteFloat
    score_kind: Literal["probability", "decision_function"]
    score_definition: str
    decision_rule: Literal["estimator.predict"]
    protocol: str

    @model_validator(mode="after")
    def probability_range(self):
        if self.score_kind == "probability" and not 0 <= self.score <= 1:
            raise ValueError("invalid_probability")
        return self


class ErrorDetail(BaseModel):
    code: str
    message: str
    reason: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    model_ready: bool
    model: str | None
    feature_set: str | None
    protocol: str | None
    artifact_sha256: str | None
    model_error: str | None


def error(status: int, code: str, message: str, reason: str, headers=None):
    return JSONResponse(status_code=status, content={"error": {
        "code": code, "message": message, "reason": reason}}, headers=headers)


def _adapt_e1_cache(cache: dict) -> dict:
    """Container adapter for an EXISTING fitted H5.1 pipeline, not a Teacher export.

    No estimator clone/fit, weights, feature formula or decision threshold changes.
    The protocol name identifies this adapter, not Phuc's E2 ablation protocol.
    """
    if cache.get("decision_threshold") != 0.5 or cache.get("scope", {}).get("test_evaluated") is not False:
        raise ValueError("Unsupported E1 cache scope/threshold")
    name = cache["selected_model"]
    return {"feature_set": "lexical_12", "feature_names": cache["feature_names"],
            "selected_model": name, "models": {name: cache["pipeline"]},
            "score_kinds": {name: "probability"}, "protocol": "week5_e1_audit"}


def _validate_bundle(bundle: dict, model_name: str | None) -> str:
    if not isinstance(bundle, dict) or not isinstance(bundle.get("protocol"), str) or not bundle["protocol"].strip():
        raise ValueError("Missing bundle metadata")
    if bundle.get("feature_set") == "lexical_12":
        expected = list(CANDIDATE_FEATURES)
    else:
        from phishguard_vn.brand_features import E2_FEATURES, FEATURE_SCHEMA_VERSION, load_reference
        if bundle.get("feature_set") != FEATURE_SCHEMA_VERSION:
            raise ValueError("Unsupported feature version")
        reference = bundle.get("brand_reference")
        if (reference is None or not reference.is_fully_verified
                or reference.sha256 != load_reference().sha256):
            raise ValueError("E2 reference differs from current verified reference")
        for filename in ("features.py", "url_parser.py", "brand_features.py"):
            source = (Path(__file__).parent / filename).read_bytes().replace(b"\r\n", b"\n")
            if hashlib.sha256(source).hexdigest() != bundle.get("extractor_source_sha256", {}).get(filename):
                raise ValueError("E2 extractor source changed")
        expected = list(E2_FEATURES)
    if bundle.get("feature_names") != expected:
        raise ValueError("Feature order differs from contract")
    name = model_name if model_name is not None else bundle["selected_model"]
    model = bundle["models"][name]
    if list(model.classes_) != [0, 1] or model.n_features_in_ != len(expected):
        raise ValueError("Model class/schema mismatch")
    if hasattr(model, "feature_names_in_") and list(model.feature_names_in_) != expected:
        raise ValueError("Fitted model feature order mismatch")
    kind = bundle["score_kinds"][name]
    if kind not in {"probability", "decision_function"}:
        raise ValueError("Unsupported score kind")
    if not callable(getattr(model, "predict_proba" if kind == "probability" else "decision_function", None)):
        raise ValueError("Model lacks its declared scoring method")
    return name


def _load(app: FastAPI, bundle_path, bundle_format, model_name, expected_sha256):
    app.state.bundle = None
    app.state.model_name = None
    app.state.artifact_sha256 = None
    app.state.model_error = "not_configured"
    if not bundle_path:
        return
    path = Path(bundle_path)
    if not path.is_file():
        app.state.model_error = "artifact_missing"
        return
    try:
        # Hash and load the same opened file. This is a trusted local admin artifact,
        # never a filename/URL supplied by an API caller.
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
            if expected_sha256 and digest != expected_sha256.lower():
                app.state.model_error = "artifact_incompatible"
                return
            stream.seek(0)
            with warnings.catch_warnings():
                warnings.simplefilter("error", InconsistentVersionWarning)
                bundle = joblib.load(stream)
    except Exception:
        app.state.model_error = "artifact_load_failed"
        return
    try:
        if bundle_format == "week5_e1_audit":
            bundle = _adapt_e1_cache(bundle)
        elif bundle_format != "v2":
            raise ValueError("Unsupported bundle format")
        name = _validate_bundle(bundle, model_name)
        with threadpool_limits(limits=1):
            PredictionResponse.model_validate(predict_url("https://example.com", bundle, name))
    except Exception:
        app.state.model_error = "artifact_incompatible"
        return
    app.state.bundle = bundle
    app.state.model_name = name
    app.state.artifact_sha256 = digest
    app.state.model_error = None


def create_app(*, bundle_path: str | Path | None = None, bundle_format: str = "v2",
               model_name: str | None = None, expected_sha256: str | None = None,
               cors_origins: tuple[str, ...] | list[str] = ()) -> FastAPI:
    """Explicit factory for TestClient; module-level app below reads environment."""
    origins = [origin.strip().rstrip("/") for origin in cors_origins if origin.strip()]
    for origin in origins:
        parts = urlsplit(origin)
        if (parts.scheme not in {"http", "https"} or not parts.hostname or parts.path
                or parts.query or parts.fragment or parts.username or "*" in origin):
            raise ValueError("CORS requires explicit HTTP(S) origins without paths/wildcards")

    @asynccontextmanager
    async def lifespan(app):
        _load(app, bundle_path, bundle_format, model_name, expected_sha256)
        yield
        app.state.bundle = None

    app = FastAPI(title="PhishGuardVN API", version="1.0.0", lifespan=lifespan,
                  description="Offline URL classification; benign is not a safety guarantee.")

    @app.middleware("http")
    async def safe_exception_boundary(request, call_next):
        try:
            return await call_next(request)
        except Exception:
            # No exception text, request body or raw URL in logs/responses.
            return error(500, "INTERNAL_ERROR", "Lỗi máy chủ ngoài dự kiến.", "internal_error")

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        reason = "invalid_json" if any(e["type"] == "json_invalid" for e in exc.errors()) else "schema_validation"
        return error(422, "INVALID_REQUEST", "Body phải gồm duy nhất url là chuỗi 1–4096 ký tự, không chỉ khoảng trắng.", reason)

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        codes = {404: ("NOT_FOUND", "Không tìm thấy endpoint.", "not_found"),
                 405: ("METHOD_NOT_ALLOWED", "HTTP method không được hỗ trợ.", "method_not_allowed")}
        return error(exc.status_code, *codes.get(exc.status_code, ("HTTP_ERROR", "Yêu cầu không được hỗ trợ.", "http_error")),
                     headers=exc.headers)

    @app.get("/health", response_model=HealthResponse)
    def health():
        bundle = app.state.bundle
        return {"status": "ok" if bundle is not None else "degraded", "model_ready": bundle is not None,
                "model": app.state.model_name, "feature_set": bundle["feature_set"] if bundle else None,
                "protocol": bundle["protocol"] if bundle else None,
                "artifact_sha256": app.state.artifact_sha256, "model_error": app.state.model_error}

    @app.post("/predict", response_model=PredictionResponse,
              responses={status: {"model": ErrorResponse} for status in (422, 503, 500)})
    def predict(payload: PredictRequest):
        url = payload.url.strip()
        if any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in url):
            return error(422, "INVALID_URL", "URL không hợp lệ hoặc tên miền không được parser hỗ trợ.", "invalid_characters")
        if SCHEME_RE.match(url) and url.partition("://")[0].lower() not in {"http", "https"}:
            return error(422, "INVALID_URL", "URL không hợp lệ hoặc tên miền không được parser hỗ trợ.", "unsupported_scheme")
        parsed = parse_url(url)
        if not parsed.is_valid:
            reason = parsed.error_reason or "parse_error"
            if reason.startswith("parsing_error"):
                reason = "parse_error"
            return error(422, "INVALID_URL", "URL không hợp lệ hoặc tên miền không được parser hỗ trợ.", reason)
        if app.state.bundle is None:
            return error(503, "MODEL_UNAVAILABLE", "Model chưa sẵn sàng. Vui lòng liên hệ người vận hành.", app.state.model_error)
        try:
            with threadpool_limits(limits=1):
                result = predict_url(url, app.state.bundle, app.state.model_name)
            return PredictionResponse.model_validate(result)
        except Exception:
            return error(500, "INFERENCE_FAILED", "Không thể thực hiện suy luận.", "prediction_failed")

    # Outermost middleware also attaches CORS headers to sanitized error responses.
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False,
                       allow_methods=["GET", "POST"], allow_headers=["Content-Type", "Accept"])
    return app


app = create_app(bundle_path=os.getenv("PHISHGUARD_MODEL_BUNDLE"),
                 bundle_format=os.getenv("PHISHGUARD_BUNDLE_FORMAT", "v2"),
                 model_name=os.getenv("PHISHGUARD_MODEL_NAME") or None,
                 expected_sha256=os.getenv("PHISHGUARD_MODEL_SHA256") or None,
                 cors_origins=os.getenv("PHISHGUARD_CORS_ORIGINS", "").split(","))
