"""Launch live routing from a source checkout, including an external cwd."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] not in {"serve", "hook"}:
        print("Usage: live_entry.py {serve|hook} --config PATH [options]", file=sys.stderr)
        return 2
    mode = args.pop(0)
    if mode == "serve":
        from human_eye_plugin.live_spatial_mcp import main as entry
    else:
        from human_eye_hook import main as entry
    return entry(args)


if __name__ == "__main__":
    raise SystemExit(main())
