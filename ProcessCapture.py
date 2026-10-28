#!/usr/bin/env python3

"""
Convert Tektronix MDO34 capture .npz files to PNG and/or CSV.

The input may be either:
    - a single .npz capture file
    - a directory containing .npz capture files

The script automatically detects which channels are present in each capture.

Examples:

    # Process one capture
    py ProcessCapture.py captures/capture_0001.npz

    # Process every .npz capture in a folder
    py ProcessCapture.py captures/2026-10-06_12-54-40

    # Folder: images only
    py ProcessCapture.py captures/2026-10-06_12-54-40 --no-csv

    # Folder: CSV only
    py ProcessCapture.py captures/2026-10-06_12-54-40 --no-image

    # Limit plots to 100,000 points/channel
    py ProcessCapture.py captures/2026-10-06_12-54-40 \
        --max-plot-points 100000

Requirements:
    pip install numpy matplotlib
"""

import argparse
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt


# ----------------------------------------------------------------------
# Command-line arguments
# ----------------------------------------------------------------------

def parse_args():

    parser = argparse.ArgumentParser(
        description=(
            "Convert MDO34 NPZ capture(s) to image and/or CSV. "
            "Input may be a capture file or a directory."
        )
    )

    parser.add_argument(
        "input",
        type=Path,
        help=(
            "Capture .npz file or directory containing .npz captures."
        ),
    )

    parser.add_argument(
        "--no-image",
        action="store_true",
        help="Do not generate PNG waveform images.",
    )

    parser.add_argument(
        "--no-csv",
        action="store_true",
        help="Do not generate CSV files.",
    )

    parser.add_argument(
        "--max-plot-points",
        type=int,
        default=200_000,
        help=(
            "Maximum number of points per channel to draw in each image "
            "(default: 200000). "
            "CSV output always contains full-resolution data."
        ),
    )

    return parser.parse_args()


# ----------------------------------------------------------------------
# Capture discovery
# ----------------------------------------------------------------------

def find_capture_files(input_path):
    """
    Return a sorted list of capture files.

    If input_path is a file, return that file only.

    If input_path is a directory, return all .npz files directly
    contained in that directory.
    """

    if not input_path.exists():

        raise FileNotFoundError(
            f"Input does not exist: {input_path}"
        )

    if input_path.is_file():

        if input_path.suffix.lower() != ".npz":

            raise ValueError(
                "Input file must be a .npz capture file."
            )

        return [input_path]

    if input_path.is_dir():

        captures = sorted(
            input_path.glob("*.npz")
        )

        if not captures:

            raise FileNotFoundError(
                f"No .npz capture files found in: {input_path}"
            )

        return captures

    raise ValueError(
        f"Input is neither a file nor a directory: {input_path}"
    )


# ----------------------------------------------------------------------
# Channel detection
# ----------------------------------------------------------------------

def detect_channels(data):
    """
    Determine which analog channels are present in the capture.

    New capture files contain a 'channels' array.

    For compatibility with older capture files, fall back to searching
    for ch1_raw, ch2_raw, etc.
    """

    if "channels" in data:

        channels = [
            int(ch)
            for ch in np.atleast_1d(
                data["channels"]
            )
        ]

    else:

        channels = []

        for ch in range(1, 5):

            if f"ch{ch}_raw" in data:
                channels.append(ch)

    if not channels:

        raise ValueError(
            "No channel waveform data was found in the capture."
        )

    return channels


# ----------------------------------------------------------------------
# Capture loading
# ----------------------------------------------------------------------

def load_capture(filename):
    """
    Load capture and reconstruct time and voltage arrays.

    Only channels actually stored in the capture are processed.
    """

    data = np.load(filename)

    channels_present = detect_channels(
        data
    )

    xincr = float(
        data["xincr"]
    )

    xzero = float(
        data["xzero"]
    )

    pt_off = float(
        data["pt_off"]
    )

    channels = {}

    for ch in channels_present:

        raw = data[
            f"ch{ch}_raw"
        ]

        ymult = float(
            data[f"ch{ch}_ymult"]
        )

        yoff = float(
            data[f"ch{ch}_yoff"]
        )

        yzero = float(
            data[f"ch{ch}_yzero"]
        )

        voltage = (
            (
                raw.astype(np.float64)
                - yoff
            )
            * ymult
            + yzero
        )

        channels[ch] = voltage

    first_channel = channels_present[0]

    npoints = len(
        channels[first_channel]
    )

    # Verify all channels contain the same number of samples.
    for ch in channels_present:

        if len(channels[ch]) != npoints:

            raise ValueError(
                f"Channel length mismatch: "
                f"CH{first_channel} has {npoints:,} points, "
                f"but CH{ch} has {len(channels[ch]):,}."
            )

    # Tektronix waveform time scaling.
    time_axis = (
        (
            np.arange(
                npoints,
                dtype=np.float64,
            )
            - pt_off
        )
        * xincr
        + xzero
    )

    return (
        data,
        time_axis,
        channels,
        channels_present,
    )


# ----------------------------------------------------------------------
# Image output
# ----------------------------------------------------------------------

