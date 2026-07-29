#!/usr/bin/env python3
"""Fetch next UFC event, make predictions, and email results.

Run weekly via a scheduled task. Expects these env vars:
  GMAIL_ADDRESS: Gmail account to send from (e.g., myeckal123@gmail.com)
  GMAIL_APP_PASSWORD: Gmail app-specific password (not your regular password)
  RECIPIENT_EMAIL: Email to send predictions to (defaults to GMAIL_ADDRESS)

Usage: python send_weekly_predictions.py
"""
import os
import smtplib
import logging
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import requests
from bs4 import BeautifulSoup
import pandas as pd

from predict import load_artifacts, load_history, predict_winner

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def fetch_upcoming_events():
    """Fetch upcoming UFC events from ufc.com."""
    try:
        response = requests.get(
            "https://www.ufc.com/events",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")

        # Look for event cards - these are typically in event link containers
        event_links = soup.find_all("a", {"data-testid": "internal-link"})

        upcoming_events = []
        for link in event_links:
            href = link.get("href", "")
            if "/event/" in href:
                title = link.get_text(strip=True)
                upcoming_events.append({
                    "title": title,
                    "url": f"https://www.ufc.com{href}" if href.startswith("/") else href
                })

        return upcoming_events
    except Exception as e:
        logger.error(f"Failed to fetch events: {e}")
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
    """Make predictions for a list of fights."""
    predictions = []

    for fight in fights:
        try:
            fighter1 = fight["fighter1"].lower().strip()
            fighter2 = fight["fighter2"].lower().strip()
            weight_class = fight.get("weight_class", "Middleweight")

            # Skip if fighters not in training data
            all_fighters = pd.concat([
                history["r_fighter"],
                history["b_fighter"]
            ]).unique()

            if fighter1 not in all_fighters or fighter2 not in all_fighters:
                logger.warning(f"Fighter(s) not in training data: {fighter1} vs {fighter2}")
                continue

            winner, proba = predict_winner(
                fighter1.title(),
                fighter2.title(),
                weight_class,
                title_fight=False,
                total_round_number=3,
                history=history,
                artifacts=artifacts,
            )

            confidence = proba if winner == fighter1.title() else 1 - proba

            predictions.append({
                "fighter1": fight["fighter1"],
                "fighter2": fight["fighter2"],
                "prediction": winner,
                "confidence": f"{confidence:.1%}",
            })
        except Exception as e:
            logger.error(f"Prediction failed for {fight['fighter1']} vs {fight['fighter2']}: {e}")
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


def send_email(recipient, subject, html_content):
    """Send email with HTML content via Gmail."""
    gmail_address = os.getenv("GMAIL_ADDRESS")
    gmail_password = os.getenv("GMAIL_APP_PASSWORD")

    if not gmail_address or not gmail_password:
        raise ValueError(
            "Missing email credentials. Set GMAIL_ADDRESS and GMAIL_APP_PASSWORD env vars."
        )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = gmail_address
    msg["To"] = recipient

    msg.attach(MIMEText(html_content, "html"))

    try:
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(gmail_address, gmail_password)
        server.sendmail(gmail_address, recipient, msg.as_string())
        server.quit()
        logger.info(f"Email sent to {recipient}")
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        raise


def main():
    """Fetch events, make predictions, and send email."""
    logger.info("Fetching upcoming UFC events...")
    events = fetch_upcoming_events()

    if not events:
        logger.error("No upcoming events found")
        return

    # Get the next upcoming event
    next_event = events[0]
    logger.info(f"Next event: {next_event['title']}")

    logger.info(f"Fetching fights for {next_event['title']}...")
    fights = fetch_event_fights(next_event["url"])

    if not fights:
        logger.error(f"No fights found for {next_event['title']}")
        return

    logger.info(f"Found {len(fights)} fights")

    # Load artifacts and make predictions
    logger.info("Loading prediction artifacts...")
    artifacts = load_artifacts()
    history = load_history()

    logger.info("Making predictions...")
    predictions = make_predictions(fights, history, artifacts)

    if not predictions:
        logger.error("No valid predictions made")
        return

    # Format and send email
    logger.info("Formatting predictions...")
    html_content = format_predictions_html(next_event["title"], predictions)

    recipient = os.getenv("RECIPIENT_EMAIL", os.getenv("GMAIL_ADDRESS"))
    subject = f"UFC Predictions: {next_event['title']}"

    logger.info(f"Sending predictions email to {recipient}...")
    send_email(recipient, subject, html_content)

    logger.info("Done!")


if __name__ == "__main__":
    main()
