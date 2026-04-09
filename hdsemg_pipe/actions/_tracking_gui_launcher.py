"""
Subprocess launcher for the openhdemg Tracking_gui.

This script is intentionally separate from the main hdsemg-pipe process so
that the Tkinter-based openhdemg GUI can run as the *only* GUI toolkit in a
dedicated Python process.  Running Tkinter alongside PyQt5 in the same process
on macOS is not supported (both require exclusive ownership of the main thread).

Invocation (internal — do not call directly):

    python _tracking_gui_launcher.py <input_pickle> <output_pickle>

The input pickle must be created by
``duplicate_detection_openhdemg._show_tracking_gui_subprocess``.
The output pickle will contain the updated tracking DataFrame, with an
``Inclusion`` column added by the GUI (values "Included" / "Excluded").
"""

import pickle
import sys


def main() -> None:
    if len(sys.argv) != 3:
        print(
            f"Usage: {sys.argv[0]} <input_pickle> <output_pickle>",
            file=sys.stderr,
        )
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2]

    # nosec: both files are written and read within the same user session;
    # this is local IPC, not deserialization of untrusted network data.
    with open(input_path, "rb") as fh:
        params: dict = pickle.load(fh)  # nosec B301

    try:
        from openhdemg.library.muap import tracking
    except ImportError as exc:
        print(f"openhdemg not available: {exc}", file=sys.stderr)
        sys.exit(2)

    result = tracking(
        emgfile1=params["emgfile1"],
        emgfile2=params["emgfile2"],
        gui=True,
        show=False,
        **params["kwargs"],
    )

    with open(output_path, "wb") as fh:
        pickle.dump(result, fh)  # nosec B301


if __name__ == "__main__":
    main()
