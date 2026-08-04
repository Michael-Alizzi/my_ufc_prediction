#!/usr/bin/env python3
"""Experiment-run helpers for scripts/run_experiments.sh.

log mode -- extract the key printed lines from an EXECUTED notebook and
append a draft entry to EXPERIMENTS.md (verbatim lines, no fragile numeric
parsing). Prints PARSED_WINDOW=tr,te when the run's chosen window is found,
so the shell can pin it for the next run.

    python scripts/log_run_metrics.py log ufc_prediction_claude.ipynb "1. Baseline v2"

pin mode -- set BEST_WINDOW = (tr, te) in the window-search cell:

    python scripts/log_run_metrics.py pin ufc_prediction_claude.ipynb 72 6
"""
import json
import re
import subprocess
import sys
from datetime import date

INTERESTING = re.compile(
    r"^(XGBoost device:|Best window:|Training period:|Window pinned|"
    r"Shared study|Postgres unreachable|OPTUNA_STORAGE_URL not set|"
    r"Laptop eGPU joined|Laptop unreachable|Worker storage env vars|"
    r"diff_pairs verified|Pooled OOF for export:|"
    r"Pooled test accuracy:|95% CI|Batch accuracy:|"
    r"No ensemble_baseline|Baseline accuracy:|This run accuracy:|"
    r"New fixes|New breaks|Test-set McNemar|McNemar p-value|"
    r"Pooled-OOF comparison|OOF fixes|Statistically significant|"
    r"No statistically significant|Validation: \d|Test: {7}\d|"
    r"Dropped \d+ (duplicate|med_)|Prediction: |Confidence: )"
)
WINDOW_RE = re.compile(r"Best window:\s*(\d+) months train / (\d+) months test")
PINNED_RE = re.compile(r"Window pinned at \((\d+), (\d+)\)")


def notebook_output_lines(path):
    nb = json.load(open(path))
    for cell in nb["cells"]:
        for out in cell.get("outputs", []):
            text = out.get("text") or out.get("data", {}).get("text/plain") or []
            if isinstance(text, str):
                text = text.splitlines(keepends=True)
            for line in text:
                yield line.rstrip("\n")


def log(nb_path, title):
    lines = [l for l in notebook_output_lines(nb_path) if INTERESTING.match(l)]
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                         capture_output=True, text=True).stdout.strip()
    entry = (
        f"\n---\n\n### {title}        {date.today().isoformat()}, notebook at {sha}\n"
        "Auto-logged from the executed notebook's output cells:\n\n```\n"
        + "\n".join(lines) +
        "\n```\n\n$100 replay (last event): (fill in from weekly-predictions-log)\n"
        "Decision: (ACCEPT / REVERT -- primary gate is the pooled-OOF McNemar line)\n"
    )
    with open("EXPERIMENTS.md", "a") as fh:
        fh.write(entry)
    print(f"logged {len(lines)} metric lines to EXPERIMENTS.md under {title!r}")

    joined = "\n".join(lines)
    m = WINDOW_RE.search(joined) or PINNED_RE.search(joined)
    if m:
        print(f"PARSED_WINDOW={m.group(1)},{m.group(2)}")


def pin(nb_path, tr, te):
    nb = json.load(open(nb_path))
    target = "BEST_WINDOW = None"
    for cell in nb["cells"]:
        src = "".join(cell["source"])
        if cell["cell_type"] == "code" and target in src:
            src = src.replace(target, f"BEST_WINDOW = ({tr}, {te})")
            cell["source"] = src.splitlines(keepends=True)
            json.dump(nb, open(nb_path, "w"), indent=1, ensure_ascii=False)
            open(nb_path, "a").write("\n")
            print(f"pinned BEST_WINDOW = ({tr}, {te})")
            return
    print("BEST_WINDOW already pinned or cell not found -- nothing changed")


if __name__ == "__main__":
    if sys.argv[1] == "log":
        log(sys.argv[2], sys.argv[3])
    elif sys.argv[1] == "pin":
        pin(sys.argv[2], int(sys.argv[3]), int(sys.argv[4]))
    else:
        raise SystemExit(__doc__)
