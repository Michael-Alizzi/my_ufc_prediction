#!/usr/bin/env python3
"""Fetch next UFC event, make predictions, and email results.

Run weekly via a scheduled task. Credentials from .env file or env vars:
  GMAIL_ADDRESS: Gmail account to send from (e.g., myeckal123@gmail.com)
  GMAIL_APP_PASSWORD: Gmail app-specific password (not your regular password)
  RECIPIENT_EMAIL: Email to send predictions to (defaults to GMAIL_ADDRESS)

Setup: Create .env file in repo root with GMAIL_ADDRESS and GMAIL_APP_PASSWORD.

Usage:
  python send_weekly_predictions.py
      Scrape ufc.com for the next event, predict, email (needs open network + SMTP).
  python send_weekly_predictions.py --fights-json card.json --event-title "UFC ..."
      Predict a known card instead of scraping. card.json is a list of
      {"fighter1", "fighter2", "weight_class", "title_fight"?, "rounds"?} dicts.
      Prints a markdown table and writes predictions_output.md; email is attempted
      only if SMTP is reachable (it is not from the Claude cloud environment,
      where the runner delivers results via its own notification email instead).
"""
import argparse
import json
import os
import smtplib
import logging
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import requests
from bs4 import BeautifulSoup
import pandas as pd
from dotenv import load_dotenv

from predict import load_artifacts, load_history, predict_winner

