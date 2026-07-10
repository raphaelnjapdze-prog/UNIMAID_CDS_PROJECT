# =========================================================================
# RESISTANCE STATUS PREDICTION ENGINE (utils/resistance_ml_engine.py)
#
# Predicts WHO susceptibility classification (Resistant / Possible
# resistance / Susceptible) from real bioassay_results data — treatment,
# concentration, species, month, and observed mortality outcome. This is
# the one ML target in this app with a fully real, directly measured
# training set: no invented institution data, no placeholder formula.
#
# Will not train or predict below MIN_TRAINING_SAMPLES real replicates.
# Below that threshold, callers get an honest "not enough data" response,
# never a model fit on too few points presented as reliable.
# =========================================================================
import json
import os
from datetime import datetime

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

from utils.data_manager import classify_resistance_status, compute_mortality_percentage, load_bioassay_results

MODEL_DIR = "models"
MODEL_FILE = os.path.join(MODEL_DIR, "resistance_status_model.pkl")
ENCODERS_FILE = os.path.join(MODEL_DIR, "resistance_status_encoders.pkl")
METRICS_FILE = os.path.join(MODEL_DIR, "resistance_model_metrics.json")

CATEGORICAL_FEATURES = ["treatment_name", "species_tested"]
NUMERIC_FEATURES = ["concentration_pct", "collection_month"]

MIN_TRAINING_SAMPLES = 30  # real bioassay replicates required before training is attempted


def _prepare_training_frame() -> pd.DataFrame:
    """
    Builds the real training frame from bioassay_results. Excludes control
    replicates — resistance status is a property of the treatment being
    tested, not the untreated control, and mixing them would train the
    model to partly just detect is_control rather than real resistance.
    """
    df = load_bioassay_results()
    if df.empty:
        return pd.DataFrame()

    df = df[df["is_control"] == False].copy()  # noqa: E712 - explicit False match; is_control may load as nullable/object
    if df.empty:
        return pd.DataFrame()

    df["assay_date"] = pd.to_datetime(df["assay_date"], errors="coerce")
    df = df.dropna(subset=["assay_date", "mosquitoes_exposed", "mortality_24hr"])
    df = df[df["mosquitoes_exposed"] > 0]
    if df.empty:
        return pd.DataFrame()

    df["collection_month"] = df["assay_date"].dt.month
    df["mortality_pct"] = df.apply(
        lambda r: compute_mortality_percentage(r["mortality_24hr"], r["mosquitoes_exposed"]), axis=1
    )
    df["resistance_status"] = df["mortality_pct"].apply(classify_resistance_status)
    df["species_tested"] = df["species_tested"].fillna("Unspecified")

    return df


def check_training_readiness() -> dict:
    """
    Returns whether enough real data exists to train, without training.
    Used by the UI to show an honest status before any model action.
    """
    df = _prepare_training_frame()
    n = len(df)
    return {
        "ready": n >= MIN_TRAINING_SAMPLES,
        "real_samples": n,
        "required_samples": MIN_TRAINING_SAMPLES,
        "class_distribution": df["resistance_status"].value_counts().to_dict() if n > 0 else {},
    }


def train_resistance_model() -> dict:
    """
    Trains a Random Forest classifier on real bioassay_results data only.
    Refuses to train below MIN_TRAINING_SAMPLES — returns an honest status
    dict instead of a fabricated or premature model.
    """
    df = _prepare_training_frame()
    n = len(df)

    if n < MIN_TRAINING_SAMPLES:
        return {
            "trained": False,
            "reason": (
                f"Only {n} real, non-control bioassay replicate(s) on file — "
                f"need at least {MIN_TRAINING_SAMPLES} before training a model. "
                "Log more results via Bioassay Result Entry."
            ),
            "real_samples": n,
        }

    if df["resistance_status"].nunique() < 2:
        return {
            "trained": False,
            "reason": (
                "All real replicates on file show the same resistance outcome — "
                "at least two different outcome classes are needed to train a "
                "meaningful classifier."
            ),
            "real_samples": n,
        }

    os.makedirs(MODEL_DIR, exist_ok=True)

    encoders = {}
    processed = df.copy()
    for feature in CATEGORICAL_FEATURES:
        le = LabelEncoder()
        values = list(df[feature].astype(str).unique()) + ["Unknown"]
        le.fit(values)
        processed[feature] = le.transform(df[feature].astype(str))
        encoders[feature] = le

    feature_cols = CATEGORICAL_FEATURES + NUMERIC_FEATURES
    X = processed[feature_cols]
    y = processed["resistance_status"]

    stratify = y if y.value_counts().min() >= 2 else None
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=stratify
    )

    model = RandomForestClassifier(n_estimators=150, max_depth=8, random_state=42, class_weight="balanced")
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)
    report = classification_report(y_test, y_pred, output_dict=True, zero_division=0)

    joblib.dump(model, MODEL_FILE)
    joblib.dump(encoders, ENCODERS_FILE)

    metrics = {
        "trained_on_real_samples": int(n),
        "test_set_size": int(len(X_test)),
        "accuracy": float(accuracy),
        "classification_report": report,
        "class_distribution": y.value_counts().to_dict(),
        "training_timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(METRICS_FILE, "w") as f:
        json.dump(metrics, f, indent=2)

    return {"trained": True, "reason": "", "real_samples": n, "metrics": metrics}


def get_last_training_metrics() -> dict | None:
    if not os.path.exists(METRICS_FILE):
        return None
    with open(METRICS_FILE, "r") as f:
        return json.load(f)


def predict_resistance_status(treatment_name: str, concentration_pct: float, species_tested: str, month: int) -> dict:
    """
    Predicts resistance status from real inputs, using a model trained
    only on real data. Refuses to predict if no model has been trained
    yet, or if the current real dataset no longer meets the training
    threshold (e.g. right after a fresh deployment with no data yet).
    """
    readiness = check_training_readiness()
    if not readiness["ready"]:
        return {
            "available": False,
            "reason": (
                f"Model not available — only {readiness['real_samples']} real "
                f"replicate(s) on file, need {readiness['required_samples']}."
            ),
        }

    if not (os.path.exists(MODEL_FILE) and os.path.exists(ENCODERS_FILE)):
        train_result = train_resistance_model()
        if not train_result["trained"]:
            return {"available": False, "reason": train_result["reason"]}

    model = joblib.load(MODEL_FILE)
    encoders = joblib.load(ENCODERS_FILE)

    processed = {}
    for feature, raw_value in [("treatment_name", treatment_name), ("species_tested", species_tested or "Unspecified")]:
        le = encoders[feature]
        val = str(raw_value)
        if val not in le.classes_:
            val = "Unknown"
        processed[feature] = le.transform([val])[0]

    processed["concentration_pct"] = float(concentration_pct)
    processed["collection_month"] = int(month)

    feature_cols = CATEGORICAL_FEATURES + NUMERIC_FEATURES
    feature_vector = pd.DataFrame([processed])[feature_cols]

    predicted_class = model.predict(feature_vector)[0]
    class_probabilities = dict(zip(model.classes_, model.predict_proba(feature_vector)[0]))

    metrics = get_last_training_metrics()

    return {
        "available": True,
        "predicted_status": predicted_class,
        "class_probabilities": {k: round(float(v), 3) for k, v in class_probabilities.items()},
        "model_trained_on_samples": metrics["trained_on_real_samples"] if metrics else None,
        "model_test_accuracy": metrics["accuracy"] if metrics else None,
    }
