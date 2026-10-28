#!/usr/bin/env python3

"""
Extract a small event window from a Tektronix MDO34 NPZ capture.

Detection:
    Positive threshold:
        detects the first crossing from below to >= threshold.

    Negative threshold:
        detects the first crossing from above to <= threshold.

Examples:

    py ExtractEventWindow.py capture_0001.npz --threshold 0.5

    py ExtractEventWindow.py capture_0001.npz \
        --channel 2 \
        --threshold -0.2 \
        --pre-ns 50 \
        --post-ns 100

    py ExtractEventWindow.py capture_0001.npz \
        --threshold 0.5 \
        --no-image

Outputs:
    capture_0001_window.csv
    capture_0001_window.png

Requirements:
    pip install numpy matplotlib
"""

import argparse
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Detect a threshold crossing in an MDO34 capture "
            "and extract a small time window around the event."
        )
    )

    parser.add_argument(
        "capture",
        type=Path,
        help="Input .npz capture file",
    )

    parser.add_argument(
        "--channel",
        "-c",
        type=int,
        choices=[1, 2, 3, 4],
        default=1,
        help="Channel used for event detection (default: CH1)",
    )

    parser.add_argument(
        "--threshold",
        "-t",
        type=float,
        required=True,
        help=(
            "Detection threshold in volts. "
            "Positive values detect upward crossings; "
            "negative values detect downward crossings."
        ),
    )

    parser.add_argument(
        "--pre-ns",
        type=float,
        default=20.0,
        help="Time before threshold crossing in ns (default: 20)",
    )

    parser.add_argument(
        "--post-ns",
        type=float,
        default=100.0,
        help="Time after threshold crossing in ns (default: 100)",
    )

    parser.add_argument(
        "--no-image",
        action="store_true",
        help="Do not generate a PNG image",
    )

    parser.add_argument(
        "--no-csv",
        action="store_true",
        help="Do not generate a cropped CSV file",
    )

    return parser.parse_args()


def detect_channels(data):
    """Determine which channels are present in the NPZ capture."""

    if "channels" in data:
        channels = [
            int(ch)
            for ch in np.atleast_1d(data["channels"])
        ]

    else:
        channels = []

        for ch in range(1, 5):
            if f"ch{ch}_raw" in data:
                channels.append(ch)

    if not channels:
        raise ValueError(
            "No waveform channels were found in the capture."
        )

    return channels


def load_capture(filename):
    """Load NPZ and convert all available channels to volts."""

    data = np.load(filename)

    channels_present = detect_channels(data)

    xincr = float(data["xincr"])
    xzero = float(data["xzero"])
    pt_off = float(data["pt_off"])

    channels = {}

    for ch in channels_present:

        raw = data[f"ch{ch}_raw"]

        ymult = float(data[f"ch{ch}_ymult"])
        yoff = float(data[f"ch{ch}_yoff"])
        yzero = float(data[f"ch{ch}_yzero"])

        voltage = (
            (raw.astype(np.float64) - yoff)
            * ymult
            + yzero
        )

        channels[ch] = voltage

    first_channel = channels_present[0]
    npoints = len(channels[first_channel])

    for ch in channels_present:

        if len(channels[ch]) != npoints:
            raise ValueError(
                f"CH{ch} does not have the same number "
                "of samples as the other channels."
            )

    time_axis = (
        (np.arange(npoints, dtype=np.float64) - pt_off)
        * xincr
        + xzero
    )

    return (
        data,
        time_axis,
        channels,
        channels_present,
        xincr,
    )


def find_threshold_crossing(signal, threshold):
    """
    Find first threshold crossing.

    Positive threshold:
        previous sample < threshold
        current sample >= threshold

    Negative threshold:
        previous sample > threshold
        current sample <= threshold
    """

    if threshold >= 0:

        crossings = np.where(
            (signal[:-1] < threshold)
            & (signal[1:] >= threshold)
        )[0]

    else:

        crossings = np.where(
            (signal[:-1] > threshold)
            & (signal[1:] <= threshold)
        )[0]

    if len(crossings) == 0:
        return None

    return int(crossings[0] + 1)


