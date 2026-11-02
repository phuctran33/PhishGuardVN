"""Dự đoán cho notebook/web: URL -> feature đúng thứ tự -> model đã học.

Không train, không thay threshold, không truy cập website.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from phishguard_vn.features import extract_features


def predict_url(url: str, bundle: dict, model_name: str | None = None) -> dict:
    """Dùng bundle v2; SVM trả margin, các model còn lại trả probability."""
    if bundle["feature_set"] != "lexical_12":
        raise ValueError("Cần nối extractor brand đúng phiên bản trước khi predict schema mới.")
    feature_values = extract_features(url)
    names = bundle["feature_names"]
    if len(names) != len(set(names)) or set(names) != set(feature_values):
        raise ValueError("Feature schema trong bundle không khớp extractor.")
    if any(value is None for value in feature_values.values()):
        raise ValueError("URL không hợp lệ theo parser của nhóm.")
    X = pd.DataFrame([[feature_values[name] for name in names]], columns=names)
    if not np.isfinite(X.to_numpy(float)).all():
        raise ValueError("Feature phải là số hữu hạn.")

    name = model_name or bundle["selected_model"]
    if name not in bundle["models"]:
        raise ValueError(f"Không có model {name!r} trong bundle.")
    model = bundle["models"][name]
    predicted = int(model.predict(X)[0])
    score_kind = bundle["score_kinds"][name]
    if score_kind == "decision_function":
        score = float(model.decision_function(X)[0])
        definition = "SVM margin; không phải xác suất, ranh giới mặc định là 0"
    elif score_kind == "probability":
        score = float(model.predict_proba(X)[0, list(model.classes_).index(1)])
        definition = "predict_proba cho phishing; chưa hiệu chuẩn nguy cơ thực tế"
    else:
        raise ValueError(f"Loại score chưa hỗ trợ: {score_kind}")
    if not np.isfinite(score):
        raise ValueError("Model trả score không hữu hạn.")
    return {"model": name, "label": "phishing" if predicted else "benign", "score": score,
            "score_kind": score_kind, "score_definition": definition,
            "decision_rule": "estimator.predict", "protocol": bundle["protocol"]}
