# SPDX-License-Identifier: Apache-2.0
"""The interactive configuration, operated from the host as a person operates it.

Twister builds tests/framework/interactive and starts zephyr.exe in the build folder; the dut
fixture of Zephyr's pytest plugin reads its standard output, where Crux Logging writes. This file
then does what docs/native-sim-interactive.md tells a person to do: it opens the console's
pseudo-terminal, makes the first account and logs in, and it opens an HTTPS connection to the web
port on the host's loopback address. Last it restarts the program and checks that the certificate
and the account came back from the flash file. The password is made here for each run.

What this cannot show: a browser (the client is Python's ssl module, which does not check the
self-signed certificate), a web login, the port forwarding of a Dev Container, or anything on a
board.
"""

import hashlib
import os
import re
import secrets
import select
import socket
import ssl
import time
import tty

from twister_harness import DeviceAdapter

PORT = 8443
START_TIMEOUT_S = 120
CONSOLE_TIMEOUT_S = 30
CONNECT_ATTEMPTS = 50
CONNECT_RETRY_S = 0.2
USER = "operator"


def start(dut: DeviceAdapter):
    """Wait for a complete start; return the console's pseudo-terminal and the logged fingerprint."""
    lines = dut.readlines_until(regex=r"startup done phases=4 failed=0", timeout=START_TIMEOUT_S)
    text = "\n".join(lines)
    pty = re.search(r"uart_1 connected to pseudotty: (\S+)", text)
    assert pty, text
    assert f"https management started on 127.0.0.1 port {PORT}" in text, text
    assert "serial command line started on crux-serial0" in text, text
    fingerprint = re.search(r"certificate sha256=(\S+) source=(\w+)", text)
    assert fingerprint, text
    return pty.group(1), fingerprint.group(1), fingerprint.group(2)


def hex_only(text):
    return re.sub(r"[^0-9a-f]", "", text.lower())


class Console:
    """The console's pseudo-terminal, opened raw as a terminal program opens it."""

    def __init__(self, path):
        self.fd = os.open(path, os.O_RDWR | os.O_NOCTTY)
        tty.setraw(self.fd)
        self.text = ""

    def close(self):
        os.close(self.fd)

    def expect(self, wanted):
        deadline = time.monotonic() + CONSOLE_TIMEOUT_S
        while wanted not in self.text:
            left = deadline - time.monotonic()
            assert left > 0, f"the console did not write {wanted!r}; it wrote {self.text!r}"
            ready, _, _ = select.select([self.fd], [], [], left)
            if ready:
                self.text += os.read(self.fd, 256).decode(errors="replace")
        self.text = self.text[self.text.index(wanted) + len(wanted):]

    def type(self, line):
        os.write(self.fd, line.encode() + b"\r")


def https_answer():
    """Open TLS to the web port and send one request; return the status line and the certificate."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    last = None
    for _ in range(CONNECT_ATTEMPTS):
        try:
            with socket.create_connection(("127.0.0.1", PORT), timeout=10) as raw:
                with context.wrap_socket(raw) as tls:
                    certificate = tls.getpeercert(binary_form=True)
                    tls.sendall(b"GET / HTTP/1.1\r\nHost: 127.0.0.1:8443\r\nConnection: close\r\n\r\n")
                    answer = tls.recv(4096).decode(errors="replace")
                    return answer.split("\r\n", 1)[0], certificate, tls.version()
        except OSError as error:
            last = error
            time.sleep(CONNECT_RETRY_S)
    raise AssertionError(f"no HTTPS answer on 127.0.0.1:{PORT}: {last}")


def test_a_person_operates_the_base_image_from_the_host(dut: DeviceAdapter):
    password = secrets.token_urlsafe(18)

    pty, fingerprint, source = start(dut)
    assert source == "generated"

    status, certificate, version = https_answer()
    assert status.startswith("HTTP/1.1 "), status
    assert version == "TLSv1.3", version
    assert hex_only(fingerprint) == hashlib.sha256(certificate).hexdigest()

    console = Console(pty)
    try:
        console.type("")
        console.expect("login: ")
        console.type("!setup")
        console.expect("new user: ")
        console.type(USER)
        console.expect("password: ")
        console.type(password)
        console.expect("repeat: ")
        console.type(password)
        console.expect("account created")
        console.expect("login: ")
        console.type(USER)
        console.expect("password: ")
        console.type(password)
        console.expect("> ")
        console.type("logout")
        console.expect("login: ")
        assert password not in console.text
    finally:
        console.close()

    # The flash file in the build folder keeps the store: after a restart the certificate is the
    # stored one and the account logs in.
    dut.close()
    dut.launch()
    pty, fingerprint_again, source = start(dut)
    assert source == "stored"
    assert fingerprint_again == fingerprint

    console = Console(pty)
    try:
        console.type("")
        console.expect("login: ")
        console.type(USER)
        console.expect("password: ")
        console.type(password)
        console.expect("> ")
        console.type("logout")
        console.expect("login: ")
    finally:
        console.close()
