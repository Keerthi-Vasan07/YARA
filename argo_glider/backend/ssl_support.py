"""TLS trust configuration for the INCOIS ERDDAP endpoint (Argo only).

Why this exists
---------------
erddap.incois.gov.in serves an INCOMPLETE certificate chain: it sends only its
leaf certificate (CN=*.incois.gov.in) and omits the issuing intermediate,
"GlobalSign RSA OV SSL CA 2018". Verified against the live host: the server
presents exactly 1 certificate.

Windows hides this bug, because its CryptoAPI trust engine automatically
downloads the missing intermediate using the certificate's AIA extension.
OpenSSL -- which is what Python/requests use on Linux, and therefore on Render --
does not do AIA fetching, so chain building stops at the leaf and verification
fails with:

    [SSL: CERTIFICATE_VERIFY_FAILED] unable to get local issuer certificate

Note that pointing requests at certifi alone does NOT fix this: certifi ships
root CAs, and the certificate that is missing here is an intermediate, so the
chain still cannot be completed.

The fix
-------
Supply the missing intermediate ourselves. certs/globalsign_rsa_ov_ssl_ca_2018.pem
is the genuine GlobalSign intermediate (subject "CN=GlobalSign RSA OV SSL CA 2018",
issued by "GlobalSign Root CA - R3", valid 2018-11-21 to 2028-11-21), obtained from
the caIssuers URL published in the leaf's own AIA extension.

Certificate verification remains FULLY enabled. We are only providing a chain
link the server should have sent; OpenSSL still validates signatures, expiry and
hostname, and still requires the chain to terminate at a root that is already
trusted in certifi. Nothing here weakens TLS, and nothing here changes Python's
global SSL behaviour -- the bundle is passed explicitly to the Argo request only,
so the Copernicus/OPeNDAP pipeline is unaffected.
"""
from __future__ import annotations

import atexit
import os
import tempfile
import threading

import certifi

_CERT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "certs")
INTERMEDIATE_PEM = os.path.join(_CERT_DIR, "globalsign_rsa_ov_ssl_ca_2018.pem")

_bundle_path: str | None = None
_bundle_lock = threading.Lock()


def incois_ca_bundle() -> str:
    """Path to a CA bundle of certifi's roots plus the intermediate INCOIS omits.

    Built once per process into a temp file and reused. Falls back to certifi's
    bundle alone if the intermediate is missing, so a packaging mistake degrades
    to the normal (possibly failing) verification rather than to no verification.
    """
    global _bundle_path

    with _bundle_lock:
        if _bundle_path and os.path.exists(_bundle_path):
            return _bundle_path

        if not os.path.exists(INTERMEDIATE_PEM):
            return certifi.where()

        with open(certifi.where(), "rb") as roots:
            root_bytes = roots.read()
        with open(INTERMEDIATE_PEM, "rb") as inter:
            inter_bytes = inter.read()

        handle, path = tempfile.mkstemp(prefix="yara_incois_ca_", suffix=".pem")
        with os.fdopen(handle, "wb") as out:
            out.write(root_bytes)
            if not root_bytes.endswith(b"\n"):
                out.write(b"\n")
            out.write(inter_bytes)

        atexit.register(_cleanup, path)
        _bundle_path = path
        return path


def _cleanup(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass
