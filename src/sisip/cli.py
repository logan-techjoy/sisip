"""Local diagnostic CLI. Diagnostic JSON may contain text; wire CBOR does not."""
import argparse
import json
from pathlib import Path
from .cbor import ProtocolError
from .protocol import encode, decode, digest
from .demo import example_message, run_demo


def diagnostic(value):
    if type(value) is bytes:
        return {"bytes_hex": value.hex()}
    if type(value) is dict:
        return {str(k): diagnostic(v) for k, v in value.items()}
    if type(value) is list:
        return [diagnostic(v) for v in value]
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description="SISIP v1.0 core diagnostics")
    sub = parser.add_subparsers(dest="command", required=True)
    example = sub.add_parser("example", help="write deterministic example CBOR")
    example.add_argument("output", type=Path)
    check = sub.add_parser("inspect", help="verify integrity/schema and print diagnostic JSON")
    check.add_argument("input", type=Path)
    sub.add_parser("demo", help="run task -> handoff -> result -> final-output gate")
    args = parser.parse_args(argv)
    try:
        if args.command == "example":
            message = example_message()
            data = encode(message)
            args.output.write_bytes(data)
            print(json.dumps({"bytes": len(data), "payload_sha256": digest(message).hex()}))
        elif args.command == "inspect":
            # Read at most the supported limit plus one byte, even for huge input.
            from .cbor import MAX_BYTES
            with args.input.open("rb") as source:
                wire = source.read(MAX_BYTES + 1)
            print(json.dumps(diagnostic(decode(wire)), indent=2))
        else:
            final, history = run_demo()
            print(json.dumps({"executed_message_kinds": [m[5] for m in history],
                              "final_output_allowed": final[5] == 2,
                              "note": "deterministic adapters; no model inference"}, indent=2))
    except (ProtocolError, OSError) as exc:
        parser.exit(1, f"sisip: {exc}\n")


if __name__ == "__main__":
    main()
