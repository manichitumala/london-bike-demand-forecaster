"""Train LightGBM demand models, compare against a seasonal-naive baseline
using time-based validation, and write an MAE report (overall + by segment).

Usage: python -m bikeforecast.models.train
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import lightgbm as lgb
import pandas as pd
from sklearn.metrics import mean_absolute_error

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from bikeforecast.config import ROOT
from bikeforecast.models.dataset import (
    attach_profile,
    build_seasonal_profile,
    feature_cols,
    load_features,
)

MODELS_DIR = ROOT / "data" / "processed" / "models"
REPORTS_DIR = ROOT / "reports"
TEST_WINDOW_HOURS = 14 * 24  # last 2 weeks of actual data held out


def time_based_split(actual: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    cutoff = actual["hour_ts"].max() - pd.Timedelta(hours=TEST_WINDOW_HOURS)
    train = actual[actual["hour_ts"] <= cutoff].copy()
    test = actual[actual["hour_ts"] > cutoff].copy()
    return train, test


def mae_by_segment(test: pd.DataFrame, y_true_col: str, pred_cols: dict[str, str]) -> dict:
    segments = {
        "overall": pd.Series(True, index=test.index),
        "rain_hours": test["rain"] > 0.1,
        "dry_hours": test["rain"] <= 0.1,
        "weekday": test["is_weekend"] == 0,
        "weekend": test["is_weekend"] == 1,
        "bank_holiday": test["is_bank_holiday"] == 1,
        "morning_peak_7_9": test["hour_of_day"].between(7, 9),
        "evening_peak_17_19": test["hour_of_day"].between(17, 19),
        "overnight_0_5": test["hour_of_day"].between(0, 5),
    }
    out = {}
    for name, mask in segments.items():
        if mask.sum() == 0:
            continue
        sub = test[mask]
        out[name] = {
            "n_rows": int(mask.sum()),
            **{
                model_name: round(mean_absolute_error(sub[y_true_col], sub[pred_col]), 4)
                for model_name, pred_col in pred_cols.items()
            },
        }
    return out


def train_one_target(actual: pd.DataFrame, target: str) -> dict:
    lag_col = "lag_168h_departures" if target == "departures" else "lag_168h_arrivals"
    usable = actual.dropna(subset=[lag_col]).copy()

    train, test = time_based_split(usable)

    profile = build_seasonal_profile(train, target)
    train = attach_profile(train, profile, target)
    test = attach_profile(test, profile, target)

    cols = feature_cols(target)
    cat_cols = ["station_id"]

    model = lgb.LGBMRegressor(
        objective="regression",
        metric="mae",
        n_estimators=400,
        learning_rate=0.05,
        num_leaves=63,
        min_child_samples=30,
        random_state=42,
        verbosity=-1,
    )
    model.fit(
        train[cols],
        train[target],
        categorical_feature=cat_cols,
    )

    test = test.copy()
    test["pred_lgbm"] = model.predict(test[cols]).clip(min=0)
    test["pred_baseline"] = test[lag_col]  # seasonal-naive: same hour, 7 days ago

    report = mae_by_segment(
        test, target, {"seasonal_naive_mae": "pred_baseline", "lightgbm_mae": "pred_lgbm"}
    )

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    model.booster_.save_model(str(MODELS_DIR / f"lgbm_{target}.txt"))
    profile.to_parquet(MODELS_DIR / f"profile_{target}.parquet", index=False)

    return {
        "target": target,
        "train_rows": len(train),
        "test_rows": len(test),
        "test_period": [str(test["hour_ts"].min()), str(test["hour_ts"].max())],
        "mae_by_segment": report,
        "feature_importance": dict(
            sorted(
                zip(cols, model.feature_importances_.tolist()),
                key=lambda kv: kv[1],
                reverse=True,
            )
        ),
    }


def main() -> None:
    df = load_features()
    actual = df[df["is_actual"]].copy()

    results = [train_one_target(actual, target) for target in ("departures", "arrivals")]

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / "evaluation.json"
    report_path.write_text(json.dumps(results, indent=2), encoding="utf-8")

    for r in results:
        print(f"\n=== {r['target']} ({r['train_rows']} train / {r['test_rows']} test rows) ===")
        print(f"test period: {r['test_period'][0]} .. {r['test_period'][1]}")
        overall = r["mae_by_segment"]["overall"]
        print(f"  seasonal-naive MAE: {overall['seasonal_naive_mae']}")
        print(f"  lightgbm MAE:       {overall['lightgbm_mae']}")
    print(f"\nFull report -> {report_path}")


if __name__ == "__main__":
    main()
