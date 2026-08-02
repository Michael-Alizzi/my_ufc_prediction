"""Optuna worker for the shared XGBoost study.

Dispatched to the laptop by the notebook's "Hyperparameter Tuning with
Optuna" cell (which also ships tuning_df_export.parquet, tuning_meta.json
and cell4_helpers.py -- the fold/mirror helpers exported from the live
kernel so this worker can never drift from the notebook's logic):

    OPTUNA_STORAGE_URL=postgresql://... python shared_study_worker.py \
        tuning_df_export.parquet tuning_meta.json STUDY_NAME TRIAL_CAP \
        cuda:1 SEED done_file

It joins the SAME Postgres-backed study as the desktop and adds trials until
the shared COMPLETE-trial cap is reached, then touches done_file (the
notebook polls for it over ssh). The device argument is probed with a tiny
fit and falls back to cpu, so a broken GPU driver degrades to slow trials
instead of dying silently in worker.log while the desktop waits.
"""
import json
import os
import sys

import numpy as np
import optuna
import pandas as pd
from optuna.samplers import TPESampler
from optuna.trial import TrialState

from cell4_helpers import evaluate_cv_predictions, train_test_windows_by_month


def probe_device(device):
    try:
        from xgboost import XGBClassifier
        XGBClassifier(n_estimators=2, tree_method="hist", device=device).fit(
            np.array([[0.0], [1.0], [0.0], [1.0]]), [0, 1, 0, 1]
        )
        return device
    except Exception as e:
        print(f"device {device!r} unusable ({e}); falling back to cpu", flush=True)
        return "cpu"


def main():
    (tuning_path, meta_path, study_name, trial_cap,
     device_arg, seed, done_file) = sys.argv[1:8]
    trial_cap = int(trial_cap)

    tuning_df = pd.read_parquet(tuning_path)
    with open(meta_path) as fh:
        meta = json.load(fh)
    device = probe_device(device_arg)

    study = optuna.load_study(
        study_name=study_name,
        storage=os.environ["OPTUNA_STORAGE_URL"],
        sampler=TPESampler(multivariate=True, n_startup_trials=20, seed=int(seed)),
    )

    def objective(trial):
        # KEEP IN SYNC with the notebook's Optuna cell -- same space, same
        # fixed params, only `device` differs per machine.
        params = {
            "objective": "binary:logistic",
            "eval_metric": "logloss",
            "verbosity": 0,
            "random_state": 42,
            "max_depth": trial.suggest_int("max_depth", 1, 6),
            "learning_rate": trial.suggest_float("learning_rate", 0.002, 0.05, log=True),
            "n_estimators": trial.suggest_int("n_estimators", 400, 1600),
            "min_child_weight": trial.suggest_int("min_child_weight", 1, 50),
            "gamma": trial.suggest_float("gamma", 1e-8, 10, log=True),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
            "reg_alpha": trial.suggest_float("reg_alpha", 1e-8, 10, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-8, 10, log=True),
            "enable_categorical": True,
            "tree_method": "hist",
            "device": device,
        }
        preds = train_test_windows_by_month(
            tuning_df,
            train_months=meta["best_train_months"],
            test_months=meta["best_test_months"],
            model_params=params,
        )
        return evaluate_cv_predictions(preds, verbose=False)["AUC"]

    def stop_when_enough(study, trial):
        n_complete = len([t for t in study.get_trials(deepcopy=False)
                          if t.state == TrialState.COMPLETE])
        if n_complete >= trial_cap:
            study.stop()

    study.optimize(objective, n_trials=None, callbacks=[stop_when_enough])

    with open(done_file, "w") as fh:
        fh.write("done\n")
    print(f"worker finished; study has "
          f"{len([t for t in study.trials if t.state == TrialState.COMPLETE])} "
          f"complete trials", flush=True)


if __name__ == "__main__":
    main()
