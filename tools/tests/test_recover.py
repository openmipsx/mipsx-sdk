#!/usr/bin/env python3
# Tests for the recovery-protocol client (tools/mipsx_recover.py).
#
# Copyright 2026 The mipsx-sdk authors.
# SPDX-License-Identifier: Apache-2.0
#
# Run from the repository root:  python3 -m unittest discover -s tools/tests
# Everything runs on loopback with unicast addresses and free ports: the
# client takes the group, ports and timings as options, and the fake
# unit (fake_unit.py) plays section B as the format spec describes it.
# The packet checks build the expected bytes by hand from the spec and
# compare them with what the fake unit received.

import io
import os
import socket
import struct
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import mipsx_pack as pack  # noqa: E402
import mipsx_recover as rec  # noqa: E402
from fake_unit import FakeUnit, free_port, wait_until  # noqa: E402
from test_tools import build_test_elf  # noqa: E402

LO = "127.0.0.1"


def cfg_for(unit, reply_port, **kw):
    """A client Config pointed at UNIT on loopback, with short timings."""
    opts = dict(group=LO, unit_port=unit.port, reply_port=reply_port,
                tftp_port=0, reply_timeout=0.4, rrq_timeout=3.0,
                block_timeout=0.5, block_retries=3, install_wait=0.3,
                port_width=unit.port_width)
    opts.update(kw)
    return rec.Config(**opts)


