import copy
import hashlib
import unittest
from pathlib import Path

from sisip import (AgentSession, Concept, Registry, ProtocolError, assess,
                   decode, encode, digest, make_message)
from sisip.cbor import dumps, loads
from sisip.demo import example_message, DEMO_REGISTRY, CELSIUS_DELTA, run_demo
from sisip.protocol import RESULT, UPDATE
from sisip.registry import UNIT, PREDICATE


class CBORTests(unittest.TestCase):
    def test_known_rfc8949_vectors(self):
        for value, hex_value in [(0, "00"), (23, "17"), (24, "1818"),
                                  (1000, "1903e8"), (-1, "20"), (-1000, "3903e7"),
                                  (b"\x01\x02", "420102"), ([1, 2, 3], "83010203"),
                                  (None, "f6"), ({0: 1, 24: 2}, "a20001181802")]:
            with self.subTest(value=value):
                self.assertEqual(dumps(value).hex(), hex_value)
                self.assertEqual(loads(bytes.fromhex(hex_value)), value)

    def test_reject_bad_wire(self):
        cases = ["", "1817", "190018", "a200010002", "a201010002",
                 "9fff", "6161", "f4", "fa3f800000", "c000", "0100", "4401",
                 "82", "a18000", "1c", "f7"]
        for data in cases:
            with self.subTest(data=data), self.assertRaises(ProtocolError):
                loads(bytes.fromhex(data))

    def test_depth_and_size_limits(self):
        for data in [b"\x81" * 34 + b"\x00", b"\x00" * 1_048_577,
                     bytes.fromhex("9a000186a1")]:
            with self.assertRaises(ProtocolError):
                loads(data)
        with self.assertRaises(ProtocolError):
            dumps([b"x" * 600_000, b"y" * 600_000])

    def test_forbidden_python_values(self):
        for value in ["English", 0.82, True, {"x": 1}, 1 << 64, -(1 << 64)-1]:
            with self.subTest(value=value), self.assertRaises(ProtocolError):
                dumps(value)


