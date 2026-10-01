"""What Marchlands.exe actually runs.

A thin front door, and it exists for one reason: a windowed build has nowhere
to print a traceback. If anything goes wrong before the browser opens -- a
port in use, a missing bundle, a permissions refusal -- the process would
simply vanish, and the player would have double-clicked something that did
nothing at all. So this catches whatever happens and puts it somewhere they
can actually read it.
"""

from __future__ import annotations

import os
import sys
import traceback


def _complain(text: str) -> None:
    """Say what went wrong, in whatever way this machine has of saying it."""
    sys.stderr.write(text + "\n")
    try:                                    # Windows: a real message box
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, "Marchlands", 0x10)
        return
    except Exception:
        pass
    # tkinter is in the spec's `excludes` -- it is several megabytes for a
    # dialog Windows already has -- so this branch only fires when somebody
    # runs launch.py from a checkout. In the packaged build the import fails
    # and the file below is what a non-Windows player actually gets.
    try:                                    # anywhere else with a display
        import tkinter
        from tkinter import messagebox
        root = tkinter.Tk()
        root.withdraw()
        messagebox.showerror("Marchlands", text)
        return
    except Exception:
        pass
    # Nothing to show it on: leave it beside the executable instead.
    try:
        where = os.path.join(os.path.dirname(sys.executable),
                             "marchlands-error.txt")
        with open(where, "w", encoding="utf-8") as fh:
            fh.write(text)
    except Exception:
        pass


def main() -> int:
    try:
        from marchlands.__main__ import main as run
        return run()
    except SystemExit as exc:               # argparse --help and friends
        return int(exc.code or 0)
    except Exception:
        _complain(
            "Marchlands could not start.\n\n"
            + traceback.format_exc()
            + "\nIf the port is in use, run it from a terminal with "
              "--port 9000.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
