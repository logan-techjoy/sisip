# Super Intelligence Semantic Interchange Protocol

## SISIP v1.0

*Model-independent structured communication during agentic workload execution.*

**Status:** proposed core specification with an experimental Python reference
implementation, version 1.0.0. This document replaces the supplied SIP draft.
MUST, MUST NOT, SHOULD, and MAY express requirements of this proposal.

## 1. Purpose and execution model

SISIP transfers explicit task state between cooperating agent adapters before and
during execution. It is an execution-time interchange layer, not an operation
performed after an answer has already been produced.

A typical workload has this sequence:

1. Construct a task graph with explicit concepts and applicable constraints.
2. Validate the exchange before invoking the receiving adapter.
3. Execute one authorized agent step, possibly including model or tool calls.
4. Exchange the resulting update, handoff, or result graph.
5. Repeat validation and execution as needed.
6. Permit final answer rendering only after an accepted latest result and
   application-specific success checks.

The reference `AgentSession` coordinates a single sequential workload. Its first
message MUST be a task with no reply target. Subsequent messages MUST be updates,
results, or handoffs replying to the immediately preceding message. A result does
not close the workload until `finalize()` succeeds. Any later update or handoff
revokes result readiness. Validation or adapter failure blocks the session;
recovery requires corrected data and a fresh workload session.

SISIP specifies externally supplied structured state. It does not require private
chain-of-thought disclosure or assume access to hidden activations. A conventional
language-model adapter may still tokenize its local representation. Native graph
consumption requires a backend that actually supports it.

## 2. Design principles

- **Tokenizer independence:** semantic payloads contain typed structures and
  registry references, never model-specific token IDs.
- **No natural-language wire fields:** the core excludes CBOR text strings and
  arbitrary byte blobs. Byte strings have fixed identifier/digest roles. Registry
  definitions, documentation, and local diagnostics may contain human language.
- **Explicit semantics:** statement arguments, units, modality, and confidence
  occupy distinct fields. Registry meaning is a shared contract, not an inference
  from integer appearance.
- **Deterministic representation:** encoding and array ordering are specified.
  Equivalent rewordings or differently numbered graphs are not automatically
  semantically canonicalized.
- **Visible failure:** unsupported meanings and violated hard constraints MUST
  block execution in the reference runtime. They MUST NOT be silently replaced.
- **Measured efficiency:** compactness and alignment are evaluation questions.
  No performance percentages or bandwidth advantage are asserted without evidence.

## 3. Concept registry and identity

The original term Universal Concept Registry describes a goal. This release uses
explicitly shared, locally supplied registry snapshots; no global registry,
registry authority, or decentralized lookup service is provided.

A registry record consists of an immutable descriptor and an integer role:

| Role | Code |
| --- | ---: |
| Entity identity | 0 |
| Class/concept | 1 |
| Predicate | 2 |
| Unit | 3 |

The identity algorithm is:

```text
record = deterministic_cbor([role, UTF8(exact_descriptor)])
concept_id = SHA256(b"SISIP-CONCEPT/1\x00" || record)
snapshot_id = SHA256(b"SISIP-REGISTRY/1\x00" ||
                     deterministic_cbor(sorted_unique_concept_ids))
```

Sorting concept IDs means bytewise lexicographic order. Exact descriptor bytes
are authoritative; implementations MUST NOT silently normalize Unicode or case.
The descriptor SHOULD identify a versioned, unambiguous semantic definition
agreed by the participants. Changing its meaning requires a new descriptor/ID.
The reference registry stores descriptors and roles; it does not implement an
ontology server or verify external definitions.

Concept IDs are full 256-bit digests. A message dictionary assigns positive
uint64 handles to these digests. These handles are message-local aliases, not
truncated hashes and not tokenizer vocabulary IDs. Duplicate IDs or duplicate
handles MUST be rejected. Graph node IDs are a separate positive uint64 space.

Cryptographic hashes greatly reduce accidental collision risk; they do not prove
truth or eliminate the need for trusted definitions and registry governance.

## 4. Core message schema

The normative shape is given in [core.cddl](core.cddl), with additional semantic
requirements in this document. The wire envelope is the untagged CBOR array:

```text
[ payload_bytes, payload_digest_bytes32 ]
```

The payload is a CBOR map with exactly these integer keys:

| Key | Value | Meaning |
| ---: | --- | --- |
| 0 | `0x5349534950` | SISIP protocol identifier |
| 1 | `[1, 0]` | Major and minor version |
| 2 | `0` | Core profile |
| 3 | bytes16 | Unique message ID within the workload |
| 4 | uint64 | Creation time, Unix milliseconds |
| 5 | `0..3` | Task=0, update=1, result=2, handoff=3 |
| 6 | bytes16 or null | Immediately preceding message ID, or null for initial task |
| 7 | bytes32 | Registry snapshot ID |
| 8 | `[[handle, concept_id], ...]` | Dictionary, increasing handle order |
| 9 | `[[node_id, node_type, data], ...]` | Nodes, increasing node ID order |
| 10 | `[node_id, ...]` | Statement/constraint roots, increasing, unique |
| 11 | `[handle, ...]` | Sender-required concepts, increasing, unique |

