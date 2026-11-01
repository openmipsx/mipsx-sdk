#!/usr/bin/env python3
"""mipsx-recover: sends an upgrade image to an SPA3000 that is running
its recovery program (section B), over the multicast recovery protocol.

Copyright 2026 The mipsx-sdk authors.
SPDX-License-Identifier: Apache-2.0

Written from openmipsx/devices common/firmware-image-format.md ("format
spec") §5 (Section B), §7.1 and the public description it cites, alone,
with no vendor code or data.  Python 3 standard library only.  See
tools/README.md for usage and for the points the format spec leaves
open; each of those is a command-line option here, defaulting to the
most conservative reading.

Usage: mipsx_recover.py discover [options]
       mipsx_recover.py upgrade IMAGE [options]

The protocol (format spec §7.1): the unit listens on UDP port 4810,
joined to multicast group 234.4.8.10.  A 160-byte request carries the
message type in byte 0, the magic 'RECM' at offset 4 and a target
identifier from offset 8 ('FFFFFFFFFFFF' matches any unit).  Type 0 asks
for a 100-byte type 1 reply naming the unit; type 2 asks the unit to
fetch the file named at offset 0x20 by TFTP, through the port at 0x1C,
and install it.  Replies go to port 4811.  The unit sends its TFTP read
request from its port 4810 to 234.4.8.10 at the given port, and its
acknowledgements to the socket that answered, so this program serves
the image from a socket bound to that port and joined to the group.
"""

import argparse
import ipaddress
import os
import select
import socket
import struct
import sys
import time

GROUP = "234.4.8.10"                  # format spec §7.1
UNIT_PORT = 4810                      # the unit listens here
REPLY_PORT = 4811                     # replies go here; we send from here
REQUEST_LEN = 160
REPLY_LEN = 100
MAGIC = b"RECM"                       # 0x5245434D big-endian at offset 4
WILDCARD = "FFFFFFFFFFFF"             # target matching any unit
MSG_DISCOVER, MSG_DISCOVER_REPLY, MSG_UPGRADE = 0, 1, 2
# Request layout.  The identifier field is 20 bytes in the public
# description (0x08-0x1B); the format spec only says NUL-terminated from
# offset 8.  Keeping it to 19 characters plus NUL satisfies both.
ID_OFF, ID_LEN = 0x08, 20
PORT_OFF = 0x1C                       # TFTP port (width: --port-width)
NAME_OFF = 0x20                       # file name, NUL-terminated
NAME_USED = 67                        # the unit uses this many bytes
# Type 1 reply layout (public description; unconfirmed on the SPA3000).
R_ID, R_MODEL, R_MAC, R_VERSION, R_HW, R_IP, R_UNKNOWN = (
    0x08, 0x1C, 0x30, 0x36, 0x4A, 0x5E, 0x62)

# TFTP (RFC 1350).
TFTP_PORT = 69
TFTP_BLOCK = 512
OP_RRQ, OP_WRQ, OP_DATA, OP_ACK, OP_ERROR, OP_OACK = 1, 2, 3, 4, 5, 6
TFTP_ERRORS = {0: "not defined", 1: "file not found", 2: "access violation",
               3: "disk full", 4: "illegal operation", 5: "unknown transfer "
               "ID", 6: "file already exists", 7: "no such user",
               8: "option refused"}


class RecoverError(Exception):
    pass


class Log:
    """Progress lines with a time stamp, and hex dumps when verbose."""

    def __init__(self, out=None, verbose=False):
        self.out = out or sys.stdout
        self.verbose = verbose
        self.t0 = time.monotonic()

    def __call__(self, msg):
        self.out.write("[%7.3f] %s\n" % (time.monotonic() - self.t0, msg))
        self.out.flush()

    def packet(self, what, addr, data):
        if not self.verbose:
            return
        self("%s %s:%d, %d bytes" % (what, addr[0], addr[1], len(data)))
        for off in range(0, len(data), 16):
            chunk = data[off:off + 16]
            text = "".join(chr(c) if 0x20 <= c < 0x7F else "." for c in chunk)
            self("    %04x  %-48s %s" % (off, chunk.hex(" "), text))


