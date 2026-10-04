import sys


def run(operation):
    try:
        return operation()
    except (ValueError, OSError, ImportError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1) from None
    except KeyboardInterrupt:
        print("Cancelled", file=sys.stderr)
        raise SystemExit(130) from None