class GraphTests(unittest.TestCase):
    def test_round_trip_and_determinism(self):
        m = example_message()
        self.assertEqual(decode(encode(m)), m)
        self.assertEqual(encode(dict(reversed(list(m.items())))), encode(m))
        self.assertTrue(assess(m, DEMO_REGISTRY).accepted)

    def test_no_text_anywhere_in_wire_data(self):
        def walk(obj):
            self.assertNotIsInstance(obj, str)
            if type(obj) is bytes:
                return
            if type(obj) is list:
                for val in obj:
                    walk(val)
            elif type(obj) is dict:
                for key, val in obj.items():
                    walk(key)
                    walk(val)
        wire = encode(example_message())
        walk(loads(wire))
        walk(decode(wire))

    def test_integrity_covers_headers_too(self):
        wire = loads(encode(example_message()))
        payload = loads(wire[0])
        payload[5] = RESULT
        wire[0] = dumps(payload)
        with self.assertRaises(ProtocolError):
            decode(dumps(wire))

    def test_schema_failures(self):
        mutations = [
            lambda m: m.update({1: [2, 0]}),
            lambda m: m.update({2: 1}),
            lambda m: m.update({12: 1}),
            lambda m: m[9][2][2].__setitem__(0, 999),
            lambda m: m[9][2][2].__setitem__(3, 2),
            lambda m: m[9][2][2].__setitem__(4, 10001),
            lambda m: m[9][1][2].__setitem__(0, 50),
            lambda m: m.update({10: [3]}),
            lambda m: m.update({10: [4, 3]}),
            lambda m: m[9].reverse(),
            lambda m: m[9][1][2].__setitem__(2, 100),
            lambda m: m[8][1].__setitem__(1, m[8][0][1]),
        ]
        for mutate in mutations:
            m = example_message()
            mutate(m)
            with self.subTest(message=m), self.assertRaises(ProtocolError):
                encode(m)

    def test_unknown_concepts_do_not_become_zero_confidence(self):
        m = example_message()
        report = assess(m, Registry())
        self.assertEqual(len(report.missing_concepts), 3)
        self.assertFalse(report.accepted)
        self.assertEqual(m[9][2][2][4], 8200)

    def test_registry_identity_and_snapshot(self):
        a, b = Concept("demo/v1/a", UNIT), Concept("demo/v1/b", UNIT)
        self.assertEqual(Registry([a, b]).snapshot, Registry([b, a]).snapshot)
        self.assertNotEqual(a.cid, Concept("demo/v1/a", PREDICATE).cid)
        self.assertEqual(len(a.cid), 32)

    def test_hard_and_soft_unit_constraints(self):
        other = Concept("sisip.demo/v1/unit/kelvin-difference", UNIT)
        base = [DEMO_REGISTRY.get(cid) for _, cid in DEMO_REGISTRY.dictionary()]
        registry = Registry(base + [other])
        # Remap every handle after extending the dictionary.
        old = dict(DEMO_REGISTRY.dictionary())
        new = {cid: handle for handle, cid in registry.dictionary()}
        m = example_message()
        nodes = copy.deepcopy(m[9])
        nodes[0][2] = new[old[nodes[0][2]]]
        nodes[1][2][2] = registry.handle(other)
        nodes[2][2][1] = new[old[nodes[2][2][1]]]
        nodes[3][2][1] = registry.handle(CELSIUS_DELTA)
        m = make_message(registry, nodes, [3, 4])
        self.assertEqual(assess(m, registry).hard_violations, (4,))
        m[9][3][2][2] = 1
        report = assess(m, registry)
        self.assertTrue(report.accepted)
        self.assertEqual(report.soft_violations, (4,))

    def test_registry_role_mismatch(self):
        m = example_message()
        m[9][2][2][1] = DEMO_REGISTRY.handle(CELSIUS_DELTA)
        # Preserve dictionary usage through required concepts.
        with self.assertRaises(ProtocolError):
            assess(m, DEMO_REGISTRY)

    def test_committed_conformance_vector(self):
        directory = Path(__file__).resolve().parents[1] / "examples"
        vector = directory / "temperature.sisip"
        self.assertTrue(vector.is_file(), "generate conformance fixture before release")
        self.assertEqual(vector.read_bytes(), encode(example_message()))
        self.assertEqual(decode(vector.read_bytes()), example_message())


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.m = example_message()
        self.session = AgentSession(DEMO_REGISTRY, clock=lambda: self.m[4])

    def reply(self, m, kind=RESULT):
        return make_message(DEMO_REGISTRY, m[9], m[10], kind=kind,
                            reply_to=m[3], timestamp_ms=m[4], message_id=b"r" * 16)

    def test_demo_runs_during_execution(self):
        result, history = run_demo()
        self.assertEqual([m[5] for m in history], [0, 3, 2])
        self.assertEqual(result[5], RESULT)

    def test_no_final_output_before_result(self):
        with self.assertRaises(ProtocolError):
            self.session.finalize()
        self.session.receive(encode(self.m))
        with self.assertRaises(ProtocolError):
            self.session.finalize()

    def test_validation_precedes_adapter(self):
        called = []
        with self.assertRaises(ProtocolError):
            self.session.step(b"bad", lambda m: called.append(m))
        self.assertEqual(called, [])
        with self.assertRaises(ProtocolError):
            self.session.finalize()

    def test_dropped_hard_constraint_blocks_result(self):
        def adapter(m):
            reply = self.reply(m)
            reply[9] = reply[9][:-1]
            reply[10] = [3]
            return reply
        with self.assertRaises(ProtocolError):
            self.session.step(encode(self.m), adapter)
        with self.assertRaises(ProtocolError):
            self.session.finalize()

    def test_direct_receive_cannot_drop_hard_constraint(self):
        self.session.receive(encode(self.m))
        reply = self.reply(self.m)
        reply[9] = reply[9][:-1]
        reply[10] = [3]
        with self.assertRaises(ProtocolError):
            self.session.receive(encode(reply))

    def test_latest_update_invalidates_result(self):
        self.session.step(encode(self.m), self.reply)
        latest = self.session.history[-1]
        update = self.reply(latest, UPDATE)
        update[3] = b"u" * 16
        self.session.receive(encode(update))
        with self.assertRaises(ProtocolError):
            self.session.finalize()

    def test_replay_and_stale_messages(self):
        self.session.receive(encode(self.m))
        with self.assertRaises(ProtocolError):
            self.session.receive(encode(self.m))
        stale = AgentSession(DEMO_REGISTRY, clock=lambda: self.m[4] + 300001)
        with self.assertRaises(ProtocolError):
            stale.receive(encode(self.m))

    def test_registry_snapshot_mismatch(self):
        self.m[7] = b"x" * 32
        with self.assertRaises(ProtocolError):
            self.session.receive(encode(self.m))

    def test_unlinked_result_rejected(self):
        self.m[5] = RESULT
        with self.assertRaises(ProtocolError):
            self.session.receive(encode(self.m))

    def test_bad_reply_and_adapter_exception_block_finalization(self):
        def bad_reply(m):
            reply = self.reply(m)
            reply[6] = b"x" * 16
            return reply
        with self.assertRaises(ProtocolError):
            self.session.step(encode(self.m), bad_reply)
        with self.assertRaises(ProtocolError):
            self.session.finalize()

    def test_finalize_only_once(self):
        self.session.step(encode(self.m), self.reply)
        self.assertEqual(self.session.finalize()[5], RESULT)
        with self.assertRaises(ProtocolError):
            self.session.finalize()

    def test_history_is_detached(self):
        self.session.receive(encode(self.m))
        snapshot = self.session.history
        snapshot[0][9].clear()
        self.assertTrue(self.session.history[0][9])


