#!/usr/bin/env python3

"""
Capture multiple triggered acquisitions from a Tektronix MDO34.

Requirements:
    pip install pyvisa pyvisa-py numpy

Examples:

    # Default:
    #   100 captures
    #   CH1-CH4 enabled
    #   trigger on CH1 at 0 V rising edge
    #   retain existing timebase/record length/vertical scales
    py ScopeCapture.py

    # Three captures, 10 us/div, 5 Mpoint record
    py ScopeCapture.py \
        -n 3 \
        --timebase 1e-5 \
        --record-length 5_000_000

    # Capture only CH1 and CH2
    py ScopeCapture.py \
        -n 10 \
        --channels 1 2

    # Trigger on CH2 at 0.5 V and capture CH1, CH2 and CH4
    py ScopeCapture.py \
        -n 100 \
        --channels 1 2 4 \
        --trigger-channel 2 \
        --trigger-level 0.5

    # Set all active channels to 200 mV/div
    py ScopeCapture.py \
        --vertical-scale 0.2

    # Individual vertical scales
    py ScopeCapture.py \
        --ch1-scale 2 \
        --ch2-scale 0.1 \
        --ch3-scale 0.1 \
        --ch4-scale 0.1


Output:

    captures/
        2026-10-06_13-15-27/
            capture_0001.npz
            capture_0002.npz
            ...

The script leaves acquisition settings unchanged unless explicitly
specified on the command line.
"""

import argparse
import time
import sys
from pathlib import Path
from datetime import datetime

import numpy as np
import pyvisa


# ----------------------------------------------------------------------
# Defaults
# ----------------------------------------------------------------------

DEFAULT_IP = "169.254.169.91"

VALID_RECORD_LENGTHS = [
    1_000,
    10_000,
    100_000,
    1_000_000,
    5_000_000,
    10_000_000,
]


# ----------------------------------------------------------------------
# Command-line arguments
# ----------------------------------------------------------------------

def parse_args():

    parser = argparse.ArgumentParser(
        description="Capture triggered waveforms from a Tektronix MDO34."
    )

    parser.add_argument(
        "--captures",
        "-n",
        type=int,
        default=100,
        help="Number of triggered acquisitions to collect (default: 100)",
    )

    parser.add_argument(
        "--trigger-level",
        "-l",
        type=float,
        default=0.0,
        help="Trigger level in volts (default: 0.0)",
    )

    parser.add_argument(
        "--trigger-channel",
        "-c",
        type=int,
        choices=[1, 2, 3, 4],
        default=1,
        help="Trigger source channel, 1-4 (default: 1)",
    )

    parser.add_argument(
        "--slope",
        choices=["rise", "fall"],
        default="rise",
        help="Trigger edge (default: rise)",
    )

    parser.add_argument(
        "--channels",
        type=int,
        nargs="+",
        choices=[1, 2, 3, 4],
        default=[1, 2, 3, 4],
        help=(
            "Analog channels to enable and capture. "
            "Example: --channels 1 2 4. "
            "Default: all four channels."
        ),
    )

    parser.add_argument(
        "--ip",
        default=DEFAULT_IP,
        help=f"Oscilloscope IP address (default: {DEFAULT_IP})",
    )

    parser.add_argument(
        "--output",
        "-o",
        default="captures",
        help="Base output directory (default: captures)",
    )

    # ------------------------------------------------------------------
    # Optional acquisition settings
    # ------------------------------------------------------------------

    parser.add_argument(
        "--timebase",
        type=float,
        default=None,
        help=(
            "Horizontal scale in seconds/division. "
            "Example: 1e-5 = 10 us/div. "
            "If omitted, the current scope setting is retained."
        ),
    )

    parser.add_argument(
        "--record-length",
        type=int,
        choices=VALID_RECORD_LENGTHS,
        default=None,
        help=(
            "Record length in samples/channel. "
            "Valid values: 1000, 10000, 100000, "
            "1000000, 5000000, 10000000. "
            "If omitted, the current scope setting is retained."
        ),
    )

    parser.add_argument(
        "--vertical-scale",
        type=float,
        default=None,
        help=(
            "Set all active channels to this vertical scale in V/div. "
            "Individual --chN-scale settings override this."
        ),
    )

    for ch in range(1, 5):

        parser.add_argument(
            f"--ch{ch}-scale",
            type=float,
            default=None,
            help=(
                f"CH{ch} vertical scale in V/div. "
                "Example: 0.1 = 100 mV/div."
            ),
        )

    return parser.parse_args()


