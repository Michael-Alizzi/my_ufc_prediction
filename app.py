"""UFC fight predictor. Run with: streamlit run app.py"""
import streamlit as st

from predict import list_fighters, load_artifacts, load_history, predict_winner

st.set_page_config(page_title="UFC Fight Predictor", page_icon="\U0001F94A")
st.title("UFC Fight Predictor")

artifacts = load_artifacts()
history = load_history()
fighters = list_fighters(history)

red_col, blue_col = st.columns(2)
with red_col:
    red = st.selectbox("Red corner", fighters, index=0)
with blue_col:
    # Same-fighter constraint enforced by excluding red from blue's options,
    # rather than validating after the fact.
    blue_options = [f for f in fighters if f != red]
    blue = st.selectbox("Blue corner", blue_options, index=0)

weight_classes = artifacts["dtypes"]["weight_class"].categories.tolist()
weight_class = st.selectbox("Weight class", weight_classes)
title_fight = st.checkbox("Title fight")
total_round_number = st.radio("Rounds", [3, 5], horizontal=True)

if st.button("Predict", type="primary"):
    try:
        winner, proba = predict_winner(
            red, blue, weight_class, title_fight, total_round_number,
            history, artifacts,
        )
        confidence = proba if winner == red else 1 - proba
        st.success(f"**{winner}** wins")
        st.metric(f"Confidence ({winner})", f"{confidence:.1%}")
        st.caption(
            "Raw ensemble probability, not calibrated — treat as a ranking "
            "signal, not a literal win frequency."
        )
    except ValueError as e:
        st.error(str(e))
