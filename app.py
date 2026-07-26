"""UFC fight predictor. Run with: streamlit run app.py"""
import streamlit as st

from predict import list_fighters, load_artifacts, load_history, predict_winner

st.set_page_config(page_title="UFC Fight Predictor", page_icon="\U0001F94A")
st.title("UFC Fight Predictor")

# Keep the corner picker side by side even below Streamlit's ~640px column-
# stacking breakpoint, and tint each corner red/blue to match the octagon.
st.markdown(
    """
    <style>
    [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; }
    [data-testid="stColumn"] { flex: 1 1 0% !important; min-width: 0 !important; }
    [data-testid="stColumn"]:nth-of-type(1) [data-baseweb="select"] > div {
        border-color: #e10600 !important;
    }
    [data-testid="stColumn"]:nth-of-type(2) [data-baseweb="select"] > div {
        border-color: #ffd60a !important;
    }
    [data-testid="stColumn"]:nth-of-type(3) [data-baseweb="select"] > div {
        border-color: #0072ce !important;
    }
    [data-testid="stColumn"]:nth-of-type(1) label p { color: #e10600 !important; font-weight: 700; }
    [data-testid="stColumn"]:nth-of-type(2) label p {
        color: #ffd60a !important; font-weight: 700; text-align: center; display: block;
    }
    [data-testid="stColumn"]:nth-of-type(3) label p { color: #0072ce !important; font-weight: 700; }
    [data-testid="stColumn"]:nth-of-type(2) [data-baseweb="select"] { text-align: center; }
    </style>
    """,
    unsafe_allow_html=True,
)

artifacts = load_artifacts()
history = load_history()
fighters = list_fighters(history)

# Fight-card layout: red corner, weight class, blue corner.
red_col, weight_col, blue_col = st.columns(3)
with red_col:
    red = st.selectbox("\U0001F534 Red corner", fighters, index=None, placeholder="Select fighter")
with weight_col:
    weight_classes = artifacts["dtypes"]["weight_class"].categories.tolist()
    weight_class = st.selectbox(
        "\U0001F3C6 Weight class", weight_classes, index=None, placeholder="Select weight class"
    )
with blue_col:
    # Same-fighter constraint enforced by excluding red from blue's options,
    # rather than validating after the fact.
    blue_options = [f for f in fighters if f != red]
    blue = st.selectbox("\U0001F535 Blue corner", blue_options, index=None, placeholder="Select fighter")
title_fight = st.checkbox("Title fight")
total_round_number = st.radio("Rounds", [3, 5], horizontal=True)

if st.button("Predict", type="primary"):
    if not red or not blue or not weight_class:
        st.warning("Pick both fighters and a weight class first.")
    else:
        try:
            winner, proba = predict_winner(
                red, blue, weight_class, title_fight, total_round_number,
                history, artifacts,
            )
            confidence = proba if winner == red else 1 - proba
            st.success(f"**{winner}** wins")
            st.metric(f"Confidence ({winner})", f"{confidence:.1%}")
            st.caption(
                "Calibrated via Platt scaling on pooled walk-forward CV "
                "predictions — tracks real win frequency, not just ranking."
            )
        except ValueError as e:
            st.error(str(e))