def extract_window(
    time_axis,
    channels,
    event_index,
    xincr,
    pre_ns,
    post_ns,
):
    """Extract requested time range around the detected event."""

    pre_samples = int(
        np.ceil(
            (pre_ns * 1e-9)
            / xincr
        )
    )

    post_samples = int(
        np.ceil(
            (post_ns * 1e-9)
            / xincr
        )
    )

    start = max(
        0,
        event_index - pre_samples,
    )

    stop = min(
        len(time_axis),
        event_index + post_samples + 1,
    )

    event_time = time_axis[event_index]

    relative_time = (
        time_axis[start:stop]
        - event_time
    )

    cropped_channels = {}

    for ch, signal in channels.items():
        cropped_channels[ch] = signal[start:stop]

    return (
        relative_time,
        cropped_channels,
        start,
        stop,
    )


def save_csv(
    filename,
    relative_time,
    channels,
    channels_present,
):
    """Save cropped region to CSV."""

    columns = [
        relative_time * 1e9
    ]

    column_names = [
        "time_ns"
    ]

    for ch in channels_present:

        columns.append(
            channels[ch]
        )

        column_names.append(
            f"ch{ch}_v"
        )

    block = np.column_stack(
        columns
    )

    np.savetxt(
        filename,
        block,
        delimiter=",",
        header=",".join(column_names),
        comments="",
        fmt="%.10e",
    )


def save_image(
    filename,
    relative_time,
    channels,
    channels_present,
    detection_channel,
    threshold,
):
    """Plot extracted event region."""

    time_ns = (
        relative_time * 1e9
    )

    fig, ax = plt.subplots(
        figsize=(14, 8)
    )

    for ch in channels_present:

        ax.plot(
            time_ns,
            channels[ch],
            label=f"CH{ch}",
            linewidth=1.0,
        )

    ax.axvline(
        0.0,
        linestyle="--",
        linewidth=1.0,
        label="Detected crossing",
    )

    ax.axhline(
        threshold,
        linestyle=":",
        linewidth=1.0,
        label=(
            f"CH{detection_channel} threshold "
            f"({threshold:g} V)"
        ),
    )

    ax.set_xlabel(
        "Time relative to threshold crossing (ns)"
    )

    ax.set_ylabel(
        "Voltage (V)"
    )

    ax.set_title(
        filename.stem
    )

    ax.grid(
        True,
        alpha=0.3,
    )

    ax.legend()

    ax.margins(
        x=0
    )

    fig.tight_layout()

    fig.savefig(
        filename,
        dpi=150,
    )

    plt.close(fig)


