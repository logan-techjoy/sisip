# Changelog

## 1.0.2 — 2026-11-06

Wire format and protocol version `[1, 0]` are unchanged.

- `make_message` raises `ProtocolError`, not `TypeError`, for non-sequence or
  non-integer roots and for non-integer node IDs.
- `MANIFEST.sha256` lists only tracked files. The 1.0.1 manifest also listed six
  local `__pycache__` files that are not part of the source.

## 1.0.1 — 2026-11-06

Wire format and protocol version `[1, 0]` are unchanged; the conformance fixture
is byte-identical.

- `make_message` puts only the concepts a graph uses (plus any `required`
  handles) into the message dictionary. `required` now defaults to empty instead
  of marking every registry concept as sender-required.
- Registries larger than 4,096 concepts can now send messages; the 4,096-entry
  limit applies per message. Registry snapshots no longer hit the 1 MiB message
  limit, and handle lookup is constant time.
- The execution session requires consistent handle bindings across a workload
  instead of an identical dictionary on every message; later messages may add
  new bindings.
- Clarified that a hard required-unit constraint locks the unit of its target
  quantity, not its numeric value.
- A descriptor that is not valid Unicode now raises `ProtocolError` instead of
  `UnicodeEncodeError`.

## 1.0.0 — 2026-11-06

- Renamed Semantic Interchange Protocol (SIP) to **Super Intelligence Semantic
  Interchange Protocol (SISIP)**.
- Positioned interchange inside agentic execution, including validation before
  adapters and a final-output boundary after the accepted result.
- Separated full 256-bit concept identities, local uint64 handles, and graph node IDs.
- Replaced natural-language wire keys/values with a closed numeric schema.
- Replaced contradictory float precision rules with normalized exact decimal
  quantities and nullable fixed-point statement confidence.
- Replaced the DAG restriction with a bounded directed graph and explicit statement nodes.
- Made the complete payload deterministic and integrity-covered, including headers.
- Added concrete unit constraints, registry-role checks, replay/time limits,
  dictionary stability, and preservation of hard constraints through execution.
- Removed unsupported benchmark percentages and the proposed SFI formula.
- Clarified that registry resolution is not proof of cross-model understanding
  and that hashes do not authenticate senders.
- Supplied the Python reference package, CLI, running example, tests, conformance
  vector, CI configuration, documentation, and CC0 1.0 public-domain dedication.
- Marked Rust, distributed registry, native model adapters, signatures,
  compression, deltas, and advanced inference as unimplemented extensions.

The v1.0 core is a first experimental release, not evidence of production
maturity or universal semantic alignment.
