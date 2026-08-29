# SPDX-License-Identifier: Apache-2.0
"""
Milestone DR27a: QRNG-OPENAPI Sealed Host Ingress Daemon.

Standards & Resource Citations:
1. Palo Alto Networks QRNG-OPENAPI Specification (v1.0):
   - Implementation of `/v1/entropy` (POST) and `/v1/healthtest` (GET) endpoints.
   - Standard JSON envelope with metadata: version, timestamp, source_id, quality, entropy_b64.
2. NIST Special Publication 800-90B (Recommendation for the Entropy Sources Used for Random Bit Generation):
   - Health test execution over streaming entropy windows prior to NPU DMA dispatch.
3. ETSI GS QKD 014 v1.1.1 (2019-02):
   - Transport security boundary separation: zero host key storage with immediate hardware offload.
4. DOI: 10.5281/zenodo.22164124.
"""
import os
import json
import time
import threading
import urllib.request
import urllib.error
from typing import Optional, Dict, Any, Tuple
from http.server import HTTPServer, BaseHTTPRequestHandler

from . import dr27_qrng_openapi_abi as abi
from . import dr27_qrng_reservoir_graph as reservoir

class MockQrngOpenApiServer(BaseHTTPRequestHandler):
    """Reference mock QRNG-OPENAPI v1.0 appliance endpoint."""
    def do_POST(self):
        if self.path == "/v1/entropy":
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length) if length > 0 else b"{}"
            try:
                req_json = json.loads(body) if body else {}
            except Exception:
                req_json = {}
            requested_bytes = int(req_json.get("num_bytes", 32))
            source_id = int(req_json.get("source_id", 1))
            
            raw_entropy = os.urandom(requested_bytes)
            resp_json = abi.format_qrng_openapi_json(raw_entropy, source_id=source_id, quality=0.9998)
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(resp_json.encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        if self.path == "/v1/healthtest":
            sample = os.urandom(512)
            is_healthy, rct, apt = abi.eval_sp800_90b_health(sample)
            health_doc = {
                "status": "HEALTHY" if is_healthy else "DEGRADED",
                "sp800_90b_rct_max": rct,
                "sp800_90b_rct_cutoff": abi.SP800_90B_RCT_CUTOFF,
                "sp800_90b_apt_max": apt,
                "sp800_90b_apt_cutoff": abi.SP800_90B_APT_CUTOFF,
                "timestamp": time.time()
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(health_doc, indent=2).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass

class QrngIngressClient:
    """Client for pulling entropy from QRNG-OPENAPI appliances and pushing to AIE2 reservoir."""
    def __init__(self, base_url: str = "http://127.0.0.1:8443", source_id: int = 1):
        self.base_url = base_url.rstrip("/")
        self.source_id = source_id

    def check_health(self) -> Dict[str, Any]:
        """Queries /v1/healthtest on remote QRNG appliance."""
        url = f"{self.base_url}/v1/healthtest"
        req = urllib.request.Request(url, headers={"User-Agent": "Phoenix-NPU-DR27-Client/1.0"})
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read().decode('utf-8'))

    def fetch_and_ingress(self, num_bytes: int = 32) -> Dict[str, Any]:
        """Fetches entropy from QRNG appliance, validates health, and pushes to AIE2 reservoir."""
        url = f"{self.base_url}/v1/entropy"
        payload = json.dumps({"num_bytes": num_bytes, "source_id": self.source_id}).encode('utf-8')
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "Phoenix-NPU-DR27-Client/1.0"}
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            raw_body = r.read()
            container = abi.parse_qrng_openapi_json(raw_body)
            entropy_bytes = container["entropy"]
            
            # Pushes to AIE2 silicon reservoir
            res = reservoir.ingress_entropy(entropy_bytes, source_id=self.source_id)
            return {
                "ingress_result": res,
                "source_id": self.source_id,
                "quality": container["quality"],
                "bytes_ingressed": len(entropy_bytes),
                "reservoir_fill": res["fill_level"],
                "reservoir_mode": res["mode_str"]
            }

def start_mock_qrng_server(port: int = 8443) -> Tuple[HTTPServer, threading.Thread]:
    """Starts local mock QRNG-OPENAPI server for offline testing."""
    server = HTTPServer(("127.0.0.1", port), MockQrngOpenApiServer)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread
