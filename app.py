"""UFC fight predictor. Run with: streamlit run app.py"""
import streamlit as st

from predict import kelly_edge, list_fighters, load_artifacts, load_history, predict_winner

st.set_page_config(page_title="UFC Fight Predictor", page_icon="\U0001F94A")
st.title("UFC Fight Predictor")

# Keep each row's columns side by side even below Streamlit's ~640px column-
# stacking breakpoint, and tint them fight-card style. Each row lives in its
# own st.container(key=...) -- Streamlit stamps that key as a CSS class
# (st-key-<key>) on the wrapper div, which is what actually scopes these
# rules per-row (nth-of-type on stHorizontalBlock doesn't work: each row's
# block is the *only* child of its own wrapper, so every row is "1st of
# type" and nth-of-type(2) never matches anything).
st.markdown(
    """
    <style>
    [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; }
    [data-testid="stColumn"] { flex: 1 1 0% !important; min-width: 0 !important; }

    /* Row 1: red corner / weight class / blue corner */
    .st-key-corner_row [data-testid="stColumn"]:nth-of-type(1) [data-baseweb="select"] > div {
        border-color: #e63946 !important;
    }
    .st-key-corner_row [data-testid="stColumn"]:nth-of-type(2) [data-baseweb="select"] > div {
        border-color: #f1faee !important;
    }
    .st-key-corner_row [data-testid="stColumn"]:nth-of-type(3) [data-baseweb="select"] > div {
        border-color: #0072ce !important;
    }
    .st-key-corner_row [data-testid="stColumn"]:nth-of-type(1) label p { color: #e63946 !important; font-weight: 700; }
    .st-key-corner_row [data-testid="stColumn"]:nth-of-type(2) label p {
        color: #f1faee !important; font-weight: 700; text-align: center; display: block;
    }
    .st-key-corner_row [data-testid="stColumn"]:nth-of-type(2) [data-baseweb="select"] { text-align: center; }
    .st-key-corner_row [data-testid="stColumn"]:nth-of-type(3) label p { color: #0072ce !important; font-weight: 700; }

    /* Row 2: rounds / title fight -- both centered within their column.
       stWidgetLabel/stRadio/stCheckbox wrappers size to their content by
       default, so text-align/justify-content have no room to act until
       those wrappers are stretched to the column's full width. */
    .st-key-rules_row [data-testid="stColumn"] { text-align: center; }
    .st-key-rules_row [data-testid="stColumn"] [data-testid="stElementContainer"],
    .st-key-rules_row [data-testid="stColumn"] [data-testid="stRadio"] {
        width: 100% !important;
    }
    /* Center the checkbox as a single opaque unit from OUTSIDE it, via its
       parent -- not by resizing/reflowing anything inside its own <label>.
       stCheckbox's internal icon/input/text are laid out by BaseWeb in a
       way that isn't safe to restyle piecemeal: forcing width/justify-
       content on pieces inside that label (tried twice) detached the
       invisible native <input> from its visible icon, silently breaking
       the click target while still looking fine on screen. */
    .st-key-rules_row [data-testid="stColumn"]:nth-of-type(2) [data-testid="stElementContainer"] {
        display: flex; justify-content: center;
    }
    /* stWidgetLabel is itself a flex box (justify-content:normal by default)
       -- widening it isn't enough, its flex child still hugs the left edge
       unless the box's own justify-content is centered too. Scoped to the
       Rounds column only: the checkbox's own stWidgetLabel wraps just its
       text as ONE sibling of the checkbox icon/input inside a shared flex
       row, and stretching it to 100% blew that row apart, displacing the
       invisible input off of its visible icon (checkbox became unclickable). */
    .st-key-rules_row [data-testid="stColumn"]:nth-of-type(1) [data-testid="stWidgetLabel"] {
        width: 100% !important; justify-content: center !important;
    }
    /* stWidgetLabel's <p> (Rounds' standalone title) is safe to force
       block+centered. stCheckbox's <p> must NOT get display:block -- it
       sits inline next to the checkbox icon in the same flex row, and
       forcing it to block broke that layout badly enough to visually
       overlap and eat the checkbox's click target entirely. */
    .st-key-rules_row [data-testid="stColumn"] [data-testid="stWidgetLabel"] p {
        text-align: center; display: block; font-weight: 700;
    }
    .st-key-rules_row [data-testid="stColumn"]:nth-of-type(1) [data-testid="stWidgetLabel"] p { color: #f77f00 !important; }
    .st-key-rules_row [data-testid="stColumn"]:nth-of-type(1) [role="radiogroup"] {
        display: flex !important; justify-content: center; width: 100%;
    }
    .st-key-rules_row [data-testid="stColumn"]:nth-of-type(2) [data-testid="stCheckbox"] p { color: #ffd60a !important; font-weight: 700; }
    .st-key-rules_row [data-testid="stColumn"]:nth-of-type(2) [data-testid="stCheckbox"] svg { fill: #ffd60a !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

# Streamlit reruns this whole script on every widget interaction; without
# caching, each click re-unpickled 7MB of models and re-read a 7MB parquet.
@st.cache_resource
def _load():
    artifacts = load_artifacts()
    history = load_history()
    return artifacts, history, list_fighters(history)


artifacts, history, fighters = _load()

# Fight-card layout: red corner, weight class, blue corner.
with st.container(key="corner_row"):
    red_col, weight_col, blue_col = st.columns(3)
    with red_col:
        red = st.selectbox("\U0001F534 Red corner", fighters, index=None, placeholder="Select fighter")
    with weight_col:
        weight_classes = artifacts["dtypes"]["weight_class"].categories.tolist()
        weight_class = st.selectbox(
            "\U00002696\U0000FE0F Weight class", weight_classes, index=None, placeholder="Select weight class"
        )
    with blue_col:
        # Same-fighter constraint enforced by excluding red from blue's options,
        # rather than validating after the fact.
        blue_options = [f for f in fighters if f != red]
        blue = st.selectbox("\U0001F535 Blue corner", blue_options, index=None, placeholder="Select fighter")

with st.container(key="rules_row"):
    rounds_col, title_col, country_col = st.columns(3)
    with title_col:
        title_fight = st.checkbox("\U0001F451 Title fight")
    with rounds_col:
        # Title fights are always 5 rounds -- force and lock it rather than
        # letting an invalid 3-round title fight be submitted.
        total_round_number = st.radio(
            "\U0001F514 Rounds", [3, 5],
            index=1 if title_fight else None,
            horizontal=True,
            disabled=title_fight,
        )
    with country_col:
        # Feeds the home-crowd features; empty = unknown (features go NaN).
        event_country = st.text_input("\U0001F30D Event country", value="USA")

with st.expander("\U0001F4B0 Bookmaker odds (optional)"):
    odds_red_col, odds_blue_col = st.columns(2)
    with odds_red_col:
        odds_red = st.number_input("Decimal odds — red", min_value=1.01, value=None, placeholder="e.g. 1.85")
    with odds_blue_col:
        odds_blue = st.number_input("Decimal odds — blue", min_value=1.01, value=None, placeholder="e.g. 2.10")

if st.button("Predict", type="primary"):
    if not red or not blue or not weight_class or not total_round_number:
        st.warning("Pick both fighters, a weight class, and rounds first.")
    else:
        try:
            winner, proba = predict_winner(
                red, blue, weight_class, title_fight, total_round_number,
                history, artifacts,
                event_country=event_country.strip() or None,
                odds_r=odds_red, odds_b=odds_blue,
            )
            confidence = proba if winner == red else 1 - proba
            st.success(f"**{winner}** wins")
            st.metric(f"Confidence ({winner})", f"{confidence:.1%}")
            st.caption(
                "Calibrated via Platt scaling on pooled walk-forward CV "
                "predictions — tracks real win frequency, not just ranking."
            )
            # Value bet: at most one side's model probability can beat the
            # market's implied probability. Same maths as the weekly job.
            bets = [
                (name, o, kelly_edge(p, o))
                for name, p, o in ((red, proba, odds_red), (blue, 1 - proba, odds_blue))
                if o
            ]
            value = [(n, o, k) for n, o, k in bets if k > 0]
            if value:
                name, o, k = value[0]
                st.info(
                    f"Value bet: **{name}** @ {o:.2f} — Kelly stake "
                    f"{k:.1%} of bankroll. The model's edge over bookmakers "
                    f"is unproven; bet only what you're happy to lose."
                )
            elif bets:
                st.info("No value at these odds — the market prices both sides at or above the model's probabilities.")
        except ValueError as e:
            st.error(str(e))
