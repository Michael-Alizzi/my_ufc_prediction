#!/usr/bin/env python3
"""Test the email pipeline with mock UFC data."""
import os
from dotenv import load_dotenv

from send_weekly_predictions import (
    make_predictions, format_predictions_html, send_email
)
from predict import load_artifacts, load_history

load_dotenv()

# Mock UFC event data for testing
mock_fights = [
    {"fighter1": "sean strickland", "fighter2": "dricus du plessis", "weight_class": "Middleweight"},
    {"fighter1": "israel adesanya", "fighter2": "alex pereira", "weight_class": "Middleweight"},
]

print("Loading prediction artifacts...")
artifacts = load_artifacts()
history = load_history()

print("Making predictions on mock fights...")
predictions = make_predictions(mock_fights, history, artifacts)

if predictions:
    print(f"✓ Generated {len(predictions)} predictions")
    for pred in predictions:
        print(f"  {pred['fighter1']} vs {pred['fighter2']}: {pred['prediction']} ({pred['confidence']})")

    print("\nFormatting HTML email...")
    html = format_predictions_html("UFC Test Event", predictions)
    print(f"✓ HTML email formatted ({len(html)} chars)")

    print("\nSending test email...")
    recipient = os.getenv("RECIPIENT_EMAIL", os.getenv("GMAIL_ADDRESS"))
    try:
        send_email(recipient, "UFC Predictions Test", html)
        print(f"✓ Email sent successfully to {recipient}!")
    except Exception as e:
        print(f"✗ Email send failed: {e}")
else:
    print("✗ No predictions generated")