def main():
    args = parse_args()

    print()
    print("--------------------------------------------------")
    print("MDO34 Event Window Extraction")
    print("--------------------------------------------------")
    print()

    print(
        f"Looking for input file:"
    )
    print(
        f"  {args.capture.resolve()}"
    )

    if not args.capture.exists():

        print()
        print("ERROR: Input file was not found.")
        print()

        raise FileNotFoundError(
            f"Capture does not exist: {args.capture}"
        )

    print(
        "File found."
    )

    if args.capture.suffix.lower() != ".npz":

        print()
        print(
            "ERROR: Input file is not an NPZ capture."
        )

        raise ValueError(
            "Input must be an .npz capture file."
        )

    if args.pre_ns < 0:

        raise ValueError(
            "--pre-ns must be >= 0"
        )

    if args.post_ns < 0:

        raise ValueError(
            "--post-ns must be >= 0"
        )

    print()
    print(
        "Loading capture..."
    )

    (
        data,
        time_axis,
        channels,
        channels_present,
        xincr,
    ) = load_capture(
        args.capture
    )

    print(
        "Capture loaded successfully."
    )

    print()

    print(
        "Available channels: "
        + ", ".join(
            f"CH{ch}"
            for ch in channels_present
        )
    )

    if args.channel not in channels_present:

        print()
        print(
            f"ERROR: CH{args.channel} is not present "
            "in this capture."
        )

        data.close()

        return

    sample_rate = 1.0 / xincr

    print()
    print("Detection settings:")
    print(
        f"  Detection channel: CH{args.channel}"
    )
    print(
        f"  Threshold:         {args.threshold:g} V"
    )
    print(
        f"  Pre-window:        {args.pre_ns:g} ns"
    )
    print(
        f"  Post-window:       {args.post_ns:g} ns"
    )
    print(
        f"  Sample rate:       "
        f"{sample_rate / 1e9:.6g} GS/s"
    )
    print(
        f"  Sample interval:   "
        f"{xincr * 1e9:.6g} ns"
    )

    print()
    print(
        "Searching for threshold crossing..."
    )

    detection_signal = channels[
        args.channel
    ]

    event_index = find_threshold_crossing(
        detection_signal,
        args.threshold,
    )

    if event_index is None:

        print()
        print(
            "No threshold crossing was found."
        )

        print(
            f"CH{args.channel} never crossed "
            f"{args.threshold:g} V "
            "in the requested direction."
        )

        print()

        print(
            f"Signal range:"
        )

        print(
            f"  Minimum: "
            f"{np.min(detection_signal):.6g} V"
        )

        print(
            f"  Maximum: "
            f"{np.max(detection_signal):.6g} V"
        )

        print()
        print(
            "No window was extracted."
        )

        data.close()
        return

    event_time = time_axis[
        event_index
    ]

    print()
    print(
        "Threshold crossing found."
    )

    print(
        f"  Sample index: {event_index:,}"
    )

    print(
        f"  Absolute time: "
        f"{event_time:.10e} s"
    )

    print(
        f"  Signal value: "
        f"{detection_signal[event_index]:.6g} V"
    )

    (
        relative_time,
        cropped_channels,
        start,
        stop,
    ) = extract_window(
        time_axis,
        channels,
        event_index,
        xincr,
        args.pre_ns,
        args.post_ns,
    )

    print()
    print(
        "Window found and extracted."
    )

    print(
        f"  Source samples: "
        f"{start:,} to {stop - 1:,}"
    )

    print(
        f"  Number of samples: "
        f"{stop - start:,}"
    )

    print(
        f"  Actual start: "
        f"{relative_time[0] * 1e9:.3f} ns"
    )

    print(
        f"  Actual end:   "
        f"{relative_time[-1] * 1e9:.3f} ns"
    )

    base = args.capture.with_suffix(
        ""
    )

    outputs_created = []

    print()
    print(
        "Generating outputs..."
    )

    if not args.no_csv:

        csv_file = Path(
            str(base)
            + "_window.csv"
        )

        save_csv(
            csv_file,
            relative_time,
            cropped_channels,
            channels_present,
        )

        outputs_created.append(
            csv_file
        )

        print(
            f"  CSV saved:"
        )

        print(
            f"    {csv_file.resolve()}"
        )

    else:

        print(
            "  CSV output disabled."
        )

    if not args.no_image:

        image_file = Path(
            str(base)
            + "_window.png"
        )

        save_image(
            image_file,
            relative_time,
            cropped_channels,
            channels_present,
            args.channel,
            args.threshold,
        )

        outputs_created.append(
            image_file
        )

        print(
            f"  Image saved:"
        )

        print(
            f"    {image_file.resolve()}"
        )

    else:

        print(
            "  Image output disabled."
        )

    print()

    if outputs_created:

        print(
            f"Finished successfully. "
            f"{len(outputs_created)} output file"
            f"{'' if len(outputs_created) == 1 else 's'} created."
        )

    else:

        print(
            "Finished. Window was found, but no outputs "
            "were requested."
        )

    print()

    data.close()


if __name__ == "__main__":
    main()