import numpy as np
import os
from pathlib import Path
import pytest
from unittest.mock import Mock

from phishguard_vn.features import extract_features


def pytest_addoption(parser):
    group = parser.getgroup("teacher QA")
    group.addoption(
        "--teacher-root",
        default=os.environ.get("PHISHGUARD_TEACHER_ROOT"),
        help="Checkout backend/Teacher phát hành, chứa configs/teacher_lock.json.",
    )
    group.addoption(
        "--teacher-api",
        action="store_true",
        help="Chạy nghiệm thu API với Teacher thật; sẽ fail nếu backend chưa hỗ trợ bundle.",
    )


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--teacher-api"):
        marker = pytest.mark.skip(reason="Bật --teacher-api để nghiệm thu API Teacher; chưa tính là pass.")
        for item in items:
            if "teacher_api" in item.keywords:
                item.add_marker(marker)


@pytest.fixture(scope="session")
def teacher_root(pytestconfig):
    value = pytestconfig.getoption("--teacher-root")
    if not value:
        pytest.skip("Cần --teacher-root hoặc PHISHGUARD_TEACHER_ROOT để kiểm tra artifact thật.")
    root = Path(value).resolve()
    required = (
        "src/phishguard_vn/teacher.py",
        "scripts/predict_teacher.py",
        "configs/teacher_lock.json",
        "requirements-teacher.txt",
    )
    for relative in required:
        if not (root / relative).is_file():
            pytest.fail(f"Teacher checkout thiếu {relative}; kiểm tra --teacher-root.")
    return root


@pytest.fixture
def valid_url_cases():
    """URLs hợp lệ đại diện cho cách viết URL thường gặp và các host biên."""
    return {
        "https_with_path_and_query": "https://example.com/login?next=%2Faccount",
        "host_without_scheme": "example.org/account",
        "unicode_domain": "https://例え.com/ログイン",
        "ipv4_address": "http://192.0.2.1/",
        "ipv6_address": "http://[2001:db8::1]/status",
    }


@pytest.fixture
def sample_url(valid_url_cases):
    return valid_url_cases["https_with_path_and_query"]


@pytest.fixture
def invalid_url_cases():
    """Chuỗi URL không hợp lệ mà parser phải từ chối."""
    return {
        "empty_string": "",
        "invalid_port": "http://example.com:99999/",
        "malformed_ipv6": "http://[2001:db8::1/",
        "whitespace_in_hostname": "https://exa mple.com/",
    }


@pytest.fixture
def missing_url_cases():
    """Giá trị URL bị thiếu hoặc sai kiểu trước khi parser trích feature."""
    return {
        "none": None,
        "integer": 123,
        "list": [],
        "mapping": {},
    }


@pytest.fixture
def mock_model():
    model = Mock(name="mock_estimator")
    model.predict.return_value = np.array([1])
    model.predict_proba.return_value = np.array([[0.05, 0.95]])
    model.classes_ = np.array([0, 1])
    return model


@pytest.fixture
def mock_bundle(sample_url, mock_model):
    feature_values = extract_features(sample_url)

    return {
        "feature_set": "lexical_12",
        "feature_names": list(feature_values.keys()),
        "selected_model": "mock_model",
        "models": {"mock_model": mock_model},
        "score_kinds": {"mock_model": "probability"},
        "protocol": "mock-test-v1",
    }


@pytest.fixture
def mock_prediction_result():
    return {
        "model": "mock_model",
        "label": "phishing",
        "score": 0.95,
        "score_kind": "probability",
        "score_definition": (
            "predict_proba cho phishing; chưa hiệu chuẩn nguy cơ thực tế"
        ),
        "decision_rule": "estimator.predict",
        "protocol": "mock-test-v1",
    }
