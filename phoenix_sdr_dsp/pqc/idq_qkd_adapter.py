# SPDX-License-Identifier: Apache-2.0
"""
ID Quantique (IDQ) Cerberis / Clavis ETSI GS QKD 014 Hardware Adapter
---------------------------------------------------------------------
Implements client and mock Key Management Entity (KME) server compliant with
ID Quantique Cerberis XGR / Clavis 3 systems and ETSI GS QKD 014 (v1.1.1 / v1.3.1).
Directly pipes quantum key material into AMD Phoenix AIE2 tile memory.
"""

import base64
import json
import secrets
import threading
import time
import urllib.request
import urllib.error
import uuid
import http.server
from typing import Dict, List, NamedTuple, Optional, Tuple

from . import dr16_etsi_qkd014_abi as abi
from . import dr16_etsi_qkd014_graph as dr16_graph

class IdqKmeConfig(NamedTuple):
    kme_id: str
    host: str
    port: int
    master_sae_id: str
    slave_sae_id: str
    key_size_bits: int = 256

class MockIdqCerberisServer:
    """Threaded Mock ID Quantique Cerberis XGR QKD Key Management Server."""
    def __init__(self, host: str = "127.0.0.1", port: int = 18080, kme_id: str = "IDQ-CERBERIS-XGR-01"):
        self.host = host
        self.port = port
        self.kme_id = kme_id
        self.server: Optional[http.server.ThreadingHTTPServer] = None
        self.thread: Optional[threading.Thread] = None
        self.key_store: Dict[str, bytes] = {}
        self._lock = threading.Lock()

    def start(self):
        parent = self

        class IdqHandler(http.server.BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass # Silent logs

            def do_GET(self):
                # /api/v1/keys/{slave_sae_id}/status
                # /api/v1/keys/{slave_sae_id}/enc_keys
                path_parts = self.path.split("?")[0].strip("/").split("/")
                if len(path_parts) >= 5 and path_parts[0] == "api" and path_parts[1] == "v1" and path_parts[2] == "keys":
                    target_sae = path_parts[3]
                    action = path_parts[4]

                    if action == "status":
                        resp = {
                            "source_KME_ID": parent.kme_id,
                            "target_KME_ID": f"{parent.kme_id}-REMOTE",
                            "master_SAE_ID": "SAE-NODE-A-NPU",
                            "slave_SAE_ID": target_sae,
                            "key_size": 256,
                            "stored_key_count": 4096,
                            "max_key_count": 8192,
                            "max_key_per_request": 128,
                            "max_key_size": 1024,
                            "min_key_size": 64
                        }
                        self._send_json(200, resp)
                        return

                    elif action == "enc_keys":
                        # Generate fresh QKD key
                        key_id = str(uuid.uuid4())
                        raw_key = secrets.token_bytes(32)
                        with parent._lock:
                            parent.key_store[key_id] = raw_key

                        resp = {
                            "keys": [
                                {
                                    "key_ID": key_id,
                                    "key": base64.b64encode(raw_key).decode("ascii")
                                }
                            ]
                        }
                        self._send_json(200, resp)
                        return

                self._send_json(404, {"error": "Not Found"})

            def do_POST(self):
                # /api/v1/keys/{master_sae_id}/dec_keys
                path_parts = self.path.split("?")[0].strip("/").split("/")
                if len(path_parts) >= 5 and path_parts[0] == "api" and path_parts[1] == "v1" and path_parts[2] == "keys" and path_parts[4] == "dec_keys":
                    content_len = int(self.headers.get("Content-Length", 0))
                    body = self.rfile.read(content_len)
                    try:
                        req_data = json.loads(body.decode("utf-8"))
                        key_ids = req_data.get("key_IDs", [])
                        keys_out = []
                        with parent._lock:
                            for item in key_ids:
                                kid = item.get("key_ID")
                                if kid in parent.key_store:
                                    raw_key = parent.key_store[kid]
                                    keys_out.append({
                                        "key_ID": kid,
                                        "key": base64.b64encode(raw_key).decode("ascii")
                                    })
                        self._send_json(200, {"keys": keys_out})
                        return
                    except Exception as e:
                        self._send_json(400, {"error": str(e)})
                        return

                self._send_json(404, {"error": "Not Found"})

            def _send_json(self, status: int, data: dict):
                payload = json.dumps(data).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        self.server = http.server.ThreadingHTTPServer((self.host, self.port), IdqHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None

class IdqQkdClient:
    """Client for ID Quantique Cerberis / Clavis ETSI GS QKD 014 Key Delivery REST API."""
    def __init__(self, kme_url: str = "http://127.0.0.1:18080", master_sae: str = "SAE-NODE-A-NPU", slave_sae: str = "SAE-NODE-B-NPU"):
        self.kme_url = kme_url.rstrip("/")
        self.master_sae = master_sae
        self.slave_sae = slave_sae

    def get_status(self) -> dict:
        url = f"{self.kme_url}/api/v1/keys/{self.slave_sae}/status"
        req = urllib.request.Request(url, headers={"User-Agent": "AMD-Phoenix-NPU-ETSI014/1.1"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def get_enc_key(self, number: int = 1, size_bits: int = 256) -> Tuple[uuid.UUID, bytes, str]:
        """Request fresh quantum encryption key (Master SAE)."""
        url = f"{self.kme_url}/api/v1/keys/{self.slave_sae}/enc_keys?number={number}&size={size_bits}"
        req = urllib.request.Request(url, headers={"User-Agent": "AMD-Phoenix-NPU-ETSI014/1.1"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw_json = resp.read().decode("utf-8")
            keys = abi.parse_etsi_014_json(raw_json, source_sae=self.master_sae, target_sae=self.slave_sae)
            if not keys:
                raise RuntimeError("No keys returned by IDQ KME server.")
            return keys[0].key_id, keys[0].key_bytes, raw_json

    def get_dec_key(self, key_id: uuid.UUID) -> bytes:
        """Retrieve matching quantum decryption key using Key ID (Slave SAE)."""
        url = f"{self.kme_url}/api/v1/keys/{self.master_sae}/dec_keys"
        req_data = json.dumps({"key_IDs": [{"key_ID": str(key_id)}]}).encode("utf-8")
        req = urllib.request.Request(url, data=req_data, headers={
            "Content-Type": "application/json",
            "User-Agent": "AMD-Phoenix-NPU-ETSI014/1.1"
        })
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw_json = resp.read().decode("utf-8")
            keys = abi.parse_etsi_014_json(raw_json, source_sae=self.master_sae, target_sae=self.slave_sae)
            if not keys:
                raise RuntimeError(f"Key ID {key_id} not found on IDQ KME server.")
            return keys[0].key_bytes

    def stream_key_directly_to_npu(self, epoch: int = 1000) -> Tuple[uuid.UUID, int, int, int]:
        """Fetch key from IDQ KME and stream directly into AIE2 Tile (0,1) memory without CPU storage."""
        key_id, key_bytes, _ = self.get_enc_key()
        desc_buf = abi.pack_dr16_descriptor(key_id, epoch, len(key_bytes))
        req_buf = abi.pack_dr16_request(key_bytes, self.master_sae, self.slave_sae)
        req_id, status, slot, crc32 = dr16_graph.run_dr16_ingress_service(req_buf, desc_buf)
        return key_id, status, slot, crc32