# ----------------------------------------------------------------------
# Connection
# ----------------------------------------------------------------------

def connect_scope(ip):

    rm = pyvisa.ResourceManager("@py")

    resource = f"TCPIP::{ip}::INSTR"

    print(f"Connecting to {resource}...")

    scope = rm.open_resource(resource)

    # Large waveform transfers may take some time.
    scope.timeout = 120_000

    # Increase PyVISA read chunk size for large binary transfers.
    scope.chunk_size = 1024 * 1024

    identity = scope.query("*IDN?").strip()

    print(f"Connected: {identity}")

    return rm, scope


# ----------------------------------------------------------------------
# Scope configuration
# ----------------------------------------------------------------------

def configure_scope(scope, args):

    print("Configuring scope...")

    # Stop acquisition before changing configuration.
    scope.write("ACQUIRE:STATE STOP")

    # ------------------------------------------------------------------
    # Channel enable / disable
    # ------------------------------------------------------------------

    for ch in range(1, 5):

        if ch in args.channels:
            scope.write(f"SELECT:CH{ch} ON")
        else:
            scope.write(f"SELECT:CH{ch} OFF")

    # ------------------------------------------------------------------
    # Horizontal configuration
    # ------------------------------------------------------------------

    if args.record_length is not None:

        scope.write(
            f"HORIZONTAL:RECORDLENGTH {args.record_length}"
        )

    if args.timebase is not None:

        scope.write(
            f"HORIZONTAL:SCALE {args.timebase}"
        )

    # ------------------------------------------------------------------
    # Vertical scales
    # ------------------------------------------------------------------

    for ch in args.channels:

        individual_scale = getattr(
            args,
            f"ch{ch}_scale",
        )

        if individual_scale is not None:

            scale = individual_scale

        elif args.vertical_scale is not None:

            scale = args.vertical_scale

        else:

            scale = None

        if scale is not None:

            if scale <= 0:
                raise ValueError(
                    f"CH{ch} vertical scale must be > 0"
                )

            scope.write(
                f"CH{ch}:SCALE {scale}"
            )

    # ------------------------------------------------------------------
    # Trigger
    # ------------------------------------------------------------------

    scope.write(
        "TRIGGER:A:TYPE EDGE"
    )

    scope.write(
        f"TRIGGER:A:EDGE:SOURCE CH{args.trigger_channel}"
    )

    scope.write(
        "TRIGGER:A:EDGE:COUPLING DC"
    )

    if args.slope == "rise":

        scope.write(
            "TRIGGER:A:EDGE:SLOPE RISE"
        )

    else:

        scope.write(
            "TRIGGER:A:EDGE:SLOPE FALL"
        )

    scope.write(
        f"TRIGGER:A:LEVEL:CH{args.trigger_channel} "
        f"{args.trigger_level}"
    )

    # NORMAL prevents the scope from generating an acquisition
    # automatically when no valid trigger occurs.
    scope.write(
        "TRIGGER:A:MODE NORMAL"
    )

    # One acquisition each time the scope is armed.
    scope.write(
        "ACQUIRE:STOPAFTER SEQUENCE"
    )

    scope.write(
        "ACQUIRE:SEQUENCE:NUMSEQUENCE 1"
    )

    # ------------------------------------------------------------------
    # Waveform transfer format
    # ------------------------------------------------------------------

    # Signed binary integer.
    scope.write(
        "DATA:ENCDG RIBINARY"
    )

    # 16-bit samples.
    scope.write(
        "DATA:WIDTH 2"
    )

    # ------------------------------------------------------------------
    # Query actual resulting configuration
    # ------------------------------------------------------------------

    settings = get_scope_settings(
        scope,
        args.channels,
    )

    print()
    print("Acquisition settings:")

    print(
        f"  Timebase:       "
        f"{settings['timebase']:.6g} s/div"
    )

    print(
        f"  Record length:  "
        f"{settings['record_length']:,} points"
    )

    print(
        f"  Sample rate:    "
        f"{settings['sample_rate'] / 1e9:.6g} GS/s"
    )

    print()

    print(
        "  Active channels: "
        + ", ".join(
            f"CH{ch}"
            for ch in args.channels
        )
    )

    for ch in args.channels:

        print(
            f"  CH{ch} scale:       "
            f"{settings[f'ch{ch}_scale']:.6g} V/div"
        )

    print()

    print(
        f"Trigger: CH{args.trigger_channel}, "
        f"{args.trigger_level:g} V, "
        f"{args.slope.upper()} edge"
    )

    print()

    return settings