Every referenced node/handle MUST exist. The dictionary MUST NOT contain entries
unused by either graph fields or the required-concept list. At least one node
and one root are required. Core payload keys are closed: extra keys, versions,
profiles, or node types are errors rather than silently ignored extensions.

Node data has exactly the following shape:

| Type | Code | Data |
| --- | ---: | --- |
| Entity | 0 | Entity concept handle |
| Quantity | 1 | `[mantissa, exponent, unit_handle]` |
| Statement | 2 | `[subject_node, predicate_handle, object_node, modality, confidence]` |
| Time interval | 3 | `[start_ms, end_ms]` |
| Concept | 4 | Class/concept handle |
| Required-unit constraint | 5 | `[quantity_node, required_unit_handle, strength]` |

The graph is directed and may contain cycles, including relations to statement
nodes. A general knowledge graph is not necessarily a DAG. Implementations MUST
bound graph processing; this implementation resolves IDs without recursive
semantic inference.

### 4.1 Quantities and intervals

The exact quantity is `mantissa × 10^exponent` in the referenced unit. Mantissas
are signed int64 and exponents are integers from -18 through 18. Zero MUST be
`[0, 0, unit]`. Nonzero mantissas MUST have trailing decimal zeros removed until
none remain or the exponent reaches 18. For example, 5.0 is `[5, 0, unit]`.
Values outside these bounds MUST be rejected, not rounded.

Intervals use ordered unsigned Unix-millisecond endpoints, inclusive in the core
profile. An absent interval means timing is unspecified, not instantaneous.
Temperature differences and absolute temperatures MUST use distinct registry
definitions. The example transfers a temperature difference, not a rate.

### 4.2 Modality and confidence

Modality 0 means asserted; modality 1 means hypothetical. Hypothetical statements
MUST NOT be promoted to asserted facts without an explicit new assertion.
Conditional and counterfactual execution semantics are outside the core profile.

Confidence is null when unspecified, otherwise an integer 0..10000 divided by
10000. It records the sender's epistemic confidence in that statement. Confidence
0.82 is 8200; null is not 0. Zero means stated confidence zero, not unknown ID.
The core does not declare confidence calibrated, convert it into an interval,
multiply it into edge weights, or propagate it by an unspecified algorithm.

### 4.3 Constraints

Strength 0 means hard and 1 means soft. A required-unit constraint targets a
quantity node and compares its unit handle with the required unit handle.
Conversion is not implicit, even for physically equivalent units. Every
constraint MUST appear among the roots, so none can be hidden as a non-root node.

The reference runtime blocks on hard violations and reports soft violations.
Hard constraint records MUST retain their node IDs and data throughout a workload;
each successive graph MUST include them and their quantity targets. Dictionary
bindings MUST remain identical throughout that workload. Applications enforce
additional domain requirements through adapter validation; the core does not
provide a general constraint solver.

## 5. Serialization and integrity

The core uses the deterministic encoding requirements of RFC 8949 section 4.2.1,
restricted to integers, byte strings, arrays, integer-keyed maps, and null.
Maps sort by the bytewise lexical order of encoded keys. Only protocol-designated
arrays are sorted; positional arrays retain their semantic argument order.

Indefinite lengths, duplicate keys, nonminimal integer/length encodings, tags,
text strings, booleans, floating-point values, NaN/Infinity, trailing bytes, and
unknown types MUST be rejected. An encoded item MUST consume its complete input.

```text
payload_digest = SHA256(b"SISIP/1.0\x00" || payload_bytes)
```

The digest covers the complete payload, including IDs, version, timestamp,
registry, modality, and constraints. The digest is outside the payload to avoid
self-reference. It detects changed bytes but provides no sender authentication.
It is not a signature, an authorization decision, or evidence of semantic truth.

There is no compression or delta encoding in the v1.0 core. Transport extensions
must be explicitly agreed; they cannot silently change the core decoder behavior.

The reference limits are 1 MiB per encoded item, depth 32, 100,000 decoded items,
4,096 dictionary entries, and 4,096 graph nodes. Its session allows 4,096 messages,
rejects timestamps older than five minutes or over 30 seconds ahead by default,
and retains seen IDs without eviction until session close. Time windows and
session capacity are configurable. Cross-session replay prevention is a transport
or application responsibility. The session object is single-threaded.

## 6. Concept resolution and agent integration

