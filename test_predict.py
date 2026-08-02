"""Self-check for predict.py. Run: .venv/bin/python test_predict.py
Requires ensemble.joblib and fighter_history.parquet (produced by the
notebook's "Export for Streamlit App" cell).
"""
from predict import kelly_edge, load_artifacts, load_history, predict_winner

SYMMETRY_TOLERANCE = 0.05


def demo():
    # Money path: edge only when model probability beats implied probability.
    assert abs(kelly_edge(0.6, 2.0) - 0.2) < 1e-9   # p*o-1 = 0.2, /(o-1) = 0.2
    assert kelly_edge(0.5, 2.0) == 0.0               # fair price, no bet
    assert kelly_edge(0.4, 2.0) == 0.0               # negative edge, no bet
    print("OK: kelly_edge")

    artifacts = load_artifacts()
    history = load_history()

    a, b = "Ilia Topuria", "Justin Gaethje"
    winner, proba = predict_winner(a, b, "Lightweight", True, 5, history, artifacts,
                                   event_country="USA")
    assert winner in (a, b)
    assert 0.0 <= proba <= 1.0
    print(f"{a} vs {b} -> {winner} ({proba:.1%} {a} wins)")

    # mirror_fights augmentation trains the model to be corner-agnostic, so
    # swapping who's red/blue should roughly invert the red-win probability.
    _, proba_swapped = predict_winner(b, a, "Lightweight", True, 5, history, artifacts)
    drift = abs(proba - (1 - proba_swapped))
    assert drift < SYMMETRY_TOLERANCE, (
        f"corner swap should roughly invert probability: "
        f"{proba:.3f} vs {1 - proba_swapped:.3f} (drift {drift:.3f})"
    )
    print(f"OK: corner-swap drift {drift:.3f} < {SYMMETRY_TOLERANCE}")


if __name__ == "__main__":
    demo()