# --- Messages --------------------------------------------------------------

def cstring(data, off, length):
    """The NUL-terminated string in DATA[off:off+length], as text."""
    s = data[off:off + length].split(b"\0", 1)[0]
    return s.decode("ascii", "replace")


def build_request(mtype, target=WILDCARD, tftp_port=0, name="",
                  port_width=16):
    """A 160-byte request (format spec §7.1): type in byte 0, 'RECM' at
    4, the target identifier NUL-terminated from 8, and for an upgrade
    the TFTP port at 0x1C (PORT_WIDTH bits, big-endian) and the file
    name NUL-terminated at 0x20.  Everything else is zero."""
    tid = target.encode("ascii")
    if not tid or len(tid) >= ID_LEN:
        raise RecoverError("target identifier must be 1-%d characters"
                           % (ID_LEN - 1))
    req = bytearray(REQUEST_LEN)
    req[0] = mtype
    req[4:8] = MAGIC
    req[ID_OFF:ID_OFF + len(tid)] = tid
    if mtype == MSG_UPGRADE:
        if not 0 < tftp_port < 0x10000:
            raise RecoverError("TFTP port out of range")
        if port_width == 16:
            struct.pack_into(">H", req, PORT_OFF, tftp_port)
        elif port_width == 32:
            struct.pack_into(">I", req, PORT_OFF, tftp_port)
        else:
            raise RecoverError("port width must be 16 or 32")
        fname = name.encode("ascii")
        if not fname or b"\0" in fname:
            raise RecoverError("file name must be non-empty ASCII")
        if len(fname) >= NAME_USED:
            raise RecoverError("file name longer than %d characters; the "
                               "unit reads only %d bytes of it"
                               % (NAME_USED - 1, NAME_USED))
        req[NAME_OFF:NAME_OFF + len(fname)] = fname
    return bytes(req)


class UnitInfo:
    """What a type 1 reply says about a unit."""

    def __init__(self, data, addr):
        self.addr = addr
        self.raw = data
        self.identifier = cstring(data, R_ID, R_MODEL - R_ID)
        self.model = cstring(data, R_MODEL, R_MAC - R_MODEL)
        self.mac = ":".join("%02x" % c for c in data[R_MAC:R_MAC + 6])
        self.version = cstring(data, R_VERSION, R_HW - R_VERSION)
        self.hardware = cstring(data, R_HW, R_IP - R_HW)
        self.ip = socket.inet_ntoa(data[R_IP:R_IP + 4])
        self.unknown = data[R_UNKNOWN:R_UNKNOWN + 2]

    def __str__(self):
        return ("%s  model %s  mac %s  recovery %s  hardware %s  ip %s  "
                "(0x62: %s, from %s:%d)"
                % (self.identifier, self.model, self.mac, self.version,
                   self.hardware, self.ip, self.unknown.hex(), *self.addr))


def classify_reply(data):
    """(type, problem) for a datagram received on the reply port.  TYPE is
    None if it is not a recovery-protocol message at all; PROBLEM names
    what is off about a message that is one but does not match the
    public description (length), else None."""
    if len(data) < 8 or data[4:8] != MAGIC:
        return None, None
    problem = None
    if len(data) != REPLY_LEN:
        problem = "length %d, expected %d" % (len(data), REPLY_LEN)
    return data[0], problem


# --- Sockets ---------------------------------------------------------------

def is_multicast(addr):
    return ipaddress.IPv4Address(addr).is_multicast


