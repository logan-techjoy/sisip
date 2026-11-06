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


if __name__ == "__main__":
    unittest.main()