def _subset_nodes(r, loc, delta, unit):
    return [[1, 0, r.handle(loc)],
            [2, 1, [5, 0, r.handle(unit)]],
            [3, 2, [1, r.handle(delta), 2, 0, 8200]]]


class RegistrySubsetTests(unittest.TestCase):
    def setUp(self):
        from sisip.demo import LOCATION, DELTA
        self.LOCATION, self.DELTA = LOCATION, DELTA
        self.r = Registry([LOCATION, DELTA, CELSIUS_DELTA, Concept("x/unused", 0)])
        self.nodes = _subset_nodes(self.r, LOCATION, DELTA, CELSIUS_DELTA)

    def build(self, **kw):
        return make_message(self.r, copy.deepcopy(self.nodes), [3],
                            timestamp_ms=1735689600000,
                            message_id=bytes.fromhex("00" * 15 + "01"), **kw)

    def test_subset_graph_with_empty_required(self):
        m = self.build(required=[])
        used = {self.r.handle(c) for c in (self.LOCATION, self.DELTA, CELSIUS_DELTA)}
        self.assertEqual({h for h, _ in m[8]}, used)
        self.assertEqual(m[11], [])
        self.assertEqual(decode(encode(m)), m)

    def test_default_required_is_empty(self):
        m = self.build()
        self.assertEqual(m[11], [])
        self.assertEqual(len(m[8]), 3)

    def test_explicit_required_in_dictionary_and_key_11(self):
        extra = self.r.handle(Concept("x/unused", 0))
        m = self.build(required=[extra])
        self.assertIn(extra, m[11])
        self.assertIn(extra, [h for h, _ in m[8]])
        self.assertEqual(len(m[8]), 4)

    def test_handles_stable_across_messages(self):
        a = self.build(required=[])
        b = make_message(self.r, [[1, 0, self.r.handle(self.LOCATION)],
                                  [2, 1, [5, 0, self.r.handle(CELSIUS_DELTA)]],
                                  [3, 2, [1, self.r.handle(self.DELTA), 2, 0, 8200]]], [3])
        self.assertEqual(dict(a[8]), dict(b[8]))

    def test_snapshot_bytes_unchanged_for_demo_registry(self):
        import json
        vec = json.loads((Path(__file__).resolve().parents[1] / "examples" /
                          "temperature.vector.json").read_text())
        self.assertEqual(DEMO_REGISTRY.snapshot.hex(), vec["registry_snapshot"])
        legacy = hashlib.sha256(b"SISIP-REGISTRY/1\x00" +
                                dumps(sorted(c.cid for c in DEMO_REGISTRY._concepts.values()))).digest()
        self.assertEqual(DEMO_REGISTRY.snapshot, legacy)

    def test_fixture_still_byte_identical(self):
        directory = Path(__file__).resolve().parents[1] / "examples"
        self.assertEqual((directory / "temperature.sisip").read_bytes(),
                         encode(example_message()))


