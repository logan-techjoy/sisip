# Contributing

Use Python 3.10+ and install with `python -m pip install -e .`. Run:

```sh
python -m unittest discover -s tests -v
python examples/agentic_workload.py
```

Keep the implementation, specification, CDDL, conformance vectors, and tests in
agreement. Wire format changes require an explicit version/profile decision.
Preserve strict rejection of unsupported features rather than silently guessing
meaning. Add tests for behavior changes and malformed inputs.

For adapter work, publish the registry definitions, backend assumptions, tasks,
and observed failures. Distinguish structural round-trip success from semantic
or task success. Performance claims need reproducible measurements, complete
wire sizes, setup costs, and appropriate JSON/natural-language baselines.

Contributions are dedicated to the public domain under the repository's CC0 1.0 license. The public source
release includes no API keys, vendor-specific integrations, or deployment secrets.
