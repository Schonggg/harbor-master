"""Serve the Bridge over HTTPS with one command.

Two modes:

  py -3 scripts/serve_https.py                 # full stack: FastAPI + web/ on https://localhost:8443
  py -3 scripts/serve_https.py --static-only   # web/ only (offline replay mode) on https://localhost:8443

A self-signed certificate is generated into certs/ on first run (needs the
`cryptography` package, which is already a FastAPI transitive dependency).
Browsers will show a one-time warning for the self-signed cert; accept it.

For a public HTTPS URL, either push web/ to any static host (GitHub Pages,
Netlify, Vercel, Cloudflare Pages) and point it at a backend with
`?api=https://your-backend`, or tunnel this server with
`cloudflared tunnel --url https://localhost:8443 --no-tls-verify`.
"""

from __future__ import annotations

import argparse
import datetime as dt
import ipaddress
import os
import ssl
import subprocess
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
CERT_DIR = ROOT / "certs"
CERT = CERT_DIR / "cert.pem"
KEY = CERT_DIR / "key.pem"


def ensure_cert(hosts: list[str]) -> None:
    if CERT.exists() and KEY.exists():
        return
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
    except ImportError:
        sys.exit("cryptography not installed: pip install cryptography (or `pip install -e .`)")

    CERT_DIR.mkdir(exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Harbormaster Bridge (dev)")])
    sans = []
    for h in hosts:
        try:
            sans.append(x509.IPAddress(ipaddress.ip_address(h)))
        except ValueError:
            sans.append(x509.DNSName(h))
    now = dt.datetime.now(dt.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=825))
        .add_extension(x509.SubjectAlternativeName(sans), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    KEY.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    CERT.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    print(f"[https] generated self-signed cert -> {CERT}")


class StaticHandler(SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        # Never cache during demos; the JS import map + ES modules must stay fresh.
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt: str, *args) -> None:  # quieter console
        if "/api/" in (args[0] if args else ""):
            super().log_message(fmt, *args)


def serve_static(host: str, port: int) -> None:
    handler = partial(StaticHandler, directory=str(WEB))
    httpd = ThreadingHTTPServer((host, port), handler)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(certfile=str(CERT), keyfile=str(KEY))
    httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
    print(f"[https] static Bridge (offline replay mode) at https://{host}:{port}/")
    print("[https] add ?api=https://your-backend to the URL to go live")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


def serve_full(host: str, port: int, extra: list[str]) -> None:
    cmd = [
        sys.executable, "-m", "uvicorn", "harbormaster.api.main:app",
        "--host", host, "--port", str(port),
        "--ssl-keyfile", str(KEY), "--ssl-certfile", str(CERT),
        *extra,
    ]
    print(f"[https] FastAPI + Bridge at https://{host}:{port}/")
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src") + os.pathsep + os.environ.get("PYTHONPATH", "")}
    raise SystemExit(subprocess.call(cmd, cwd=str(ROOT), env=env))


def serve_tunnel(port: int, extra: list[str]) -> None:
    """Plain HTTP uvicorn on loopback + a Cloudflare quick tunnel = public, trusted HTTPS URL."""
    import shutil
    import threading

    env = {**os.environ, "PYTHONPATH": str(ROOT / "src") + os.pathsep + os.environ.get("PYTHONPATH", "")}
    api = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "harbormaster.api.main:app", "--host", "127.0.0.1", "--port", str(port), *extra],
        cwd=str(ROOT), env=env,
    )
    cf = shutil.which("cloudflared")
    cmd = [cf] if cf else (["npx", "--yes", "cloudflared"] if shutil.which("npx") else None)
    if not cmd:
        api.terminate()
        sys.exit("need `cloudflared` or `npx` on PATH for --tunnel (winget install Cloudflare.cloudflared)")
    print(f"[https] backend on http://127.0.0.1:{port} ; opening Cloudflare quick tunnel ...")
    tun = subprocess.Popen([*cmd, "tunnel", "--url", f"http://127.0.0.1:{port}"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, shell=os.name == "nt" and not cf)

    def pump() -> None:
        for line in tun.stdout or []:
            if "trycloudflare.com" in line:
                url = line.strip().split("https://", 1)[-1].split()[0]
                print(f"\n[https] PUBLIC URL  ->  https://{url}/\n", flush=True)
            elif "error" in line.lower():
                print(line.rstrip(), flush=True)

    threading.Thread(target=pump, daemon=True).start()
    try:
        api.wait()
    except KeyboardInterrupt:
        pass
    finally:
        tun.terminate()
        api.terminate()


def _https_already_up(port: int) -> bool:
    import ssl
    import urllib.error
    import urllib.request

    ctx = ssl._create_unverified_context()
    try:
        urllib.request.urlopen(f"https://127.0.0.1:{port}/", context=ctx, timeout=2)
        return True
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _port_holder(port: int) -> str:
    """Best-effort hint for who is sitting on the port."""
    if os.name != "nt":
        return ""
    try:
        out = subprocess.check_output(["netstat", "-ano"], text=True, errors="ignore")
    except OSError:
        return ""
    for line in out.splitlines():
        if f":{port}" in line and "LISTENING" in line.upper():
            return f"PID {line.split()[-1]}"
    return ""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="0.0.0.0", help="bind address (default 0.0.0.0 so a projector laptop can reach it)")
    ap.add_argument("--port", type=int, default=8443)
    ap.add_argument("--static-only", action="store_true", help="serve web/ only; Bridge runs in offline replay mode")
    ap.add_argument("--tunnel", action="store_true", help="expose a public trusted-HTTPS URL via a Cloudflare quick tunnel (no cert warning)")
    ap.add_argument("--san", action="append", default=[], help="extra hostname/IP for the certificate (repeatable)")
    args, extra = ap.parse_known_args()

    if args.tunnel:
        serve_tunnel(args.port if args.port != 8443 else 8000, extra)
        return
    ensure_cert(["localhost", "127.0.0.1", "::1", *args.san])
    if _https_already_up(args.port):
        print(f"[https] already running. Open in Chrome or Edge (not Cursor's preview):")
        print(f"        https://localhost:{args.port}/")
        print("[https] first visit: Advanced -> Proceed to localhost (self-signed cert).")
        return
    holder = _port_holder(args.port)
    if holder:
        print(f"[https] port {args.port} is busy ({holder}) but not serving HTTPS.")
        print("[https] retry with a free port:  py -3 scripts/serve_https.py --port 8444")
        raise SystemExit(1)
    if args.static_only:
        serve_static(args.host, args.port)
    else:
        serve_full(args.host, args.port, extra)


if __name__ == "__main__":
    main()
