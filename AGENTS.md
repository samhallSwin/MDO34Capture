# Project Guidelines

## Project workflow

This project captures triggered waveforms from a Tektronix MDO34 oscilloscope, stores each acquisition as an NPZ file, then converts or crops captures for analysis.

- [`ScopeCapture.py`](./ScopeCapture.py) configures the scope over PyVISA/TCPIP and saves timestamped capture sessions under `captures/` by default. It leaves timebase, record length, and vertical scales unchanged unless corresponding options are supplied.
- [`ProcessCapture.py`](./ProcessCapture.py) accepts one NPZ file or a directory of NPZ files and produces full-resolution CSV data and/or waveform PNGs. Plot decimation does not reduce CSV resolution.
- [`ExtractEventWindow.py`](./ExtractEventWindow.py) finds the first threshold crossing in one channel and exports a time-relative cropped CSV and/or PNG.
- [`ScopeTest.py`](./ScopeTest.py) is a small PyVISA connectivity/identity check.
- [`readme.md`](./readme.md) documents the point-to-point Ethernet setup and capture workflow. In particular, the scope's sample rate is selected from its available settings; timebase and record length are the controls used here.

## Data compatibility

- Treat the NPZ format written by `ScopeCapture.py` as the shared interface for the processing scripts. It contains raw samples, waveform scaling values, time-axis values, active-channel metadata, trigger metadata, and acquisition settings.
- Convert raw samples to volts using the stored per-channel scaling metadata, and derive time from `xincr`, `xzero`, and `pt_off`. Preserve compatibility with older captures that may not contain the `channels` array; both processing scripts currently detect channels from `chN_raw` keys in that case.
- Keep captures uncompressed unless there is a measured reason to change this: `ScopeCapture.py` intentionally uses uncompressed NPZ to avoid slowing acquisition saves.

## Development and validation

- The scripts are standalone Python CLIs; there is no package manifest or automated test suite in the repository.
- Runtime dependencies are NumPy and Matplotlib for processing, and PyVISA with the `pyvisa-py` backend for scope capture. `ScopeTest.py` only needs PyVISA and its backend.
- For CLI-only changes, run the affected script with `--help` and perform focused offline checks where practical. Do not require a connected oscilloscope for offline processing changes.
- Scope capture and `ScopeTest.py` communicate with physical hardware. Do not run them as validation unless a connected MDO34 is intentionally available.
- Keep changes focused on the relevant script and preserve its existing command-line options, output naming, and capture-file behavior.