def save_image(
    filename,
    time_axis,
    channels,
    channels_present,
    max_plot_points,
):
    """
    Save waveform image.

    Large acquisitions are decimated for plotting only.
    The underlying capture and CSV remain full resolution.
    """

    npoints = len(
        time_axis
    )

    if npoints > max_plot_points:

        step = int(
            np.ceil(
                npoints
                / max_plot_points
            )
        )

    else:

        step = 1

    plot_time = time_axis[
        ::step
    ]

    fig, ax = plt.subplots(
        figsize=(14, 8)
    )

    for ch in channels_present:

        ax.plot(
            plot_time,
            channels[ch][::step],
            label=f"CH{ch}",
            linewidth=0.8,
        )

    ax.set_xlabel(
        "Time (s)"
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

    plt.close(
        fig
    )

    print(
        f"  Saved image: {filename.name} "
        f"({len(plot_time):,} plotted points/channel)"
    )


# ----------------------------------------------------------------------
# CSV output
# ----------------------------------------------------------------------

def save_csv(
    filename,
    time_axis,
    channels,
    channels_present,
    chunk_size=100_000,
):
    """
    Save full-resolution CSV.

    Columns are created dynamically based on the channels present.

    Data is written in chunks so a multi-million-point acquisition does
    not require constructing the entire CSV representation in memory.
    """

    npoints = len(
        time_axis
    )

    print(
        f"  Writing CSV: {filename.name}"
    )

    print(
        f"    {npoints:,} rows"
    )

    column_names = [
        "time_s"
    ]

    column_names.extend(
        f"ch{ch}_v"
        for ch in channels_present
    )

    with open(
        filename,
        "w",
        newline="",
    ) as f:

        f.write(
            ",".join(
                column_names
            )
            + "\n"
        )

        for start in range(
            0,
            npoints,
            chunk_size,
        ):

            stop = min(
                start + chunk_size,
                npoints,
            )

            columns = [
                time_axis[
                    start:stop
                ]
            ]

            for ch in channels_present:

                columns.append(
                    channels[ch][
                        start:stop
                    ]
                )

            block = np.column_stack(
                columns
            )

            np.savetxt(
                f,
                block,
                delimiter=",",
                fmt="%.10e",
            )

            print(
                f"\r    Written "
                f"{stop:,} / {npoints:,}",
                end="",
                flush=True,
            )

    print()

    print(
        f"  Saved CSV: {filename.name}"
    )


# ----------------------------------------------------------------------
# Process one capture
# ----------------------------------------------------------------------

def process_capture(
    capture_file,
    create_image,
    create_csv,
    max_plot_points,
):
    """
    Process a single capture file.
    """

    print()
    print(
        f"Processing: {capture_file}"
    )

    (
        data,
        time_axis,
        channels,
        channels_present,
    ) = load_capture(
        capture_file
    )

    npoints = len(
        time_axis
    )

    sample_interval = float(
        data["xincr"]
    )

    sample_rate = (
        1.0
        / sample_interval
    )

    if npoints > 1:

        duration = (
            time_axis[-1]
            - time_axis[0]
        )

    else:

        duration = 0.0

    print(
        "  Channels:       "
        + ", ".join(
            f"CH{ch}"
            for ch in channels_present
        )
    )

    print(
        f"  Points/channel: "
        f"{npoints:,}"
    )

    print(
        f"  Sample rate:    "
        f"{sample_rate / 1e9:.6g} GS/s"
    )

    print(
        f"  Duration:       "
        f"{duration:.6g} s"
    )

    if (
        "trigger_channel" in data
        and "trigger_level" in data
    ):

        trigger_text = (
            f"CH{int(data['trigger_channel'])}, "
            f"{float(data['trigger_level']):g} V"
        )

        if "trigger_slope" in data:

            trigger_text += (
                f", "
                f"{str(data['trigger_slope']).upper()}"
            )

        print(
            f"  Trigger:        "
            f"{trigger_text}"
        )

    if "timestamp" in data:

        print(
            f"  Captured:       "
            f"{str(data['timestamp'])}"
        )

    base = capture_file.with_suffix(
        ""
    )

    if create_image:

        image_file = base.with_suffix(
            ".png"
        )

        save_image(
            image_file,
            time_axis,
            channels,
            channels_present,
            max_plot_points,
        )

    if create_csv:

        csv_file = base.with_suffix(
            ".csv"
        )

        save_csv(
            csv_file,
            time_axis,
            channels,
            channels_present,
        )

    # Explicitly close the NPZ file.
    data.close()


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

def main():

    args = parse_args()

    if args.no_image and args.no_csv:

        print(
            "Both image and CSV output are disabled. "
            "Nothing to do."
        )

        return

    if args.max_plot_points < 1:

        raise ValueError(
            "--max-plot-points must be at least 1."
        )

    capture_files = find_capture_files(
        args.input
    )

    print(
        f"Found {len(capture_files)} capture"
        f"{'' if len(capture_files) == 1 else 's'}."
    )

    create_image = not args.no_image
    create_csv = not args.no_csv

    successful = 0
    failed = 0

    for index, capture_file in enumerate(
        capture_files,
        start=1,
    ):

        print()
        print(
            f"[{index}/{len(capture_files)}]"
        )

        try:

            process_capture(
                capture_file,
                create_image,
                create_csv,
                args.max_plot_points,
            )

            successful += 1

        except Exception as exc:

            failed += 1

            print(
                f"  ERROR: {exc}"
            )

    print()
    print(
        "Finished."
    )

    print(
        f"  Successful: {successful}"
    )

    if failed:

        print(
            f"  Failed:     {failed}"
        )


if __name__ == "__main__":
    main()