# ----------------------------------------------------------------------
# Read current scope settings
# ----------------------------------------------------------------------

def get_scope_settings(scope, channels):

    settings = {}

    settings["timebase"] = float(
        scope.query(
            "HORIZONTAL:SCALE?"
        )
    )

    settings["record_length"] = int(
        float(
            scope.query(
                "HORIZONTAL:RECORDLENGTH?"
            )
        )
    )

    settings["sample_rate"] = float(
        scope.query(
            "HORIZONTAL:SAMPLERATE?"
        )
    )

    for ch in channels:

        settings[f"ch{ch}_scale"] = float(
            scope.query(
                f"CH{ch}:SCALE?"
            )
        )

    return settings


# ----------------------------------------------------------------------
# Trigger / acquisition
# ----------------------------------------------------------------------

def wait_for_trigger(scope):

    # Arm the scope.
    scope.write(
        "ACQUIRE:STATE RUN"
    )

    # In single-sequence mode the state returns to zero once
    # the triggered acquisition has completed.
    while True:

        state = int(
            float(
                scope.query(
                    "ACQUIRE:STATE?"
                ).strip()
            )
        )

        if state == 0:
            return

        time.sleep(0.1)


# ----------------------------------------------------------------------
# Waveform download
# ----------------------------------------------------------------------

def read_channel(scope, channel):

    """
    Download the complete acquisition record for one channel.

    DATA:STOP does not automatically track acquisition record length,
    so the full desired transfer range must be set explicitly before
    querying WFMOUTPRE:NR_PT?.
    """

    scope.write(
        f"DATA:SOURCE CH{channel}"
    )

    # Get actual acquisition record length.
    record_length = int(
        float(
            scope.query(
                "HORIZONTAL:RECORDLENGTH?"
            )
        )
    )

    # Explicitly select the complete acquisition for transfer.
    scope.write(
        "DATA:START 1"
    )

    scope.write(
        f"DATA:STOP {record_length}"
    )

    # NR_PT now represents the number of points CURVE? should return.
    npoints = int(
        float(
            scope.query(
                "WFMOUTPRE:NR_PT?"
            )
        )
    )

    # ------------------------------------------------------------------
    # Waveform scaling information
    # ------------------------------------------------------------------

    xincr = float(
        scope.query(
            "WFMOUTPRE:XINCR?"
        )
    )

    xzero = float(
        scope.query(
            "WFMOUTPRE:XZERO?"
        )
    )

    pt_off = float(
        scope.query(
            "WFMOUTPRE:PT_OFF?"
        )
    )

    ymult = float(
        scope.query(
            "WFMOUTPRE:YMULT?"
        )
    )

    yoff = float(
        scope.query(
            "WFMOUTPRE:YOFF?"
        )
    )

    yzero = float(
        scope.query(
            "WFMOUTPRE:YZERO?"
        )
    )

    # ------------------------------------------------------------------
    # Transfer waveform
    # ------------------------------------------------------------------

    raw = scope.query_binary_values(
        "CURVE?",
        datatype="h",
        is_big_endian=True,
        container=np.array,
    )

    raw = raw.astype(
        np.int16,
        copy=False,
    )

    # Sanity check against truncated transfers.
    if len(raw) != npoints:

        raise RuntimeError(
            f"CH{channel}: expected {npoints:,} points, "
            f"but received {len(raw):,}"
        )

    return {
        "raw": raw,
        "npoints": npoints,
        "xincr": xincr,
        "xzero": xzero,
        "pt_off": pt_off,
        "ymult": ymult,
        "yoff": yoff,
        "yzero": yzero,
    }


# ----------------------------------------------------------------------
# Download all selected channels
# ----------------------------------------------------------------------

def capture(scope, channels):

    result = {}

    for ch in channels:

        print(
            f"    Downloading CH{ch}...",
            end="",
            flush=True,
        )

        data = read_channel(
            scope,
            ch,
        )

        result[f"ch{ch}"] = data

        print(
            f" {len(data['raw']):,} points"
        )

    return result


