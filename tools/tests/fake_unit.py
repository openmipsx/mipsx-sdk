#!/usr/bin/env python3
# A fake SPA3000 recovery program (section B) for testing mipsx_recover.py.
#
# Copyright 2026 The mipsx-sdk authors.
# SPDX-License-Identifier: Apache-2.0
#
# Follows the format spec's description of section B's main loop and
# installer (§5, "What section B does"; §7.1) on a UDP socket of its own,
# so that the client can be exercised on loopback.  It shares no code
# with the client or the verifier: its message layouts and checks are
# written again here from the spec, so a disagreement between the two
# shows up as a test failure.

import hashlib
import re
import socket
import struct
import threading
import time

MAGIC = b"SpA3000 FiRmWaRe"
RECM = 0x5245434D


class FakeUnit(threading.Thread):
    """One unit.  Listens on (host, port); replies go to REPLY_TO, either
    'sender' (the request's source address, at reply_port) or 'group'
    (group_addr, reply_port).  Its TFTP read request goes to group_addr
    at the port named in the upgrade request, from the listening socket,
    as the spec says.

    After a successful install it falls silent (the real program stops
    and waits for a power cycle); after a failed one it goes on
    listening and records the error in .install_error."""

    def __init__(self, identifier="001122334455", model="SPA-3000",
                 mac=b"\x00\x11\x22\x33\x44\x55", version="1.0.6(3k)",
                 hardware="1.0.0", ip="127.0.0.1", host="127.0.0.1",
                 group_addr="127.0.0.1", reply_port=4811, reply_to="sender",
                 port_width=16, drop_data_blocks=(), tftp_timeout=2.0):
        super().__init__(daemon=True)
        self.identifier, self.model, self.mac = identifier, model, mac
        self.version, self.hardware, self.ip = version, hardware, ip
        self.group_addr, self.reply_port = group_addr, reply_port
        self.reply_to, self.port_width = reply_to, port_width
        self.drop_data_blocks = set(drop_data_blocks)   # drop first copy
        self.tftp_timeout = tftp_timeout
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((host, 0))
        self.port = self.sock.getsockname()[1]
        self.received = []          # every datagram, (data, addr)
        self.sent = []              # every datagram, (data, addr)
        self.requests = []          # the recovery requests acted on
        self.downloaded = None      # the image received by TFTP
        self.installed = None       # [(type, entry, data)] once installed
        self.install_error = None
        self.stopped = False        # silent, "waiting for a power cycle"
        self.running = True
        self.log = []

    def close(self):
        self.running = False
        self.sock.close()

    def send(self, data, addr):
        self.sent.append((data, addr))
        self.sock.sendto(data, addr)

    def reply_addr(self, sender):
        if self.reply_to == "sender":
            return (sender[0], self.reply_port)
        return (self.group_addr, self.reply_port)

    # -- main loop: the recovery protocol (§7.1) ------------------------

    def run(self):
        self.sock.settimeout(0.2)
        while self.running:
            try:
                data, addr = self.sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                return
            self.received.append((data, addr))
            if self.stopped:
                continue
            # Messages are 160 bytes, magic at 4, target from 8.
            if len(data) != 160:
                self.log.append("ignored: length %d" % len(data))
                continue
            if struct.unpack_from(">I", data, 4)[0] != RECM:
                self.log.append("ignored: magic")
                continue
            target = data[8:].split(b"\0", 1)[0]
            if target not in (b"FFFFFFFFFFFF", self.identifier.encode()):
                self.log.append("ignored: target %r" % target)
                continue
            self.requests.append(data)
            if data[0] == 0:
                self.send(self.discovery_reply(), self.reply_addr(addr))
            elif data[0] == 2:
                self.send(data[:100], self.reply_addr(addr))
                self.upgrade(data)
            else:
                self.log.append("ignored: type %d" % data[0])

    def discovery_reply(self):
        """100 bytes: type 1, magic, identifier 0x08 (20), model 0x1C
        (20), MAC 0x30 (6), recovery version 0x36 (20), hardware version
        0x4A (20), IPv4 0x5E (4), two unknown bytes 0x62."""
        r = bytearray(100)
        r[0] = 1
        struct.pack_into(">I", r, 4, RECM)

        def put(off, s):
            b = s.encode("ascii")
            r[off:off + len(b)] = b
        put(0x08, self.identifier)
        put(0x1C, self.model)
        r[0x30:0x36] = self.mac
        put(0x36, self.version)
        put(0x4A, self.hardware)
        r[0x5E:0x62] = socket.inet_aton(self.ip)
        r[0x62:0x64] = b"\x00\x00"
        return bytes(r)

    # -- the upgrade: TFTP fetch (RFC 1350), then install (§5) ----------

    def upgrade(self, req):
        if self.port_width == 16:
            port = struct.unpack_from(">H", req, 0x1C)[0]
        else:
            port = struct.unpack_from(">I", req, 0x1C)[0]
        name = req[0x20:0x20 + 67].split(b"\0", 1)[0]
        server = (self.group_addr, port)
        self.send(struct.pack(">H", 1) + name + b"\0octet\0", server)
        image = bytearray()
        expect = 1
        peer = None
        self.sock.settimeout(self.tftp_timeout)
        try:
            while True:
                try:
                    data, addr = self.sock.recvfrom(4096)
                except socket.timeout:
                    self.install_error = "tftp: timed out waiting for " \
                        "block %d" % expect
                    return
                self.received.append((data, addr))
                if len(data) < 4:
                    continue
                op, arg = struct.unpack_from(">HH", data)
                if op == 5:
                    self.install_error = "tftp: server error %d" % arg
                    return
                if op != 3:
                    continue
                # Acknowledgements go to the socket that sent the data.
                peer = addr
                if arg == expect & 0xFFFF and expect in self.drop_data_blocks:
                    self.drop_data_blocks.discard(expect)
                    continue
                if arg == (expect - 1) & 0xFFFF:          # duplicate
                    self.send(struct.pack(">HH", 4, arg), peer)
                    continue
                if arg != expect & 0xFFFF:
                    continue
                image += data[4:]
                self.send(struct.pack(">HH", 4, arg), peer)
                expect += 1
                if len(data) - 4 < 512:
                    break
        finally:
            self.sock.settimeout(0.2)
        self.downloaded = bytes(image)
        err = self.install(self.downloaded)
        if err:
            self.install_error = err
        else:
            self.stopped = True

    def install(self, img):
        """Section B's installer checks (§5, Installing, steps 2-6) and
        what it writes (step 8).  Returns an error text or None."""
        if len(img) < 0x100 or img[:16] != MAGIC:
            return "too short or not an SPA3000 image"
        hsize, esize, total = struct.unpack_from(">III", img, 0x50)
        count = struct.unpack_from(">I", img, 0x7C)[0]
        start = hsize + esize * count
        if len(img) < start or len(img) < total:
            return "shorter than its header and table say"
        zeroed = img[:0x10] + bytes(0x30) + img[0x40:start]
        if hashlib.md5(zeroed).digest() != img[0x30:0x40]:
            return "global MD5"
        m = re.match(rb"(\d+)\.(\d+)\.(\d+)", img[0x5C:0x7C])
        if not m:
            return "version unparseable"
        major, minor = int(m.group(1)), int(m.group(2))
        if major == 0 or (major in (1, 2) and minor == 0):
            return "version refused (downgrade)"
        pos, sections = start, []
        for i in range(count):
            e = img[pos:pos + esize]
            if struct.unpack_from(">I", e, 0x7C)[0] != sum(e[:0x7C]):
                return "entry %d byte sum" % i
            doff, = struct.unpack_from(">I", e, 0x0C)
            length, = struct.unpack_from(">I", e, 0x20)
            data = img[pos + doff:pos + doff + length]
            if hashlib.md5(data).digest() != e[0x10:0x20]:
                return "section %d MD5" % i
            sections.append((e[8], e, data))
            pos += doff + length
        # Step 8: only types 2 and above are written, 4-byte aligned.
        self.installed = [(t, e, d + bytes(-len(d) % 4))
                          for t, e, d in sections if t >= 2]
        return None


def free_port(host="127.0.0.1"):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind((host, 0))
    port = s.getsockname()[1]
    s.close()
    return port


def wait_until(pred, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pred():
            return True
        time.sleep(0.02)
    return pred()