def open_socket(port, group, interface=None, ttl=1):
    """A UDP socket bound to PORT on every address, joined to GROUP (if
    it is a multicast address) on INTERFACE (a local IPv4 address, or
    None for the system's choice), sending multicast with TTL."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, "SO_REUSEPORT"):
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    try:
        s.bind(("", port))
    except OSError as ex:
        s.close()
        raise RecoverError("cannot bind UDP port %d: %s" % (port, ex))
    if is_multicast(group):
        iface = socket.inet_aton(interface or "0.0.0.0")
        s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                     socket.inet_aton(group) + iface)
        if interface:
            s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, iface)
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl)
    return s


def recv_within(sock, timeout):
    """Yields (data, addr) for every datagram arriving within TIMEOUT
    seconds."""
    deadline = time.monotonic() + timeout
    while True:
        left = deadline - time.monotonic()
        if left <= 0:
            return
        r, _, _ = select.select([sock], [], [], left)
        if r:
            yield sock.recvfrom(4096)


class Config:
    """Addresses, ports and timings; see tools/README.md and parse_args.
    Attributes are set from an argparse namespace."""

    group = GROUP
    unit_port = UNIT_PORT
    reply_port = REPLY_PORT
    tftp_port = TFTP_PORT
    interface = None
    ttl = 1
    port_width = 16
    unicast = None            # send requests to this address, not the group
    reply_timeout = 2.5       # the public description's wait
    repeat = 1                # discovery requests
    rrq_timeout = 60.0        # from the request to the unit's read request
    block_timeout = 5.0       # per TFTP block
    block_retries = 5
    install_wait = 30.0       # before asking the unit whether it is alive
    post_check = True

    def __init__(self, **kw):
        for k, v in kw.items():
            if not hasattr(Config, k):
                raise TypeError("unknown option %r" % k)
            setattr(self, k, v)

    def destination(self):
        return (self.unicast or self.group, self.unit_port)


# --- Discovery -------------------------------------------------------------

def send_request(sock, cfg, req, log, what):
    dest = cfg.destination()
    log.packet("send %s to" % what, dest, req)
    sock.sendto(req, dest)


def collect_replies(sock, cfg, log, expect, target=None):
    """Replies of type EXPECT arriving within the reply timeout, as
    (data, addr).  Every datagram is logged; the ones that are not
    recovery-protocol messages, or not of the type asked for, are
    reported and left out.  With TARGET, replies naming another
    identifier are reported and left out too."""
    out = []
    for data, addr in recv_within(sock, cfg.reply_timeout):
        log.packet("received from", addr, data)
        mtype, problem = classify_reply(data)
        if mtype is None:
            log("ignored %d bytes from %s:%d: not a recovery message"
                % (len(data), *addr))
            continue
        if problem:
            log("warning: type %d reply from %s:%d has %s"
                % (mtype, *addr, problem))
        if mtype != expect:
            log("ignored type %d reply from %s:%d (waiting for type %d)"
                % (mtype, *addr, expect))
            continue
        if (target and target != WILDCARD and mtype == MSG_DISCOVER_REPLY
                and cstring(data, R_ID, R_MODEL - R_ID) != target):
            log("ignored reply from another unit, %s"
                % cstring(data, R_ID, R_MODEL - R_ID))
            continue
        out.append((data, addr))
    return out


def discover(sock, cfg, log, target=WILDCARD):
    """Sends a type 0 request (cfg.repeat times at most, stopping once
    something answers) and returns the units that replied, one UnitInfo
    per identifier."""
    req = build_request(MSG_DISCOVER, target)
    units = {}
    for attempt in range(cfg.repeat):
        send_request(sock, cfg, req, log, "discovery (type 0)")
        for data, addr in collect_replies(sock, cfg, log,
                                          MSG_DISCOVER_REPLY, target):
            if len(data) < REPLY_LEN:
                log("cannot parse a short reply; raw: %s" % data.hex())
                continue
            u = UnitInfo(data, addr)
            if u.identifier not in units:
                log("unit: %s" % u)
            units[u.identifier] = u
        if units:
            break
        if attempt + 1 < cfg.repeat:
            log("no reply within %.1f s; asking again" % cfg.reply_timeout)
    return list(units.values())


# --- TFTP server -----------------------------------------------------------

def tftp_error(sock, addr, code, text):
    sock.sendto(struct.pack(">HH", OP_ERROR, code) + text.encode("ascii")
                + b"\0", addr)


def parse_rrq(data):
    """(filename, mode, options) of a read request, or None."""
    if len(data) < 4 or struct.unpack_from(">H", data)[0] != OP_RRQ:
        return None
    fields = data[2:].split(b"\0")
    if len(fields) < 3 or fields[-1] != b"":
        return None
    opts = fields[2:-1]
    options = dict(zip(opts[0::2], opts[1::2]))
    return fields[0], fields[1], options


def wait_rrq(sock, cfg, log, name, deadline):
    """Waits for a read request for NAME in octet mode and returns the
    requester's address.  Requests for other files or modes are refused
    with a TFTP error and reported; anything else is reported."""
    fname = name.encode("ascii")
    while True:
        left = deadline - time.monotonic()
        if left <= 0:
            raise RecoverError("the unit did not ask for the file within "
                               "%.0f s" % cfg.rrq_timeout)
        r, _, _ = select.select([sock], [], [], left)
        if not r:
            continue
        data, addr = sock.recvfrom(4096)
        log.packet("tftp received from", addr, data)
        rrq = parse_rrq(data)
        if rrq is None:
            op = struct.unpack_from(">H", data)[0] if len(data) >= 2 else -1
            if op == OP_ERROR and len(data) >= 4:
                code = struct.unpack_from(">H", data, 2)[0]
                log("tftp error %d (%s) from %s:%d: %s"
                    % (code, TFTP_ERRORS.get(code, "?"), *addr,
                       cstring(data, 4, len(data) - 4)))
            else:
                log("ignored %d bytes from %s:%d on the TFTP port (opcode "
                    "%d)" % (len(data), *addr, op))
            continue
        rname, mode, options = rrq
        log("read request from %s:%d for %r, mode %r%s"
            % (*addr, rname.decode("ascii", "replace"),
               mode.decode("ascii", "replace"),
               ", options %r (ignored)" % options if options else ""))
        if rname != fname:
            log("refused: the file name differs from %r" % name)
            tftp_error(sock, addr, 1, "file not found")
            continue
        if mode.lower() != b"octet":
            log("refused: only octet mode is served")
            tftp_error(sock, addr, 0, "octet mode only")
            continue
        return addr


def send_file(sock, cfg, log, image, peer):
    """Sends IMAGE to PEER in 512-byte blocks, each acknowledged before
    the next, retransmitting an unacknowledged block cfg.block_retries
    times.  Returns the number of retransmissions."""
    nblocks = len(image) // TFTP_BLOCK + 1    # last block short or empty
    retransmits = 0
    next_report = 0
    for n in range(1, nblocks + 1):
        payload = image[(n - 1) * TFTP_BLOCK:n * TFTP_BLOCK]
        pkt = struct.pack(">HH", OP_DATA, n & 0xFFFF) + payload
        for attempt in range(cfg.block_retries + 1):
            if attempt:
                retransmits += 1
                log("block %d not acknowledged within %.1f s; resending "
                    "(%d of %d)" % (n, cfg.block_timeout, attempt,
                                    cfg.block_retries))
            sock.sendto(pkt, peer)
            if wait_ack(sock, cfg, log, n & 0xFFFF, peer):
                break
        else:
            raise RecoverError("block %d of %d never acknowledged"
                               % (n, nblocks))
        done = n * TFTP_BLOCK
        if done >= next_report or n == nblocks:
            log("sent %d of %d bytes (block %d of %d)"
                % (min(done, len(image)), len(image), n, nblocks))
            next_report = done + max(len(image) // 10, TFTP_BLOCK)
    return retransmits


def wait_ack(sock, cfg, log, block, peer):
    """True once PEER acknowledges BLOCK; False on timeout.  Old
    acknowledgements and other traffic are reported and skipped; a TFTP
    error from the peer aborts."""
    for data, addr in recv_within(sock, cfg.block_timeout):
        log.packet("tftp received from", addr, data)
        if addr != peer:
            log("ignored %d bytes from %s:%d during the transfer"
                % (len(data), *addr))
            continue
        if len(data) < 4:
            log("ignored a %d-byte datagram from the unit" % len(data))
            continue
        op, arg = struct.unpack_from(">HH", data)
        if op == OP_ACK:
            if arg == block:
                return True
            log("ignored acknowledgement of block %d (waiting for %d)"
                % (arg, block))
        elif op == OP_ERROR:
            raise RecoverError("the unit aborted the transfer: error %d "
                               "(%s) %s" % (arg, TFTP_ERRORS.get(arg, "?"),
                                            cstring(data, 4, len(data) - 4)))
        else:
            log("ignored TFTP opcode %d from the unit" % op)
    return False


# --- Upgrade ---------------------------------------------------------------

def describe_image(image, log, allow_types, strict=True):
    """Runs the verifier's installer checks over IMAGE and reports.
    Raises unless STRICT is off, when problems are only reported."""
    import mipsx_verify
    r = mipsx_verify.verify(image, allow_types=allow_types)
    for e in r.errors:
        log("image: %s" % e)
    count = struct.unpack_from(">I", image, 0x7C)[0] if len(image) >= 0x80 \
        else 0
    types = [image[0x80 + 0x80 * i + 8] for i in range(count)
             if 0x80 * (i + 2) <= len(image)]
    if len(image) >= 0x80:
        log("image: %d bytes, version %r, section types %s"
            % (len(image), cstring(image, 0x5C, 0x20),
               ", ".join(map(str, types)) or "none"))
    if any(t < 2 for t in types):
        log("note: the recovery program writes only sections of type 2 "
            "and above; the others in this image will be skipped")
    if 2 not in types:
        log("warning: no type 2 section: installing this clears the "
            "application slot, and the unit will keep starting the "
            "recovery program")
    if r.errors and strict:
        raise RecoverError("the image fails the installer's checks "
                           "(--no-verify to send it anyway)")


def choose_unit(sock, cfg, log, target, any_unit):
    """The identifier to address the upgrade to.  With ANY_UNIT the
    wildcard, without discovery.  Otherwise discovers first (addressing
    TARGET if given, so only that unit answers) and requires exactly one
    unit to have answered."""
    if any_unit:
        log("addressing any unit (%s) without discovery" % WILDCARD)
        return WILDCARD, None
    units = discover(sock, cfg, log, target or WILDCARD)
    if not units:
        raise RecoverError("no unit answered discovery; is one running "
                           "its recovery program on this network?")
    if len(units) > 1:
        raise RecoverError("%d units answered; name one with --target"
                           % len(units))
    u = units[0]
    log("upgrading %s (%s at %s)" % (u.identifier, u.model, u.ip))
    return u.identifier, u


def upgrade(cfg, image, name, log, target=None, any_unit=False,
            verify_image=True, allow_types=(2,)):
    """The whole exchange.  Returns 0 when the image was transferred and
    the unit then fell silent (installed, waiting for a power cycle), 2
    when it was transferred but the unit still answers (so the install
    probably failed), and raises RecoverError otherwise."""
    if verify_image:
        describe_image(image, log, allow_types)
    control = open_socket(cfg.reply_port, cfg.group, cfg.interface, cfg.ttl)
    tftp = open_socket(cfg.tftp_port, cfg.group, cfg.interface, cfg.ttl)
    try:
        tftp_port = tftp.getsockname()[1]
        log("control socket on port %d, TFTP server on port %d%s"
            % (control.getsockname()[1], tftp_port,
               ", joined to %s" % cfg.group if is_multicast(cfg.group)
               else ""))
        tid, unit = choose_unit(control, cfg, log, target, any_unit)
        req = build_request(MSG_UPGRADE, tid, tftp_port, name, cfg.port_width)
        deadline = time.monotonic() + cfg.rrq_timeout
        send_request(control, cfg, req, log, "upgrade request (type 2)")
        acks = collect_replies(control, cfg, log, MSG_UPGRADE)
        for data, addr in acks:
            if data == req[:len(data)]:
                log("acknowledged by %s:%d (request echoed, %d bytes)"
                    % (*addr, len(data)))
            else:
                log("type 2 reply from %s:%d is not an echo of the "
                    "request: %s" % (*addr, data.hex()))
        if not acks:
            log("no acknowledgement within %.1f s; waiting for the read "
                "request anyway" % cfg.reply_timeout)
        peer = wait_rrq(tftp, cfg, log, name, deadline)
        if unit and peer[0] != unit.ip:
            log("warning: the read request came from %s, the unit said "
                "it is %s" % (peer[0], unit.ip))
        t0 = time.monotonic()
        retransmits = send_file(tftp, cfg, log, image, peer)
        log("transfer complete: %d bytes in %.1f s, %d retransmission%s"
            % (len(image), time.monotonic() - t0, retransmits,
               "" if retransmits == 1 else "s"))
        if not cfg.post_check:
            log("the unit is now checking and writing the image; power-"
                "cycle it once its LEDs settle (--post-check skipped)")
            return 0
        log("waiting %.0f s for the unit to check and write the image"
            % cfg.install_wait)
        time.sleep(cfg.install_wait)
        units = discover(control, cfg, log, tid)
        if units:
            log("the unit still answers discovery, so it went back to "
                "listening: the install most likely failed (the "
                "recovery program reports no reason)")
            return 2
        log("the unit no longer answers: the image was most likely "
            "installed and the unit is waiting for a power cycle")
        return 0
    finally:
        control.close()
        tftp.close()


# --- Command line ----------------------------------------------------------

def parse_args(argv):
    p = argparse.ArgumentParser(
        description="Talk to an SPA3000 running its recovery program "
        "(section B) over the multicast recovery protocol.",
        epilog="tools/README.md lists what the format spec leaves open "
        "and which option covers each point.")
    sub = p.add_subparsers(dest="command", required=True)

    def common(sp):
        g = sp.add_argument_group("addresses (format spec §7.1 defaults)")
        g.add_argument("--group", default=GROUP,
                       help="multicast group, or a unicast address for a "
                       "unit on a known address (default %s)" % GROUP)
        g.add_argument("--unit-port", type=int, default=UNIT_PORT,
                       help="port the unit listens on (default %d)"
                       % UNIT_PORT)
        g.add_argument("--reply-port", type=int, default=REPLY_PORT,
                       help="port replies come to, and requests are sent "
                       "from (default %d)" % REPLY_PORT)
        g.add_argument("--interface", metavar="ADDR",
                       help="local IPv4 address of the interface to use "
                       "for multicast (default: the system's choice)")
        g.add_argument("--ttl", type=int, default=1,
                       help="multicast TTL (default 1: this network only)")
        g.add_argument("--unicast", metavar="ADDR",
                       help="send requests to this address instead of the "
                       "group (replies are still awaited on the group)")
        t = sp.add_argument_group("timing")
        t.add_argument("--reply-timeout", type=float, default=2.5,
                       help="seconds to wait for replies to a request "
                       "(default 2.5, the public description's figure)")
        t.add_argument("--repeat", type=int, default=1,
                       help="discovery requests to send before giving up "
                       "(default 1)")
        sp.add_argument("-v", "--verbose", action="store_true",
                        help="hex-dump every datagram sent and received")

    d = sub.add_parser("discover", help="list the units running their "
                       "recovery program")
    common(d)
    d.add_argument("--target", default=WILDCARD,
                   help="identifier to address (default %s, any unit)"
                   % WILDCARD)

    u = sub.add_parser("upgrade", help="send an image to one unit")
    common(u)
    u.add_argument("image", help="upgrade image, as mipsx_pack.py writes")
    u.add_argument("--name", help="file name the unit asks for by TFTP "
                   "(default: the image's base name, at most %d characters)"
                   % (NAME_USED - 1))
    g = u.add_argument_group("choosing the unit")
    g.add_argument("--target", help="identifier of the unit to upgrade; "
                   "default: discover, and require exactly one unit")
    g.add_argument("--any", action="store_true",
                   help="address the request to every unit (%s) without "
                   "discovering first" % WILDCARD)
    g = u.add_argument_group("request fields the spec leaves open")
    g.add_argument("--tftp-port", type=int, default=TFTP_PORT,
                   help="port to serve the image from and name in the "
                   "request (default %d, which needs privileges; 0 picks a "
                   "free port)" % TFTP_PORT)
    g.add_argument("--port-width", type=int, choices=(16, 32), default=16,
                   help="width in bits of the port field at 0x1C (default "
                   "16)")
    g = u.add_argument_group("TFTP and result")
    g.add_argument("--rrq-timeout", type=float, default=60,
                   help="seconds to wait for the unit's read request "
                   "(default 60)")
    g.add_argument("--block-timeout", type=float, default=5,
                   help="seconds to wait for each block's acknowledgement "
                   "(default 5)")
    g.add_argument("--block-retries", type=int, default=5,
                   help="retransmissions per block (default 5)")
    g.add_argument("--install-wait", type=float, default=30,
                   help="seconds to give the unit to check and write the "
                   "image before asking whether it still answers "
                   "(default 30)")
    g.add_argument("--no-post-check", action="store_true",
                   help="do not ask the unit afterwards whether it still "
                   "answers")
    g = u.add_argument_group("image checks")
    g.add_argument("--no-verify", action="store_true",
                   help="send the image even if mipsx_verify.py would "
                   "reject it")
    g.add_argument("--allow-types", default="2",
                   help="section types the verifier accepts (default 2)")
    return p.parse_args(argv)


def config_from(args):
    cfg = Config(group=args.group, unit_port=args.unit_port,
                 reply_port=args.reply_port, interface=args.interface,
                 ttl=args.ttl, unicast=args.unicast,
                 reply_timeout=args.reply_timeout, repeat=args.repeat)
    if args.command == "upgrade":
        cfg.tftp_port = args.tftp_port
        cfg.port_width = args.port_width
        cfg.rrq_timeout = args.rrq_timeout
        cfg.block_timeout = args.block_timeout
        cfg.block_retries = args.block_retries
        cfg.install_wait = args.install_wait
        cfg.post_check = not args.no_post_check
    return cfg


def main(argv=None, out=None):
    args = parse_args(argv)
    log = Log(out, args.verbose)
    cfg = config_from(args)
    try:
        if args.command == "discover":
            sock = open_socket(cfg.reply_port, cfg.group, cfg.interface,
                               cfg.ttl)
            try:
                units = discover(sock, cfg, log, args.target)
            finally:
                sock.close()
            log("%d unit%s answered" % (len(units),
                                        "" if len(units) == 1 else "s"))
            return 0 if units else 1
        with open(args.image, "rb") as f:
            image = f.read()
        name = args.name or os.path.basename(args.image)
        return upgrade(cfg, image, name, log, target=args.target,
                       any_unit=args.any, verify_image=not args.no_verify,
                       allow_types=tuple(int(t) for t in
                                         args.allow_types.split(",")))
    except (OSError, RecoverError) as ex:
        sys.stderr.write("mipsx-recover: error: %s\n" % ex)
        return 1


if __name__ == "__main__":
    sys.exit(main())