class LargeRegistryTests(unittest.TestCase):
    def test_5000_concept_registry_can_message_and_run_session(self):
        from sisip.demo import LOCATION, DELTA
        r = Registry([LOCATION, DELTA, CELSIUS_DELTA] +
                     [Concept(f"bulk/{i}", 0) for i in range(5000)])
        nodes = _subset_nodes(r, LOCATION, DELTA, CELSIUS_DELTA)
        m = make_message(r, nodes, [3], timestamp_ms=1735689600000)
        self.assertEqual(len(m[8]), 3)
        self.assertEqual(decode(encode(m)), m)
        session = AgentSession(r, clock=lambda: 1735689600000)

        def reply(g):
            return make_message(r, copy.deepcopy(g[9]), g[10], kind=RESULT,
                                reply_to=g[3], timestamp_ms=1735689600000)
        session.step(encode(m), reply)
        self.assertEqual(session.finalize()[5], RESULT)

    def test_50000_concept_snapshot_and_handle_fast(self):
        import time
        concepts = [Concept(f"bulk/{i}", 0) for i in range(50000)]
        t = time.monotonic()
        r = Registry(concepts)
        snap = r.snapshot
        self.assertEqual(len(snap), 32)
        for c in concepts[:2000]:
            r.handle(c)
        self.assertLess(time.monotonic() - t, 5.0)
        self.assertEqual(r.handle(sorted(concepts, key=lambda c: c.cid)[41]), 42)


class SessionBindingTests(unittest.TestCase):
    T = 1735689600000

    def setUp(self):
        from sisip.demo import LOCATION, DELTA
        self.LOCATION, self.DELTA = LOCATION, DELTA
        self.other = Concept("x/other-class", 1)
        self.r = Registry([LOCATION, DELTA, CELSIUS_DELTA, self.other])
        self.session = AgentSession(self.r, clock=lambda: self.T)
        self.first = make_message(
            self.r, _subset_nodes(self.r, LOCATION, DELTA, CELSIUS_DELTA), [3],
            timestamp_ms=self.T, message_id=bytes.fromhex("00" * 15 + "01"))
        self.session.receive(encode(self.first))

    def follow(self, nodes, dictionary=None):
        m = make_message(self.r, nodes, [3], kind=UPDATE, reply_to=self.first[3],
                         timestamp_ms=self.T, message_id=bytes.fromhex("00" * 15 + "02"))
        if dictionary is not None:
            m[8] = dictionary
        return m

    def test_new_consistent_binding_accepted(self):
        nodes = _subset_nodes(self.r, self.LOCATION, self.DELTA, CELSIUS_DELTA)
        nodes.append([4, 4, self.r.handle(self.other)])
        _, report = self.session.receive(encode(self.follow(nodes)))
        self.assertTrue(report.accepted)

    def test_handle_rebound_to_different_cid_rejected(self):
        m = self.follow(_subset_nodes(self.r, self.LOCATION, self.DELTA, CELSIUS_DELTA))
        d = dict(m[8])
        h1, h2 = sorted(d)[:2]
        m[8] = [[h1, d[h2]], [h2, d[h1]]] + [[h, d[h]] for h in sorted(d)[2:]]
        with self.assertRaisesRegex(ProtocolError, "binding changed"):
            self.session.receive(encode(m))

    def test_cid_rebound_to_different_handle_rejected(self):
        m = self.follow(_subset_nodes(self.r, self.LOCATION, self.DELTA, CELSIUS_DELTA))
        loc = self.r.handle(self.LOCATION)
        m[8] = sorted([[loc + 100, self.r.dictionary([loc])[0][1]]] +
                      [e for e in m[8] if e[0] != loc])
        m[9][0] = [1, 0, loc + 100]
        m[11] = []
        with self.assertRaisesRegex(ProtocolError, "binding changed"):
            self.session.receive(encode(m))


