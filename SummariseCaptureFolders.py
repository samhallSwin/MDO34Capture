#!/usr/bin/env python3

"""
Run MeasureChannelDelay.py across all capture-session folders.

Each folder containing NPZ captures receives its own channel_delay.csv.  This
script also writes one summary CSV with the key delay statistics for every
folder.

Examples:

    py SummariseCaptureFolders.py

    py SummariseCaptureFolders.py captures --fraction 0.2

Requirements:
    pip install numpy
"""

import argparse
import csv
from pathlib import Path

from MeasureChannelDelay import find_capture_files, measure_capture, write_results


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Measure CH1-to-CH2 delay in every capture folder and write a "
            "cross-folder summary CSV."
        )
    )
    parser.add_argument(
        "captures",
        type=Path,
        nargs="?",
        default=Path("captures"),
        help="Root captures directory (default: captures).",
    )
    parser.add_argument(
        "--fraction",
        type=float,
        default=0.2,
        help=(
            "Fraction of each channel's fall used as the event level "
            "(0 < fraction < 1; default: 0.2)."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "Cross-folder summary CSV path (default: "
            "capture_folder_summary.csv in the captures directory)."
        ),
    )
    return parser.parse_args()


def find_capture_directories(root):
    """Return every directory below root that directly contains NPZ files."""
    if not root.exists():
        raise FileNotFoundError(f"Captures directory does not exist: {root}")
    if not root.is_dir():
        raise ValueError(f"Captures path is not a directory: {root}")

    directories = []
    for directory in [root, *root.rglob("*")]:
        if directory.is_dir() and any(directory.glob("*.npz")):
            directories.append(directory)

    if not directories:
        raise FileNotFoundError(f"No capture folders found in: {root}")

    return sorted(directories)


def summarise_folder(directory, fraction):
    captures = find_capture_files(directory)
    rows = [measure_capture(capture, fraction) for capture in captures]
    average_row = write_results(directory / "channel_delay.csv", rows)

    return {
        "folder": str(directory),
        "capture_count": str(len(captures)),
        "successful_capture_count": average_row["status"].split()[0],
        "average_ch2_minus_ch1_ns": average_row["ch2_minus_ch1_ns"],
        "average_positive_ns": average_row["average_positive_ns"],
        "average_negative_ns": average_row["average_negative_ns"],
        "positive_count": average_row["positive_count"],
        "negative_count": average_row["negative_count"],
        "largest_positive_absolute_ns": average_row[
            "largest_positive_absolute_ns"
        ],
        "largest_negative_absolute_ns": average_row[
            "largest_negative_absolute_ns"
        ],
    }


def write_summary(filename, rows):
    fieldnames = [
        "folder",
        "capture_count",
        "successful_capture_count",
        "average_ch2_minus_ch1_ns",
        "average_positive_ns",
        "average_negative_ns",
        "positive_count",
        "negative_count",
        "largest_positive_absolute_ns",
        "largest_negative_absolute_ns",
    ]
    with filename.open("w", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    args = parse_args()
    if not 0.0 < args.fraction < 1.0:
        raise ValueError("--fraction must be greater than 0 and less than 1")

    folders = find_capture_directories(args.captures)
    output_path = args.output or args.captures / "capture_folder_summary.csv"

    print(f"Analysing {len(folders)} capture folder(s)...")
    summary_rows = []
    for folder in folders:
        summary = summarise_folder(folder, args.fraction)
        summary["folder"] = str(folder.relative_to(args.captures)) or "."
        summary_rows.append(summary)
        print(
            f"  {summary['folder']}: "
            f"{summary['successful_capture_count']}/"
            f"{summary['capture_count']} successful"
        )

    write_summary(output_path, summary_rows)
    print(f"Cross-folder summary written to: {output_path}")


if __name__ == "__main__":
    main()