load_dotenv()  # Load .env file if it exists

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def fetch_upcoming_events():
    """Fetch upcoming UFC events from ufc.com."""
    try:
        logger.info("Attempting to fetch from https://www.ufc.com/events")
        response = requests.get(
            "https://www.ufc.com/events",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")

        # Look for event cards - these are typically in event link containers
        event_links = soup.find_all("a", {"data-testid": "internal-link"})
        logger.info(f"Found {len(event_links)} links on UFC events page")

        upcoming_events = []
        for link in event_links:
            href = link.get("href", "")
            if "/event/" in href:
                title = link.get_text(strip=True)
                upcoming_events.append({
                    "title": title,
                    "url": f"https://www.ufc.com{href}" if href.startswith("/") else href
                })

        logger.info(f"Extracted {len(upcoming_events)} upcoming events")
        return upcoming_events
    except Exception as e:
        logger.error(f"Failed to fetch events: {e}", exc_info=True)
        return []


def fetch_event_fights(event_url):
    """Fetch fights from a specific event page."""
    try:
        response = requests.get(event_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")

        # Look for fight cards - each fight typically has fighter names and details
        fights = []

        # Try to find fight rows - structure varies, but usually in a table or list
        fight_rows = soup.find_all("tr", class_="")  # Empty class selector catches most fight rows

        for row in fight_rows:
            # Extract fighter names and fight details
            cells = row.find_all("td")
            if len(cells) >= 2:
                # Typically: [fighter1, fighter2, weight_class, ...]
                fighter1 = cells[0].get_text(strip=True)
                fighter2 = cells[1].get_text(strip=True)

                if fighter1 and fighter2:
                    fights.append({
                        "fighter1": fighter1,
                        "fighter2": fighter2,
                        "weight_class": "Middleweight",  # Default, can be extracted if present
                    })

        return fights
    except Exception as e:
        logger.error(f"Failed to fetch fights from {event_url}: {e}")
        return []


def make_predictions(fights, history, artifacts):
    """Make predictions for a list of fights.

    Each fight dict: fighter1, fighter2, weight_class, and optionally
    title_fight (bool), rounds (3 or 5, defaults to 3), and odds1/odds2
    (decimal bookmaker odds for fighter1/fighter2, used to size a bet).

    Bet sizing: quarter-Kelly on a $100 bankroll against the predicted
    winner's odds, capped at $15/fight. $0 means the model's probability is
    below the odds' implied probability (no value at that price); "-" means
    odds weren't provided or the fight couldn't be predicted.
    """
    predictions = []
    known = set(pd.concat([history["r_fighter"], history["b_fighter"]]).unique())

    for fight in fights:
        try:
            fighter1 = fight["fighter1"].lower().strip()
            fighter2 = fight["fighter2"].lower().strip()
            weight_class = fight.get("weight_class", "Middleweight")
            title_fight = bool(fight.get("title_fight", False))
            rounds = 5 if title_fight else int(fight.get("rounds", 3))

            missing = [f for f in (fighter1, fighter2) if f not in known]
            if missing:
                logger.warning(f"Skipping {fighter1} vs {fighter2}: no history for {missing}")
                predictions.append({
                    "fighter1": fight["fighter1"], "fighter2": fight["fighter2"],
                    "weight_class": weight_class, "prediction": "no data",
                    "confidence": "-",
                })
                continue

            winner, proba = predict_winner(
                fighter1, fighter2, weight_class,
                title_fight=title_fight,
                total_round_number=rounds,
                history=history,
                artifacts=artifacts,
            )

            confidence = proba if winner == fighter1 else 1 - proba

            odds = fight.get("odds1") if winner == fighter1 else fight.get("odds2")
            stake = "-"
            if odds:
                edge = confidence * float(odds) - 1
                if edge <= 0:
                    stake = "$0"
                else:
                    kelly = edge / (float(odds) - 1)
                    stake = f"${min(15, max(1, round(100 * kelly / 4)))}"

            predictions.append({
                "fighter1": fight["fighter1"],
                "fighter2": fight["fighter2"],
                "weight_class": weight_class,
                "prediction": winner.title(),
                "confidence": f"{confidence:.1%}",
                "stake": stake,
            })
        except Exception as e:
            logger.error(f"Prediction failed for {fight['fighter1']} vs {fight['fighter2']}: {e}")
            predictions.append({
                "fighter1": fight["fighter1"], "fighter2": fight["fighter2"],
                "weight_class": fight.get("weight_class", "?"),
                "prediction": "error", "confidence": "-",
            })
            continue

    return predictions


def format_predictions_html(event_title, predictions):
    """Format predictions as an HTML table."""
    if not predictions:
        return f"""
        <html>
        <body>
            <h2>UFC Predictions: {event_title}</h2>
            <p>No predictions available for this event.</p>
        </body>
        </html>
        """

    rows = ""
    for pred in predictions:
        rows += f"""
        <tr>
            <td style="padding: 10px; border-bottom: 1px solid #ddd;">{pred['fighter1']}</td>
            <td style="padding: 10px; border-bottom: 1px solid #ddd;">{pred['fighter2']}</td>
            <td style="padding: 10px; border-bottom: 1px solid #ddd; font-weight: bold; color: #e63946;">{pred['prediction']}</td>
            <td style="padding: 10px; border-bottom: 1px solid #ddd;">{pred['confidence']}</td>
            <td style="padding: 10px; border-bottom: 1px solid #ddd;">{pred.get('stake', '-')}</td>
        </tr>
        """

    html = f"""
    <html>
    <body style="font-family: Arial, sans-serif;">
        <h2>UFC Predictions: {event_title}</h2>
        <p>Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        <table style="width: 100%; border-collapse: collapse; border: 1px solid #ddd;">
            <tr style="background-color: #f2f2f2;">
                <th style="padding: 12px; text-align: left; border-bottom: 2px solid #ddd;">Fighter 1</th>
                <th style="padding: 12px; text-align: left; border-bottom: 2px solid #ddd;">Fighter 2</th>
                <th style="padding: 12px; text-align: left; border-bottom: 2px solid #ddd;">Prediction</th>
                <th style="padding: 12px; text-align: left; border-bottom: 2px solid #ddd;">Confidence</th>
                <th style="padding: 12px; text-align: left; border-bottom: 2px solid #ddd;">Bet (of $100)</th>
            </tr>
            {rows}
        </table>
        <p style="font-size: 12px; color: #666; margin-top: 20px;">
            Predictions are made by an XGBoost + LightGBM ensemble trained on historical fight data.
            Confidence is calibrated via Platt scaling on pooled walk-forward CV predictions.
        </p>
    </body>
    </html>
    """

    return html


def format_predictions_markdown(event_title, predictions):
    """Format predictions as a markdown table (for logs / notification email)."""
    lines = [
        f"## UFC Predictions: {event_title}",
        f"_Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}_",
        "",
        "| Red corner | Blue corner | Weight class | Predicted winner | Confidence | Bet (of $100) |",
        "|---|---|---|---|---|---|",
    ]
    for p in predictions:
        lines.append(
            f"| {p['fighter1']} | {p['fighter2']} | {p.get('weight_class', '?')} "
            f"| **{p['prediction']}** | {p['confidence']} | {p.get('stake', '-')} |"
        )
    lines += [
        "",
        "_XGBoost + LightGBM ensemble; confidence calibrated on walk-forward CV._",
        "_Bets are quarter-Kelly vs the listed odds, capped at $15/fight. $0 = no "
        "value at the offered price; the model's betting edge is unproven, so "
        "treat stakes as entertainment sizing, not investment advice._",
    ]
    return "\n".join(lines)


def send_email(recipient, subject, html_content):
    """Send email with HTML content via Gmail."""
    gmail_address = os.getenv("GMAIL_ADDRESS")
    gmail_password = os.getenv("GMAIL_APP_PASSWORD")

    if not gmail_address or not gmail_password:
        logger.error("Missing credentials. Set GMAIL_ADDRESS and GMAIL_APP_PASSWORD in environment or .env file.")
        raise ValueError(
            f"Missing email credentials.\n"
            f"GMAIL_ADDRESS: {'✓ set' if gmail_address else '✗ missing'}\n"
            f"GMAIL_APP_PASSWORD: {'✓ set' if gmail_password else '✗ missing'}"
        )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = gmail_address
    msg["To"] = recipient

    msg.attach(MIMEText(html_content, "html"))

    try:
        logger.info(f"Connecting to Gmail SMTP (smtp.gmail.com:465)...")
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10)
        logger.info("Connected. Logging in...")
        server.login(gmail_address, gmail_password)
        logger.info("Login successful. Sending email...")
        server.sendmail(gmail_address, recipient, msg.as_string())
        server.quit()
        logger.info(f"✓ Email sent successfully to {recipient}")
    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"Gmail authentication failed. Check your GMAIL_APP_PASSWORD: {e}")
        raise
    except Exception as e:
        logger.error(f"Failed to send email: {e}", exc_info=True)
        raise