# ----------------------------------------------------------------------
# Save acquisition
# ----------------------------------------------------------------------

def save_capture(
    data,
    filename,
    metadata,
    settings,
    channels,
):

    first_channel = channels[0]

    arrays = {
        # Which channels are present in this file
        "channels": np.array(
            channels,
            dtype=np.int8,
        ),

        # Horizontal waveform scaling
        "xincr": data[
            f"ch{first_channel}"
        ]["xincr"],

        "xzero": data[
            f"ch{first_channel}"
        ]["xzero"],

        "pt_off": data[
            f"ch{first_channel}"
        ]["pt_off"],

        # Trigger information
        "trigger_channel":
            metadata["trigger_channel"],

        "trigger_level":
            metadata["trigger_level"],

        "trigger_slope":
            metadata["trigger_slope"],

        "timestamp":
            metadata["timestamp"],

        # Acquisition configuration
        "timebase_s_per_div":
            settings["timebase"],

        "record_length":
            settings["record_length"],

        "sample_rate":
            settings["sample_rate"],
    }

    # Add each active channel dynamically.
    for ch in channels:

        ch_data = data[
            f"ch{ch}"
        ]

        arrays[
            f"ch{ch}_raw"
        ] = ch_data["raw"]

        arrays[
            f"ch{ch}_ymult"
        ] = ch_data["ymult"]

        arrays[
            f"ch{ch}_yoff"
        ] = ch_data["yoff"]

        arrays[
            f"ch{ch}_yzero"
        ] = ch_data["yzero"]

        arrays[
            f"ch{ch}_scale_v_per_div"
        ] = settings[
            f"ch{ch}_scale"
        ]

    # Uncompressed NPZ is intentional:
    # scope waveform data generally does not compress especially
    # efficiently and compression slows the save operation.
    np.savez(
        filename,
        **arrays,
    )


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

def save_session_info(
    output_dir,
    scope,
    args,
    settings,
):
    """
    Save capture-session configuration to a human-readable text file.
    """

    filename = output_dir / "capture_settings.txt"

    instrument_id = scope.query("*IDN?").strip()

    start_time = datetime.now().isoformat(
        timespec="seconds"
    )

    lines = [
        "Tektronix MDO34 Capture Session",
        "================================",
        "",
        f"Session started: {start_time}",
        f"Instrument:      {instrument_id}",
        "",
        "Command",
        "-------",
        " ".join(sys.argv),
        "",
        "Capture settings",
        "----------------",
        f"Number of captures: {args.captures}",
        "",
        "Active channels:",
        "  " + ", ".join(
            f"CH{ch}" for ch in args.channels
        ),
        "",
        "Trigger",
        "-------",
        f"Channel: CH{args.trigger_channel}",
        f"Level:   {args.trigger_level:g} V",
        f"Slope:   {args.slope.upper()}",
        "",
        "Horizontal acquisition",
        "----------------------",
        f"Timebase:       {settings['timebase']:.10g} s/div",
        f"Record length:  {settings['record_length']:,} points/channel",
        f"Sample rate:    {settings['sample_rate']:.10g} samples/s",
        f"Sample rate:    {settings['sample_rate'] / 1e9:.6g} GS/s",
        "",
        "Vertical settings",
        "-----------------",
    ]

    for ch in args.channels:
        lines.append(
            f"CH{ch} scale: {settings[f'ch{ch}_scale']:.10g} V/div"
        )

    lines.extend(
        [
            "",
            "Requested command-line acquisition settings",
            "-------------------------------------------",
            (
                f"Requested timebase: "
                f"{args.timebase if args.timebase is not None else 'unchanged'}"
            ),
            (
                f"Requested record length: "
                f"{args.record_length if args.record_length is not None else 'unchanged'}"
            ),
            (
                f"Requested common vertical scale: "
                f"{args.vertical_scale if args.vertical_scale is not None else 'unchanged'}"
            ),
        ]
    )

    for ch in range(1, 5):

        requested_scale = getattr(
            args,
            f"ch{ch}_scale",
        )

        lines.append(
            f"Requested CH{ch} scale: "
            f"{requested_scale if requested_scale is not None else 'unchanged'}"
        )

    lines.extend(
        [
            "",
            f"Scope IP: {args.ip}",
            f"Output directory: {output_dir.resolve()}",
            "",
        ]
    )

    with open(
        filename,
        "w",
        encoding="utf-8",
    ) as f:
        f.write(
            "\n".join(lines)
        )

    print(
        f"Capture settings saved to: {filename.resolve()}"
    )