class HardConstraintScopeTests(unittest.TestCase):
    """Pins spec 4.3: the hard constraint node is locked; its target's value is not."""

    def setUp(self):
        self.m = example_message()
        self.session = AgentSession(DEMO_REGISTRY, clock=lambda: self.m[4])

    def reply_with(self, m, nodes):
        return make_message(DEMO_REGISTRY, nodes, m[10], kind=RESULT,
                            reply_to=m[3], timestamp_ms=m[4], message_id=b"r" * 16)

    def test_target_value_may_change_and_result_finalizes(self):
        def adapter(m):
            nodes = copy.deepcopy(m[9])
            self.assertEqual(nodes[1][2][0], 5)
            nodes[1][2][0] = 999
            return self.reply_with(m, nodes)
        self.session.step(encode(self.m), adapter)
        final = self.session.finalize()
        self.assertEqual(final[9][1][2], [999, 0, DEMO_REGISTRY.handle(CELSIUS_DELTA)])

    def test_target_unit_change_blocks_session(self):
        other = Concept("sisip.demo/v1/unit/kelvin-difference", UNIT)
        base = [DEMO_REGISTRY.get(cid) for _, cid in DEMO_REGISTRY.dictionary()]
        registry = Registry(base + [other])
        old = dict(DEMO_REGISTRY.dictionary())
        new = {cid: h for h, cid in registry.dictionary()}
        nodes = copy.deepcopy(self.m[9])
        nodes[0][2] = new[old[nodes[0][2]]]
        nodes[1][2][2] = new[old[nodes[1][2][2]]]
        nodes[2][2][1] = new[old[nodes[2][2][1]]]
        nodes[3][2][1] = new[old[nodes[3][2][1]]]
        first = make_message(registry, nodes, [3, 4], timestamp_ms=self.m[4])
        session = AgentSession(registry, clock=lambda: first[4])

        def adapter(m):
            changed = copy.deepcopy(m[9])
            changed[1][2][2] = registry.handle(other)
            return make_message(registry, changed, m[10], kind=RESULT, reply_to=m[3],
                                timestamp_ms=m[4], message_id=b"r" * 16)
        with self.assertRaises(ProtocolError):
            session.step(encode(first), adapter)
        with self.assertRaises(ProtocolError):
            session.finalize()

    def test_altered_hard_constraint_node_is_rejected(self):
        self.session.receive(encode(self.m))
        nodes = copy.deepcopy(self.m[9])
        nodes[3][2][2] = 1
        reply = self.reply_with(self.m, nodes)
        with self.assertRaises(ProtocolError):
            self.session.receive(encode(reply))
        with self.assertRaises(ProtocolError):
            self.session.finalize()

    def test_hard_constraint_target_must_exist(self):
        def adapter(m):
            nodes = [n for n in copy.deepcopy(m[9]) if n[0] != 2]
            return self.reply_with(m, nodes)
        with self.assertRaises(ProtocolError):
            self.session.step(encode(self.m), adapter)
        with self.assertRaises(ProtocolError):
            self.session.finalize()


class ConceptEncodingTests(unittest.TestCase):
    def test_lone_surrogate_descriptor_raises_protocol_error(self):
        with self.assertRaises(ProtocolError):
            Concept("demo/\ud800", UNIT).cid

    def test_registry_construction_raises_protocol_error(self):
        with self.assertRaises(ProtocolError):
            Registry([Concept("demo/\udfff", UNIT)])

    def test_descriptors_are_not_normalized(self):
        composed, decomposed = "caf\u00e9", "cafe\u0301"
        self.assertNotEqual(Concept(composed, UNIT).cid, Concept(decomposed, UNIT).cid)
        self.assertNotEqual(Concept("Demo", UNIT).cid, Concept("demo", UNIT).cid)


if __name__ == "__main__":
    unittest.main()