def expected_request(mtype, target, port=None, name=None, width=16):
    """The request as format spec §7.1 lays it out, built independently
    of the client: 160 bytes, type at 0, 'RECM' (0x5245434D) at 4,
    target NUL-terminated at 8, TFTP port at 0x1C, name at 0x20."""
    r = bytearray(160)
    r[0] = mtype
    r[4:8] = struct.pack(">I", 0x5245434D)
    r[8:8 + len(target)] = target.encode()
    if port is not None:
        r[0x1C:0x1C + width // 8] = port.to_bytes(width // 8, "big")
    if name is not None:
        r[0x20:0x20 + len(name)] = name.encode()
    return bytes(r)


class Fixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        elf, _ = build_test_elf(os.path.join(cls.tmp.name, "prog.elf"))
        cls.image = pack.pack_elf(elf, version="9.1.2(test)")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.units = []
        self.out = io.StringIO()
        self.log = rec.Log(self.out)
        self.port = free_port()           # the client's reply port

    def tearDown(self):
        for u in self.units:
            u.close()

    def unit(self, **kw):
        kw.setdefault("group_addr", LO)
        kw.setdefault("reply_port", self.port)
        u = FakeUnit(**kw)
        u.start()
        self.units.append(u)
        return u

    def control(self, reply_port):
        s = rec.open_socket(reply_port, LO)
        self.addCleanup(s.close)
        return s


# --- Messages, without a network ----------------------------------------

class MessageTest(unittest.TestCase):
    def test_discovery_request_bytes(self):
        req = rec.build_request(rec.MSG_DISCOVER)
        self.assertEqual(len(req), 160)
        self.assertEqual(req, expected_request(0, "FFFFFFFFFFFF"))
        self.assertEqual(req[4:8], b"\x52\x45\x43\x4D")   # 0x5245434D
        self.assertEqual(req[8:20], b"FFFFFFFFFFFF")
        self.assertEqual(req[20:], bytes(140))

    def test_upgrade_request_bytes(self):
        req = rec.build_request(rec.MSG_UPGRADE, "0123456789AB", 69,
                                "spa.bin")
        self.assertEqual(req, expected_request(2, "0123456789AB", 69,
                                               "spa.bin"))
        self.assertEqual(req[0x1C:0x20], b"\x00\x45\x00\x00")
        self.assertEqual(req[0x20:0x28], b"spa.bin\0")
        self.assertEqual(req[0x28:], bytes(160 - 0x28))

    def test_port_width_32(self):
        req = rec.build_request(rec.MSG_UPGRADE, "FFFFFFFFFFFF", 6969,
                                "x", port_width=32)
        self.assertEqual(req[0x1C:0x20], struct.pack(">I", 6969))
        self.assertEqual(req, expected_request(2, "FFFFFFFFFFFF", 6969,
                                               "x", width=32))

    def test_limits(self):
        rec.build_request(rec.MSG_UPGRADE, "F" * 19, 1, "n" * 66)
        for bad in [dict(target=""), dict(target="F" * 20),
                    dict(tftp_port=0), dict(tftp_port=65536), dict(name=""),
                    dict(name="n" * 67), dict(name="a\0b"),
                    dict(port_width=8)]:
            kw = dict(target="FFFFFFFFFFFF", tftp_port=69, name="f")
            kw.update(bad)
            with self.assertRaises(rec.RecoverError, msg=repr(bad)):
                rec.build_request(rec.MSG_UPGRADE, **kw)

    def test_reply_parsing(self):
        u = FakeUnit(identifier="AABBCCDDEEFF", model="SPA-3000",
                     mac=bytes.fromhex("aabbccddeeff"), version="1.0.6(3k)",
                     hardware="2.0.1", ip="192.168.1.123")
        u.close()
        data = u.discovery_reply()
        self.assertEqual(len(data), 100)
        self.assertEqual(rec.classify_reply(data), (1, None))
        info = rec.UnitInfo(data, (LO, 4811))
        self.assertEqual(info.identifier, "AABBCCDDEEFF")
        self.assertEqual(info.model, "SPA-3000")
        self.assertEqual(info.mac, "aa:bb:cc:dd:ee:ff")
        self.assertEqual(info.version, "1.0.6(3k)")
        self.assertEqual(info.hardware, "2.0.1")
        self.assertEqual(info.ip, "192.168.1.123")
        self.assertIn("192.168.1.123", str(info))

    def test_classify(self):
        self.assertEqual(rec.classify_reply(b"short"), (None, None))
        self.assertEqual(rec.classify_reply(bytes(100)), (None, None))
        t, problem = rec.classify_reply(b"\x02\0\0\0RECM" + bytes(90))
        self.assertEqual(t, 2)
        self.assertIn("98", problem)

    def test_parse_rrq(self):
        self.assertEqual(rec.parse_rrq(b"\0\x01spa.bin\0octet\0"),
                         (b"spa.bin", b"octet", {}))
        self.assertEqual(
            rec.parse_rrq(b"\0\x01f\0octet\0blksize\0" b"1428\0"),
            (b"f", b"octet", {b"blksize": b"1428"}))
        self.assertIsNone(rec.parse_rrq(b"\0\x02f\0octet\0"))   # WRQ
        self.assertIsNone(rec.parse_rrq(b"\0\x01f\0octet"))     # no NUL
        self.assertIsNone(rec.parse_rrq(b"\0"))


# --- Discovery --------------------------------------------------------------

class DiscoverTest(Fixture):
    def test_one_unit(self):
        u = self.unit(identifier="001122334455")
        port = self.port
        cfg = cfg_for(u, port)
        units = rec.discover(self.control(port), cfg, self.log)
        self.assertEqual([x.identifier for x in units], ["001122334455"])
        self.assertEqual(units[0].addr, (LO, u.port))
        # Exactly one request, and byte for byte what the spec says.
        self.assertEqual([d for d, a in u.received],
                         [expected_request(0, "FFFFFFFFFFFF")])
        # Sent from the reply port, as the public description says.
        self.assertEqual(u.received[0][1], (LO, port))
        self.assertIn("unit: 001122334455", self.out.getvalue())

    def test_reply_to_group(self):
        port = self.port
        u = self.unit(reply_to="group", reply_port=port)
        units = rec.discover(self.control(port), cfg_for(u, port), self.log)
        self.assertEqual(len(units), 1)
        self.assertEqual(u.sent[0][1], (LO, port))

    def test_two_units_and_target(self):
        a = self.unit(identifier="AAAAAAAAAAAA")
        b = self.unit(identifier="BBBBBBBBBBBB", host=LO)
        # Both listen on their own ports; point the client at each in
        # turn with the same control socket (there is no multicast on
        # loopback), then check the target filter on the wire.
        port = self.port
        sock = self.control(port)
        found = set()
        for u in (a, b):
            for x in rec.discover(sock, cfg_for(u, port), self.log):
                found.add(x.identifier)
        self.assertEqual(found, {"AAAAAAAAAAAA", "BBBBBBBBBBBB"})
        # A targeted request is ignored by the other unit.
        self.assertEqual(rec.discover(sock, cfg_for(b, port), self.log,
                                      target="AAAAAAAAAAAA"), [])
        self.assertEqual(b.received[-1][0],
                         expected_request(0, "AAAAAAAAAAAA"))
        self.assertIn("ignored: target", b.log[-1])
        self.assertEqual(len(rec.discover(sock, cfg_for(a, port), self.log,
                                          target="AAAAAAAAAAAA")), 1)

    def test_repeat_and_silence(self):
        u = self.unit()
        u.stopped = True                          # a unit that is silent
        port = self.port
        cfg = cfg_for(u, port, repeat=3, reply_timeout=0.15)
        self.assertEqual(rec.discover(self.control(port), cfg, self.log), [])
        self.assertEqual(len(u.received), 3)
        self.assertEqual(self.out.getvalue().count("asking again"), 2)

    def test_junk_reported(self):
        port = self.port
        u = self.unit()
        sock = self.control(port)
        junk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.addCleanup(junk.close)
        junk.sendto(b"hello", (LO, port))
        junk.sendto(b"\x01\0\0\0RECM" + bytes(80), (LO, port))   # short
        units = rec.discover(sock, cfg_for(u, port), self.log)
        self.assertEqual(len(units), 1)
        text = self.out.getvalue()
        self.assertIn("not a recovery message", text)
        self.assertIn("length 88, expected 100", text)


# --- Upgrade ---------------------------------------------------------------

class UpgradeTest(Fixture):
    def run_upgrade(self, unit, image=None, name="prog.bin", **kw):
        port = self.port
        cfg = cfg_for(unit, port, **{k: v for k, v in kw.items()
                                     if hasattr(rec.Config, k)})
        extra = {k: v for k, v in kw.items() if not hasattr(rec.Config, k)}
        rc = rec.upgrade(cfg, image or self.image, name, self.log, **extra)
        self.assertTrue(wait_until(lambda: not unit.is_alive()
                                   or unit.stopped or unit.install_error))
        return rc, port

    def test_full_exchange(self):
        u = self.unit(identifier="001122334455")
        rc, port = self.run_upgrade(u)
        self.assertEqual(rc, 0, self.out.getvalue())
        self.assertTrue(u.stopped)
        self.assertIsNone(u.install_error)
        self.assertEqual(u.downloaded, self.image)
        # The installer wrote exactly the image's type 2 section.
        self.assertEqual(len(u.installed), 1)
        stype, entry, data = u.installed[0]
        self.assertEqual(stype, 2)
        self.assertEqual(entry, self.image[0x80:0x100])
        length = struct.unpack_from(">I", entry, 0x20)[0]
        self.assertEqual(data[:length], self.image[0x180:0x180 + length])
        text = self.out.getvalue()
        self.assertIn("upgrading 001122334455", text)
        self.assertIn("acknowledged by", text)
        self.assertIn("transfer complete", text)
        self.assertIn("no longer answers", text)

    def test_wire_bytes(self):
        """Every message the client sent, against the spec's layout."""
        u = self.unit(identifier="001122334455")
        rc, port = self.run_upgrade(u, name="spa.bin")
        self.assertEqual(rc, 0)
        reqs = [d for d, a in u.received if len(d) == 160]
        # Discovery (wildcard), the upgrade addressed to the unit found,
        # then the post-check discovery addressed to it.
        tftp_port = struct.unpack_from(">H", reqs[1], 0x1C)[0]
        self.assertNotEqual(tftp_port, 0)
        self.assertEqual(reqs, [
            expected_request(0, "FFFFFFFFFFFF"),
            expected_request(2, "001122334455", tftp_port, "spa.bin"),
            expected_request(0, "001122334455")])
        for d, a in u.received:
            if len(d) == 160:
                self.assertEqual(a, (LO, port))   # from the reply port
        # The unit's read request went to the port named in the request,
        # and the data came back from that same port (RFC 1350 blocks,
        # 512 bytes each, numbered from 1, last one short).
        rrq, rrq_addr = u.sent[2]
        self.assertEqual(rrq, b"\0\x01spa.bin\0octet\0")
        self.assertEqual(rrq_addr, (LO, tftp_port))
        blocks = [(d, a) for d, a in u.received
                  if len(d) >= 4 and d[:2] == b"\0\x03"]
        n = len(self.image) // 512 + 1
        self.assertEqual(len(blocks), n)
        for i, (d, a) in enumerate(blocks, 1):
            self.assertEqual(a, (LO, tftp_port))
            self.assertEqual(d[:4], struct.pack(">HH", 3, i))
            self.assertEqual(d[4:], self.image[(i - 1) * 512:i * 512])
        self.assertLess(len(blocks[-1][0]) - 4, 512)
        self.assertEqual(b"".join(d[4:] for d, a in blocks), self.image)
        # The acknowledgement echoed the request cut to 100 bytes.
        self.assertEqual(u.sent[1][0], reqs[1][:100])

    def test_port_width_32(self):
        u = self.unit(port_width=32)
        rc, port = self.run_upgrade(u)
        self.assertEqual(rc, 0)
        req = [d for d, a in u.received if len(d) == 160][1]
        self.assertEqual(req[0x1C:0x1E], b"\0\0")
        self.assertEqual(u.downloaded, self.image)

    def test_retransmission(self):
        u = self.unit(drop_data_blocks=(1, 3))
        rc, port = self.run_upgrade(u)
        self.assertEqual(rc, 0)
        self.assertEqual(u.downloaded, self.image)
        self.assertIn("2 retransmissions", self.out.getvalue())
        self.assertIn("block 1 not acknowledged", self.out.getvalue())

    def test_target_and_any(self):
        u = self.unit(identifier="AAAAAAAAAAAA")
        rc, _ = self.run_upgrade(u, target="AAAAAAAAAAAA")
        self.assertEqual(rc, 0)
        u2 = self.unit(identifier="BBBBBBBBBBBB")
        rc, _ = self.run_upgrade(u2, any_unit=True)
        self.assertEqual(rc, 0)
        reqs = [d for d, a in u2.received if len(d) == 160]
        self.assertEqual(reqs[0][0], 2)             # no discovery first
        self.assertEqual(reqs[0][8:20], b"FFFFFFFFFFFF")

    def test_wrong_target_refused(self):
        u = self.unit(identifier="AAAAAAAAAAAA")
        with self.assertRaises(rec.RecoverError) as cm:
            self.run_upgrade(u, target="BBBBBBBBBBBB")
        self.assertIn("no unit answered", str(cm.exception))
        # The request named the other unit, so this one ignored it.
        self.assertEqual(u.received[0][0], expected_request(0, "BBBBBBBBBBBB"))
        self.assertIsNone(u.downloaded)

    def test_nobody_answers(self):
        u = self.unit()
        u.stopped = True
        with self.assertRaises(rec.RecoverError) as cm:
            self.run_upgrade(u)
        self.assertIn("no unit answered", str(cm.exception))

    def test_bad_image_refused_by_client(self):
        u = self.unit()
        bad = bytearray(self.image)
        bad[0x200] ^= 1                              # section data
        with self.assertRaises(rec.RecoverError) as cm:
            self.run_upgrade(u, image=bytes(bad))
        self.assertIn("installer's checks", str(cm.exception))
        self.assertIn("data MD5 wrong", self.out.getvalue())
        self.assertEqual(u.received, [])             # nothing was sent

    def test_bad_image_refused_by_unit(self):
        """--no-verify sends it; the fake unit's installer (the spec's
        steps 2-6) rejects it and goes on listening, which the client
        reports as a probable failure."""
        u = self.unit()
        bad = bytearray(self.image)
        bad[0x200] ^= 1
        rc, _ = self.run_upgrade(u, image=bytes(bad), verify_image=False)
        self.assertEqual(rc, 2)
        self.assertEqual(u.install_error, "section 0 MD5")
        self.assertFalse(u.stopped)
        self.assertIn("still answers", self.out.getvalue())

    def test_unit_installer_checks(self):
        """The fake unit's installer follows §5 steps 2-6 on images the
        verifier would also refuse."""
        u = FakeUnit()
        u.close()
        img = self.image
        self.assertIsNone(u.install(img))
        self.assertEqual(u.installed[0][0], 2)
        self.assertIn("short", u.install(img[:0xFF]))
        self.assertIn("SPA3000", u.install(b"x" + img[1:]))
        self.assertIn("header and table", u.install(img[:-1]))
        b = bytearray(img)
        b[0x40] = 1
        self.assertEqual(u.install(bytes(b)), "global MD5")
        for v in (b"0.9.0", b"1.0.6", b"2.0.1", b"junk"):
            b = bytearray(img)
            b[0x5C:0x7C] = v + bytes(0x20 - len(v))
            b[0x30:0x40] = __import__("hashlib").md5(
                b[:0x10] + bytes(0x30) + b[0x40:0x100]).digest()
            self.assertIn("version", u.install(bytes(b)))
        b = bytearray(img)
        b[0x100 + 0x28] ^= 1                          # entry copy version
        self.assertEqual(u.install(bytes(b)), "entry 0 byte sum")

    def test_no_post_check(self):
        u = self.unit()
        rc, _ = self.run_upgrade(u, post_check=False)
        self.assertEqual(rc, 0)
        self.assertIn("post-check skipped", self.out.getvalue())
        reqs = [d for d, a in u.received if len(d) == 160]
        self.assertEqual([r[0] for r in reqs], [0, 2])

    def test_image_notes(self):
        img = bytearray(self.image)
        rec.describe_image(bytes(img), self.log, (2,))
        self.assertIn("section types 2", self.out.getvalue())
        # A type 1 section is reported as one the unit will skip.
        e = bytearray(img[0x80:0x100])
        e[8] = 1
        struct.pack_into(">I", e, 4, pack.TAGS[1])
        struct.pack_into(">H", e, 0x7E, sum(e[:0x7E]) & 0xFFFF)
        img[0x80:0x100] = e
        img[0x100:0x180] = e
        with self.assertRaises(rec.RecoverError):
            rec.describe_image(bytes(img), self.log, (2,))
        self.assertIn("type 2 and above", self.out.getvalue())
        self.assertIn("no type 2 section", self.out.getvalue())


# --- TFTP server on its own --------------------------------------------------

class TftpTest(unittest.TestCase):
    def setUp(self):
        self.out = io.StringIO()
        self.log = rec.Log(self.out)
        self.server = rec.open_socket(0, LO)
        self.client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.client.bind((LO, 0))
        self.client.settimeout(2)
        self.addCleanup(self.server.close)
        self.addCleanup(self.client.close)
        self.cfg = rec.Config(rrq_timeout=1.0, block_timeout=0.3,
                              block_retries=2)
        self.saddr = (LO, self.server.getsockname()[1])

    def fetch(self, blob, name="f", mode=b"octet", drop=()):
        import threading
        result = {}

        def serve():
            try:
                import time
                peer = rec.wait_rrq(self.server, self.cfg, self.log, "f",
                                    time.monotonic() + 1.0)
                result["retx"] = rec.send_file(self.server, self.cfg,
                                               self.log, blob, peer)
            except rec.RecoverError as ex:
                result["error"] = str(ex)
        t = threading.Thread(target=serve)
        t.start()
        self.client.sendto(b"\0\x01" + name.encode() + b"\0" + mode + b"\0",
                           self.saddr)
        got = b""
        expect = 1
        drop = set(drop)
        while True:
            try:
                data, addr = self.client.recvfrom(4096)
            except socket.timeout:
                break
            op, n = struct.unpack_from(">HH", data)
            if op == 5:
                result["client_error"] = data
                break
            if n == expect and expect in drop:
                drop.discard(expect)
                continue
            if n == expect:
                got += data[4:]
                expect += 1
            self.client.sendto(struct.pack(">HH", 4, n), addr)
            if len(data) - 4 < 512:
                break
        t.join(3)
        return got, result

    def test_exact_multiple_of_block(self):
        blob = bytes(range(256)) * 4                  # 1024 bytes
        got, result = self.fetch(blob)
        self.assertEqual(got, blob)
        self.assertEqual(result, {"retx": 0})
        self.assertIn("block 3 of 3", self.out.getvalue())

    def test_odd_length_with_drops(self):
        blob = b"\xAA" * 1300
        got, result = self.fetch(blob, drop=(2,))
        self.assertEqual(got, blob)
        self.assertEqual(result, {"retx": 1})

    def test_wrong_name_and_mode(self):
        got, result = self.fetch(b"x" * 10, name="other")
        self.assertEqual(result.get("client_error")[:4],
                         struct.pack(">HH", 5, 1))
        self.assertIn("did not ask for the file", result["error"])
        self.out.truncate(0)
        got, result = self.fetch(b"x" * 10, mode=b"netascii")
        self.assertEqual(result.get("client_error")[:4],
                         struct.pack(">HH", 5, 0))
        self.assertIn("octet mode", self.out.getvalue())

    def test_never_acknowledged(self):
        import threading
        import time
        result = {}

        def serve():
            try:
                peer = rec.wait_rrq(self.server, self.cfg, self.log, "f",
                                    time.monotonic() + 1.0)
                rec.send_file(self.server, self.cfg, self.log, b"z" * 10,
                              peer)
            except rec.RecoverError as ex:
                result["error"] = str(ex)
        t = threading.Thread(target=serve)
        t.start()
        self.client.sendto(b"\0\x01f\0octet\0", self.saddr)
        t.join(5)
        self.assertIn("block 1 of 1 never acknowledged", result["error"])
        self.assertEqual(self.out.getvalue().count("resending"), 2)


# --- Command line ----------------------------------------------------------

class CliTest(Fixture):
    def test_discover_and_upgrade(self):
        u = self.unit(identifier="001122334455")
        port = self.port
        common = ["--group", LO, "--unit-port", str(u.port),
                  "--reply-port", str(port), "--reply-timeout", "0.4"]
        rc = rec.main(["discover"] + common, self.out)
        self.assertEqual(rc, 0)
        self.assertIn("1 unit answered", self.out.getvalue())
        path = os.path.join(self.tmp.name, "prog.bin")
        with open(path, "wb") as f:
            f.write(self.image)
        rc = rec.main(["upgrade", path, "--tftp-port", "0", "--install-wait",
                       "0.3", "--block-timeout", "0.5", "-v"] + common,
                      self.out)
        self.assertEqual(rc, 0, self.out.getvalue())
        self.assertTrue(wait_until(lambda: u.stopped))
        self.assertEqual(u.downloaded, self.image)
        reqs = [d for d, a in u.received if len(d) == 160]
        self.assertEqual([r[0] for r in reqs], [0, 0, 2, 0])
        self.assertEqual(reqs[2][0x20:0x29], b"prog.bin\0")
        self.assertIn("    0000  ", self.out.getvalue())     # hex dump

    def test_discover_nobody(self):
        u = self.unit()
        u.stopped = True
        rc = rec.main(["discover", "--group", LO, "--unit-port",
                       str(u.port), "--reply-port", str(free_port()),
                       "--reply-timeout", "0.2"], self.out)
        self.assertEqual(rc, 1)
        self.assertIn("0 units answered", self.out.getvalue())

    def test_bad_arguments(self):
        with self.assertRaises(SystemExit):
            rec.main(["upgrade"], self.out)
        with self.assertRaises(SystemExit):
            rec.main(["upgrade", "x", "--port-width", "8"], self.out)
        rc = rec.main(["upgrade", os.path.join(self.tmp.name, "missing"),
                       "--group", LO, "--unit-port", "1", "--reply-port",
                       "0"], self.out)
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