The receive path MUST check integrity and schema before adapters consume a graph.
The reference session requires an exact local registry snapshot match and then
resolves every dictionary concept, checking entity/class/predicate/unit roles.
Unknown IDs remain unresolved IDs; no label, invented meaning, or artificial
confidence-zero node is substituted. The standalone `assess()` function reports
unknown concepts. The session blocks execution on any unknown concept, even one
not listed as sender-required. Snapshot mismatch is a blocking error.

An adapter translates resolved structured state into its supported backend
representation and returns structured state for the next exchange. This can be
a native graph backend, a typed tool API, or a language-model integration with
local serialization. SISIP does not claim that tokens and embeddings are
interchangeable or that an arbitrary hosted model accepts native graph tensors.

Adapters SHOULD validate domain-specific completion and preserve source and
measurement meaning. Tool permissions and human-approval rules remain application
policy. Receiving a `TASK` or `HANDOFF` is not authorization to execute an action.

`step()` validates an initial inbound exchange before running an adapter, then
validates the adapter's output. `advance()` runs the next adapter against the
accepted current graph. `finalize()` returns the accepted latest result graph
and closes the session. Rendering a human-readable answer occurs after that gate.

## 7. Example

The fixture describes this supplied observation: Joplin, Missouri, USA has a
temperature difference of +5 degrees Celsius over an unspecified period, with
sender confidence 0.82 and a hard requirement to express the difference in
degrees Celsius. It does not assert a measured rate or a specific time interval.

With `L`, `P`, and `U` denoting numeric dictionary handles for the location,
temperature-difference predicate, and Celsius-difference unit, its node array is:

```text
[
  [1, 0, L],
  [2, 1, [5, 0, U]],
  [3, 2, [1, P, 2, 0, 8200]],
  [4, 5, [2, U, 0]]
]
roots = [3, 4]
```

This is explanatory pseudocode, not JSON or literal wire bytes. The actual
dictionary and complete deterministic binary fixture are generated by
`sisip.demo.example_message()` and committed as `examples/temperature.sisip`.
The accompanying JSON vector is human-facing diagnostic metadata. Neither the
location label nor the unit label is transmitted as a text field.

## 8. Fidelity and evaluation

Three different checks MUST remain separate:

| Layer | Question | Available evidence |
| --- | --- | --- |
| Transport | Were the canonical bytes preserved? | Digest and byte comparison |
| Structure | Were types, references, and core constraints preserved? | Validator and constraint reports |
| Interpretation | Did the receiver preserve the intended meaning and task behavior? | Domain tests and adapter evaluations |

A byte-identical graph can still be misunderstood. Structural determinism does
not establish identical model beliefs, reasoning, or generated answers.

The original SFI formula and unmeasured percentage claims are withdrawn. A future
evaluation SHOULD report concept-resolution coverage, retained required
constraints, modality preservation, numerical error, and domain-task accuracy
separately. Any aggregate score requires published weights, matching rules,
uncertainty interpretation, and independent ground truth.

Benchmarks SHOULD compare identical tasks using this core, structured JSON, and
ordinary language. Report complete wire sizes, registry/setup overhead, adapter
token usage when applicable, latency, unresolved concepts, and task success.
Separate cold-start and warm-cache costs. Small messages may be larger than
their natural-language equivalent. No lexical-ambiguity percentage, alignment
percentage, payload-size range, or speedup is guaranteed by this proposal.

## 9. Security, conformance, and extensions

Remote deployments require authenticated transport and application authorization.
Registry hashes identify supplied content; trust in the registry's definitions
and in an agent's assertions is a separate decision. Do not treat structured
instructions as inherently trustworthy or grant tool access from a graph field.

This release supplies no encryption, digital signatures, distributed registry,
Merkle proof service, graph repair, Rust library, or model-specific trained mapper.
COSE may be evaluated for a future authenticated message profile; it is not part
of the implemented wire format. Semantic preservation across actual models is
not established by the deterministic demo.

A conforming core codec MUST satisfy sections 3–5 and reject unsupported data.
A conforming reference-style execution gate additionally enforces section 1's
linear workload rules, section 4.3's persistent hard constraints, and section 6's
resolution requirements before adapter invocation and finalization.

Breaking core changes require a new supported version/profile. Adding registry
definitions changes its snapshot and requires a new workload agreement; it need
not change the core schema. v1.0's closed schema does not authorize silent
forward-compatible field skipping.

## References

- [RFC 8949 — Concise Binary Object Representation](https://www.rfc-editor.org/rfc/rfc8949.html), especially section 4.2.1.
- [RFC 8610 — Concise Data Definition Language](https://www.rfc-editor.org/rfc/rfc8610.html).
- [RFC 9052 — COSE: Structures and Process](https://www.rfc-editor.org/rfc/rfc9052.html), background for future authentication profiles only.

SISIP makes task state explicit and portable during execution. Shared semantic
definitions, validated adapters, and application policy remain necessary for
reliable cooperation.
