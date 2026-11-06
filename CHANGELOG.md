# Changelog

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