def run_card(fights, event_title):
    """Predict a known card: print + save a markdown table, email if possible."""
    artifacts = load_artifacts()
    history = load_history()
    predictions = make_predictions(fights, history, artifacts)
    if not predictions:
        raise SystemExit("No predictions produced")

    md = format_predictions_markdown(event_title, predictions)
    with open("predictions_output.md", "w") as f:
        f.write(md)
    print(md)
    logger.info("Wrote predictions_output.md")

    gmail_address = os.getenv("GMAIL_ADDRESS")
    if gmail_address and os.getenv("GMAIL_APP_PASSWORD"):
        recipient = os.getenv("RECIPIENT_EMAIL", gmail_address)
        try:
            html = format_predictions_html(event_title, predictions)
            send_email(recipient, f"UFC Predictions: {event_title}", html)
        except OSError as e:
            logger.warning(f"SMTP unavailable here ({e}); markdown output is the deliverable")
    return predictions


def main():
    """Fetch events, make predictions, and send email."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--fights-json", help="JSON file with the fight card")
    parser.add_argument("--event-title", default="Upcoming UFC Event")
    args = parser.parse_args()

    if args.fights_json:
        with open(args.fights_json) as f:
            fights = json.load(f)
        run_card(fights, args.event_title)
        return

    logger.info("=" * 60)
    logger.info("UFC Weekly Predictions Email Job Starting")
    logger.info("=" * 60)

    # Check credentials early
    gmail_address = os.getenv("GMAIL_ADDRESS")
    gmail_password = os.getenv("GMAIL_APP_PASSWORD")
    logger.info(f"Credentials check: GMAIL_ADDRESS={'✓' if gmail_address else '✗'}, GMAIL_APP_PASSWORD={'✓' if gmail_password else '✗'}")

    if not gmail_address or not gmail_password:
        logger.error("FATAL: Missing Gmail credentials in environment or .env file")
        return

    logger.info("Fetching upcoming UFC events...")
    events = fetch_upcoming_events()

    if not events:
        logger.error("Could not fetch UFC.com events. This is expected in restricted network environments.")
        logger.error("Alternative: You can manually trigger the script with mock event data on your desktop.")
        logger.error("The email infrastructure is ready - the blocker is accessing UFC.com from this environment.")
        return

    # Get the next upcoming event
    next_event = events[0]
    logger.info(f"Next event found: {next_event['title']}")

    logger.info(f"Fetching fights for: {next_event['title']}")
    fights = fetch_event_fights(next_event["url"])

    if not fights:
        logger.warning(f"No fights found for {next_event['title']}, attempting fallback...")
        logger.info("Skipping email - need valid fights data")
        return

    logger.info(f"Found {len(fights)} fights to predict")

    # Load artifacts and make predictions
    logger.info("Loading prediction artifacts (ensemble.joblib, fighter_history.parquet)...")
    try:
        artifacts = load_artifacts()
        history = load_history()
        logger.info("✓ Artifacts loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load artifacts: {e}", exc_info=True)
        return

    logger.info("Making predictions...")
    predictions = make_predictions(fights, history, artifacts)

    if not predictions:
        logger.error("No valid predictions made from fetched fights")
        return

    logger.info(f"✓ Generated {len(predictions)} predictions")

    # Format and send email
    logger.info("Formatting HTML email...")
    html_content = format_predictions_html(next_event["title"], predictions)

    recipient = os.getenv("RECIPIENT_EMAIL", os.getenv("GMAIL_ADDRESS"))
    subject = f"UFC Predictions: {next_event['title']}"

    logger.info(f"Sending email to {recipient}...")
    try:
        send_email(recipient, subject, html_content)
        logger.info("=" * 60)
        logger.info("✓ JOB COMPLETED SUCCESSFULLY")
        logger.info("=" * 60)
    except Exception as e:
        logger.error("=" * 60)
        logger.error(f"✗ EMAIL SEND FAILED: {e}")
        logger.error("=" * 60)
        raise


if __name__ == "__main__":
    main()
