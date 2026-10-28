#!/usr/bin/env python3

"""
Measure the relative falling-edge delay between CH1 and CH2 in MDO34
captures.

The event time is the linearly interpolated crossing at a fraction of each
channel's own fall from its initial baseline to its final level.  This avoids
relying on a shared absolute voltage when the two channels have slightly
different amplitudes.

Examples:

    py MeasureChannelDelay.py captures/2026-10-06_12-54-40

    py MeasureChannelDelay.py captures/2026-10-06_12-54-40 \
        --fraction 0.2 --output results.csv

The output CSV contains one row per capture and a final AVERAGE row.  A
positive delay means CH2 crossed its level later than CH1.

Requirements:
    pip install numpy
"""

import argparse
import csv
from pathlib import Path

import numpy as np


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Measure the relative CH1-to-CH2 falling-edge delay in one "
            "MDO34 NPZ capture or a folder of captures."
        )
    )

    parser.add_argument(
        "input",
        type=Path,
        help="Input .npz capture file or directory containing .npz files.",
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
            "Output CSV path (default: channel_delay.csv in the input "
            "directory, or beside an input file)."
        ),
    )

    return parser.parse_args()


def find_capture_files(input_path):
    if not input_path.exists():
        raise FileNotFoundError(f"Input does not exist: {input_path}")

    if input_path.is_file():
        if input_path.suffix.lower() != ".npz":
            raise ValueError("Input file must be an NPZ capture file.")
        return [input_path]

    if input_path.is_dir():
        captures = sorted(input_path.glob("*.npz"))
        if not captures:
            raise FileNotFoundError(f"No NPZ capture files found in: {input_path}")
        return captures

    raise ValueError(f"Input is neither a file nor a directory: {input_path}")


def detect_channels(data):
    """Return the channels stored in new and older capture files."""
    if "channels" in data:
        return [int(ch) for ch in np.atleast_1d(data["channels"])]

    return [ch for ch in range(1, 5) if f"ch{ch}_raw" in data]


def channel_level(raw, start, stop):
    """Return a robust representative raw value for a section of a trace."""
    return float(np.median(raw[start:stop]))