def main():

    args = parse_args()

    # ------------------------------------------------------------------
    # Validate arguments
    # ------------------------------------------------------------------

    if args.captures < 1:

        raise ValueError(
            "--captures must be at least 1"
        )

    # Remove duplicate channel entries while preserving order.
    args.channels = list(
        dict.fromkeys(
            args.channels
        )
    )

    if args.trigger_channel not in args.channels:

        raise ValueError(
            f"Trigger channel CH{args.trigger_channel} "
            f"is not enabled. "
            f"Enabled channels: "
            + ", ".join(
                f"CH{ch}"
                for ch in args.channels
            )
        )

    if args.timebase is not None:

        if args.timebase <= 0:

            raise ValueError(
                "--timebase must be > 0"
            )

    if args.vertical_scale is not None:

        if args.vertical_scale <= 0:

            raise ValueError(
                "--vertical-scale must be > 0"
            )

    # ------------------------------------------------------------------
    # Create unique capture-session directory
    # ------------------------------------------------------------------

    base_output_dir = Path(
        args.output
    )

    run_timestamp = datetime.now().strftime(
        "%Y-%m-%d_%H-%M-%S"
    )

    output_dir = (
        base_output_dir
        / run_timestamp
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=False,
    )

    print(
        f"Capture session directory: "
        f"{output_dir.resolve()}"
    )

    # ------------------------------------------------------------------
    # Connect and capture
    # ------------------------------------------------------------------

    rm = None
    scope = None

    try:

        rm, scope = connect_scope(
            args.ip
        )

        settings = configure_scope(
            scope,
            args,
        )

        save_session_info(
            output_dir,
            scope,
            args,
            settings,
        )

        print(
            f"Collecting {args.captures} captures."
        )

        print(
            "Waiting for first trigger..."
        )

        print()

        for index in range(
            1,
            args.captures + 1,
        ):

            print(
                f"[{index}/{args.captures}] "
                f"Armed - waiting for trigger..."
            )

            wait_for_trigger(
                scope
            )

            print(
                "    Triggered."
            )

            capture_timestamp = (
                datetime.now().isoformat(
                    timespec="milliseconds"
                )
            )

            data = capture(
                scope,
                args.channels,
            )

            filename = (
                output_dir
                / f"capture_{index:04d}.npz"
            )

            metadata = {
                "trigger_channel":
                    args.trigger_channel,

                "trigger_level":
                    args.trigger_level,

                "trigger_slope":
                    args.slope,

                "timestamp":
                    capture_timestamp,
            }

            save_capture(
                data,
                filename,
                metadata,
                settings,
                args.channels,
            )

            # ----------------------------------------------------------
            # Print actual waveform characteristics on first capture
            # ----------------------------------------------------------

            if index == 1:

                first_channel = (
                    args.channels[0]
                )

                dt = data[
                    f"ch{first_channel}"
                ]["xincr"]

                actual_sample_rate = (
                    1.0 / dt
                )

                actual_points = len(
                    data[
                        f"ch{first_channel}"
                    ]["raw"]
                )

                actual_duration = (
                    actual_points
                    * dt
                )

                print(
                    f"    Sample interval: "
                    f"{dt:.6g} s"
                )

                print(
                    f"    Waveform sample rate: "
                    f"{actual_sample_rate / 1e9:.6g} GS/s"
                )

                print(
                    f"    Captured duration: "
                    f"{actual_duration:.6g} s"
                )

            print(
                f"    Saved: {filename}"
            )

            print()

        print(
            f"Finished. "
            f"{args.captures} acquisitions saved to "
            f"{output_dir.resolve()}"
        )

    except KeyboardInterrupt:

        print(
            "\nCapture stopped by user."
        )

    finally:

        if scope is not None:

            try:

                scope.write(
                    "ACQUIRE:STATE STOP"
                )

                scope.close()

            except Exception:
                pass

        if rm is not None:

            rm.close()


if __name__ == "__main__":
    main()