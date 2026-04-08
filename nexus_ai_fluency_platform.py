#!/usr/bin/env python3
"""Nexus AI Fluency Platform helper script.

This script loads a staff usage CSV, applies masking, honors opt-in/opt-out,
and prints a summary dashboard with AI adoption metrics.
"""

import argparse
import csv
import os
import re
from collections import Counter, defaultdict
from datetime import datetime

EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
PHONE_PATTERN = re.compile(r"\b(?:\+?\d[\d\s\-().]{7,}\d)\b")
NAME_TOKEN_TEMPLATE = "[USER_{:02d}]"
EMAIL_TOKEN_TEMPLATE = "[EMAIL_{:02d}]"
PHONE_TOKEN_TEMPLATE = "[PHONE_{:02d}]"
AI_DISCLAIMER = (
    "⚠️ Nexus AI outputs are probabilistic and may contain inaccuracies. "
    "Please verify critical data."
)


def build_name_mapping(names):
    """Create a deterministic masking map for staff names."""
    mapping = {}
    token_index = 1
    for name in sorted(set(names)):
        if name and name not in mapping:
            mapping[name] = NAME_TOKEN_TEMPLATE.format(token_index)
            token_index += 1
    return mapping


def mask_text(text, name_mapping, email_index=None, phone_index=None):
    """Mask names, emails, and phone numbers in a text string."""
    if text is None:
        return text

    masked = text

    for raw_name, token in name_mapping.items():
        masked = re.sub(rf"\b{re.escape(raw_name)}\b", token, masked)

    if email_index is None:
        email_index = [0]
    if phone_index is None:
        phone_index = [0]

    def replace_email(match):
        email_index[0] += 1
        return EMAIL_TOKEN_TEMPLATE.format(email_index[0])

    def replace_phone(match):
        phone_index[0] += 1
        return PHONE_TOKEN_TEMPLATE.format(phone_index[0])

    masked = EMAIL_PATTERN.sub(replace_email, masked)
    masked = PHONE_PATTERN.sub(replace_phone, masked)
    return masked


def load_usage_data(path, masking_mode=False):
    """Load usage rows from CSV and optionally mask PII."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Input file not found: {path}")

    with open(path, newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        rows = list(reader)

    staff_names = [row.get("Staff_Name_Raw", "") for row in rows]
    name_mapping = build_name_mapping(staff_names)

    for row in rows:
        if masking_mode:
            row["Staff_Name_Raw"] = mask_text(row.get("Staff_Name_Raw", ""), name_mapping)
            row["User_Sentiment"] = mask_text(row.get("User_Sentiment", ""), name_mapping)

    return rows


def summarize_usage(rows):
    """Produce dashboard metrics from loaded rows."""
    categories = defaultdict(list)
    total = len(rows)
    hallucination_reports = 0
    fluency_scores = []

    for row in rows:
        category = row.get("Tool_Category", "Unknown")
        try:
            score = float(row.get("Fluency_Score", 0))
        except ValueError:
            score = 0.0
        categories[category].append(score)
        fluency_scores.append(score)

        verified_value = row.get("Output_Verified", "False").strip().lower()
        if verified_value in {"false", "0", "no"}:
            hallucination_reports += 1

    average_fluency = sum(fluency_scores) / max(1, len(fluency_scores))
    tool_summary = [
        {
            "category": category,
            "count": len(scores),
            "avg_fluency": sum(scores) / max(1, len(scores)),
        }
        for category, scores in sorted(categories.items(), key=lambda item: item[0])
    ]

    ai_curious = sum(1 for score in fluency_scores if score <= 4)
    ai_fluent = sum(1 for score in fluency_scores if score >= 8)
    ai_curious_pct = 100.0 * ai_curious / max(1, total)
    ai_fluent_pct = 100.0 * ai_fluent / max(1, total)
    output_verified_pct = 100.0 * (total - hallucination_reports) / max(1, total)

    return {
        "total_records": total,
        "tool_summary": tool_summary,
        "average_fluency": average_fluency,
        "hallucination_reports": hallucination_reports,
        "ai_curious_pct": ai_curious_pct,
        "ai_fluent_pct": ai_fluent_pct,
        "output_verified_pct": output_verified_pct,
    }


def print_dashboard(summary, masking_mode, status):
    """Print a command-line dashboard summary."""
    print("\n=== Nexus AI Fluency Platform Summary ===")
    print(AI_DISCLAIMER)
    print(f"Status: {status}")
    print(f"Masking Mode: {'ON' if masking_mode else 'OFF'}")
    print(f"Total records analyzed: {summary['total_records']}")
    print(f"Average Fluency Score: {summary['average_fluency']:.2f}")
    print(f"Verified outputs: {summary['output_verified_pct']:.1f}%")
    print(f"Hallucination reports: {summary['hallucination_reports']}")
    print(f"AI-Curious: {summary['ai_curious_pct']:.1f}%")
    print(f"AI-Fluent: {summary['ai_fluent_pct']:.1f}%")
    print("\nTool Category Breakdown:")
    for tool in summary["tool_summary"]:
        print(
            f"  - {tool['category']}: {tool['count']} records, "
            f"avg fluency {tool['avg_fluency']:.2f}"
        )
    print("=== End of Summary ===\n")


def save_masked_output(rows, output_path):
    """Save masked rows into a CSV output file."""
    if not rows:
        return

    fieldnames = list(rows[0].keys())
    with open(output_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate anonymized AI fluency dashboard metrics from usage data."
    )
    parser.add_argument(
        "--input",
        default="nexus_ai_staff_usage.csv",
        help="Path to the usage CSV file.",
    )
    parser.add_argument(
        "--output",
        default="masked_usage_output.csv",
        help="Optional path to save masked output CSV when masking is enabled.",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--opt-in",
        dest="opt_in",
        action="store_true",
        help="Enable data collection and reporting for this user.",
    )
    group.add_argument(
        "--opt-out",
        dest="opt_in",
        action="store_false",
        help="Disable all data collection and mark status as Inactive.",
    )
    parser.add_argument(
        "--masking-mode",
        action="store_true",
        help="Enable regex-based PII masking for names, emails, and phone numbers.",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if args.opt_in is False:
        print("Status: Inactive")
        print(AI_DISCLAIMER)
        print("Data collection is disabled for this user. No dashboard data is generated.")
        return

    rows = load_usage_data(args.input, masking_mode=args.masking_mode)
    summary = summarize_usage(rows)
    print_dashboard(summary, masking_mode=args.masking_mode, status="Active")

    if args.masking_mode:
        save_masked_output(rows, args.output)
        print(f"Masked output saved to: {args.output}")


if __name__ == "__main__":
    main()