def find_fractional_crossing(raw, fraction):
    """
    Locate a falling transition using initial and final sections of raw data.

    Returns the fractional sample index plus the two raw levels.  Keeping the
    search in raw ADC counts avoids making a full floating-point voltage copy
    of a potentially large capture.
    """
    npoints = len(raw)
    section = max(1, npoints // 10)
    baseline = channel_level(raw, 0, section)
    final = channel_level(raw, npoints - section, npoints)

    if final >= baseline:
        raise ValueError("channel does not have a falling transition")

    level = baseline + fraction * (final - baseline)
    crossings = np.flatnonzero((raw[:-1] > level) & (raw[1:] <= level))

    if len(crossings) == 0:
        raise ValueError("no falling crossing found")

    index = int(crossings[0])
    before = float(raw[index])
    after = float(raw[index + 1])

    # A linear interpolation makes the result less sensitive to the sample
    # grid.  The denominator should be non-zero for a crossing, but retain a
    # harmless fallback for unusual integer/quantised traces.
    if after == before:
        between_samples = 0.0
    else:
        between_samples = (level - before) / (after - before)

    return index + between_samples, baseline, final


def measure_capture(filename, fraction):
    """Return one CSV-ready result row for a capture."""
    row = {
        "capture": filename.name,
        "ch1_crossing_sample": "",
        "ch2_crossing_sample": "",
        "ch2_minus_ch1_ns": "",
        "ch1_baseline_raw": "",
        "ch1_final_raw": "",
        "ch2_baseline_raw": "",
        "ch2_final_raw": "",
        "status": "",
    }

    try:
        with np.load(filename, allow_pickle=False) as data:
            channels = detect_channels(data)
            if 1 not in channels or 2 not in channels:
                raise ValueError("CH1 and/or CH2 is not present")

            xincr = float(data["xincr"])

            # NPZ members are loaded individually: at most one channel is
            # held by this script at a time.  No full trace CSV or plot is
            # generated.
            ch1 = data["ch1_raw"]
            ch1_crossing, ch1_baseline, ch1_final = find_fractional_crossing(
                ch1, fraction
            )
            del ch1

            ch2 = data["ch2_raw"]
            ch2_crossing, ch2_baseline, ch2_final = find_fractional_crossing(
                ch2, fraction
            )
            del ch2

        delay_ns = (ch2_crossing - ch1_crossing) * xincr * 1e9
        row.update(
            {
                "ch1_crossing_sample": f"{ch1_crossing:.6f}",
                "ch2_crossing_sample": f"{ch2_crossing:.6f}",
                "ch2_minus_ch1_ns": f"{delay_ns:.9g}",
                "ch1_baseline_raw": f"{ch1_baseline:.6g}",
                "ch1_final_raw": f"{ch1_final:.6g}",
                "ch2_baseline_raw": f"{ch2_baseline:.6g}",
                "ch2_final_raw": f"{ch2_final:.6g}",
                "status": "ok",
            }
        )
    except (KeyError, OSError, ValueError) as error:
        row["status"] = f"error: {error}"

    return row


def default_output_path(input_path):
    directory = input_path if input_path.is_dir() else input_path.parent
    return directory / "channel_delay.csv"


def write_results(filename, rows):
    fieldnames = [
        "capture",
        "ch1_crossing_sample",
        "ch2_crossing_sample",
        "ch2_minus_ch1_ns",
        "average_positive_ns",
        "average_negative_ns",
        "positive_count",
        "negative_count",
        "largest_positive_absolute_ns",
        "largest_negative_absolute_ns",
        "ch1_baseline_raw",
        "ch1_final_raw",
        "ch2_baseline_raw",
        "ch2_final_raw",
        "status",
    ]

    successful_delays = [
        float(row["ch2_minus_ch1_ns"])
        for row in rows
        if row["status"] == "ok"
    ]
    positive_delays = [delay for delay in successful_delays if delay > 0]
    negative_delays = [delay for delay in successful_delays if delay < 0]

    average_row = {field: "" for field in fieldnames}
    average_row["capture"] = "AVERAGE"
    average_row["status"] = f"{len(successful_delays)} successful capture(s)"
    average_row["positive_count"] = str(len(positive_delays))
    average_row["negative_count"] = str(len(negative_delays))
    if successful_delays:
        average_row["ch2_minus_ch1_ns"] = f"{np.mean(successful_delays):.9g}"
    if positive_delays:
        average_row["average_positive_ns"] = f"{np.mean(positive_delays):.9g}"
        average_row["largest_positive_absolute_ns"] = f"{max(positive_delays):.9g}"
    if negative_delays:
        average_row["average_negative_ns"] = f"{np.mean(negative_delays):.9g}"
        average_row["largest_negative_absolute_ns"] = f"{abs(min(negative_delays)):.9g}"

    with filename.open("w", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
        writer.writerow(average_row)

    return average_row


def main():
    args = parse_args()

    if not 0.0 < args.fraction < 1.0:
        raise ValueError("--fraction must be greater than 0 and less than 1")

    captures = find_capture_files(args.input)
    output_path = args.output or default_output_path(args.input)

    print(f"Measuring {len(captures)} capture(s) at {args.fraction:.0%} of the fall...")
    rows = []
    for capture in captures:
        row = measure_capture(capture, args.fraction)
        rows.append(row)
        print(f"  {capture.name}: {row['status']}")

    average_row = write_results(output_path, rows)
    print(f"Results written to: {output_path}")
    print(f"Average CH2 - CH1 delay: {average_row['ch2_minus_ch1_ns'] or 'n/a'} ns")


if __name__ == "__main__":
    main()
