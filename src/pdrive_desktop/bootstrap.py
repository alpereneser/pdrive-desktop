from __future__ import annotations

import sys


def main() -> int:
    try:
        import gi

        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        from pdrive_desktop.presentation.app import run
    except (ImportError, ValueError) as error:
        print("GTK4/libadwaita runtime is required to start PDrive Desktop.", file=sys.stderr)
        print(str(error), file=sys.stderr)
        return 2
    return run()


if __name__ == "__main__":
    raise SystemExit(main())

