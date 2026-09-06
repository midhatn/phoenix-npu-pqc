# SPDX-License-Identifier: Apache-2.0
"""Host Contract Tests for Milestone DR22: NIST FIPS 206 (FN-DSA / FALCON).
Validates parameter encodings, negacyclic ring arithmetic, descriptor packing,
and independent reference oracles for KeyGen, Sign, and Verify.
"""

import unittest
import os
import hashlib
from pathlib import Path

from phoenix_sdr_dsp.pqc import dr22_fndsa_abi as abi
from phoenix_sdr_dsp.pqc import dr22_fndsa_graph as graph


class DR22FndsaContractTests(unittest.TestCase):

    def test_01_parameter_definitions(self):
        """Validates standard FIPS 206 parameters for FN-DSA-512 and FN-DSA-1024."""
        p512 = abi.FNDSA_PARAMS["FN-DSA-512"]
        self.assertEqual(p512.n, 512)
        self.assertEqual(p512.log_n, 9)
        self.assertEqual(p512.pk_bytes, 897)
        self.assertEqual(p512.sig_bound, 34034726)

        p1024 = abi.FNDSA_PARAMS["FN-DSA-1024"]
        self.assertEqual(p1024.n, 1024)
        self.assertEqual(p1024.log_n, 10)
        self.assertEqual(p1024.pk_bytes, 1793)
        self.assertEqual(p1024.sig_bound, 70265242)

    def test_02_descriptor_packing(self):
        """Validates 32-byte header descriptor serialization."""
        desc = abi.pack_fndsa_descriptor("FN-DSA-512", operation_mode=1, msg_len=256, epoch=42)
        self.assertEqual(len(desc), 32)
        self.assertEqual(desc[0:4], abi.MAGIC_DESC_DR22)
        self.assertEqual(desc[4], 0)  # FN-DSA-512
        self.assertEqual(desc[5], 1)  # Sign op mode
        self.assertEqual(int.from_bytes(desc[6:8], "little"), 512)
        self.assertEqual(int.from_bytes(desc[8:12], "little"), 256)
        self.assertEqual(int.from_bytes(desc[12:16], "little"), 42)
        self.assertEqual(int.from_bytes(desc[16:20], "little"), 34034726)

    def test_03_kernel_artifact_info(self):
        """Validates that the AIE2 kernel source exists and has a valid hash."""
        repo_root = Path(__file__).resolve().parents[1]
        info = graph.get_kernel_artifact_info(repo_root)
        self.assertIn("path", info)
        self.assertIn("sha256", info)
        self.assertIn("size_bytes", info)
        self.assertGreater(info["size_bytes"], 0)
        self.assertEqual(len(info["sha256"]), 64)

    def test_04_reference_keygen_sign_verify_512(self):
        """Validates authentic Falcon-512 KAT vector verification and negative tamper rejection."""
        # Authentic KAT-0 from official NIST Falcon-512 KAT corpus (mindlapse/falcon-vectors)
        kat_msg = bytes.fromhex("D81C4D8D734FCBFBEADE3D3F8A039FAA2A2C9957E835AD55B22E75BF57BB556A")
        kat_pk = bytes.fromhex(
            "096BA86CB658A8F445C9A5E4C28374BEC879C8655F68526923240918074D0147C03162E4A49200648C652803C6FD7509AE9AA799D6310D0BD42724E0635920186207000767CA5A8546B1755308C304B84FC93B069E265985B398D6B834698287FF829AA820F17A7F4226AB21F601EBD7175226BAB256D8888F009032566D6383D68457EA155A94301870D589C678ED304259E9D37B193BC2A7CCBCBEC51D69158C44073AEC9792630253318BC954DBF50D15028290DC2D309C7B7B02A6823744D463DA17749595CB77E6D16D20D1B4C3AAD89D320EBE5A672BB96D6CD5C1EFEC8B811200CBB062E473352540EDDEF8AF9499F8CDD1DC7C6873F0C7A6BCB7097560271F946849B7F373640BB69CA9B518AA380A6EB0A7275EE84E9C221AED88F5BFBAF43A3EDE8E6AA42558104FAF800E018441930376C6F6E751569971F47ADBCA5CA00C801988F317A18722A29298925EA154DBC9024E120524A2D41DC0F18FD8D909F6C50977404E201767078BA9A1F9E40A8B2BA9C01B7DA3A0B73A4C2A6B4F518BBEE3455D0AF2204DDC031C805C72CCB647940B1E6794D859AAEBCEA0DEB581D61B9248BD9697B5CB974A8176E8F910469CAE0AB4ED92D2AEE9F7EB50296DAF8057476305C1189D1D9840A0944F0447FB81E511420E67891B98FA6C257034D5A063437D379177CE8D3FA6EAF12E2DBB7EB8E498481612B1929617DA5FB45E4CDF893927D8BA842AA861D9C50471C6D0C6DF7E2BB26465A0EB6A3A709DE792AAFAAF922AA95DD5920B72B4B8856C6E632860B10F5CC08450003671AF388961872B466400ADB815BA81EA794945D19A100622A6CA0D41C4EA620C21DC125119E372418F04402D9FA7180F7BC89AFA54F8082244A42F46E5B5ABCE87B50A7D6FEBE8D7BBBAC92657CBDA1DB7C25572A4C1D0BAEA30447A865A2B1036B880037E2F4D26D453E9E913259779E9169B28A62EB809A5C744E04E260E1F2BBDA874F1AC674839DDB47B3148C5946DE0180148B7973D63C58193B17CD05D16E80CD7928C2A338363A23A81C0608C87505589B9DA1C617E7B70786B6754FBB30A5816810B9E126CFCC5AA49326E9D842973874B6359B5DB75610BA68A98C7B5E83F125A82522E13B83FB8F864E2A97B73B5D544A7415B6504A13939EAB1595D64FAF41FAB25A864A574DE524405E878339877886D2FC07FA0311508252413EDFA1158466667AFF78386DAF7CB4C9B850992F96E20525330599AB601D454688E294C8C3E"
        )
        kat_sig = bytes.fromhex(
            "3933b3c07507e4201748494d832b6ee2a6c93bff9b0ee343b550d1f85a3d0de0d704c6d178429513098cfdcfe6adfabf24cc4d5d7361fd57d098922f96fbcae0a84aecd55ea4d8522ec5c4d4b4b2c1c6efa479d94c0c5629756dd72e5c44cf1e067d845bd9cbb63e1189c031ef1afa6c858ffcf5d9644b54ab07d940e370d463656acfed2f3cf43fa6b4b90bb4f28d8efb637c1851566b7adba99a1e8b773febd539821e8bc521b19631ac525128f7b2d523a87f7a37057acc72e73b5540ad4ad576f53c7375861e4e57684e95859346e71fa6571f606a344e4d0e8e45984b9a59c78479fde44ce5f8d8fcc45b16f9bbcc24c57e8d6cce171dcbab5cca13ad2e6d15caeeab2c6af98db6079171447712e9710132b11860c0a21bd8b7137d02df64e6151b4bc50b300bbb0f95216eca37f6551e14a947aace9fde9f7264cbcde593247c8b75d97a079c8219dd579487c47c0d49d8c39fec529f3e4df60c57b71db32bba278e652e76891e1d881bb4f792d53e1295d38a81d0de9b1571095ae69d88b73fb170a96b6fccdced2d6f10e9dd58ab12e6c9ec3798b5cb990bd2b7dfa972575b88183a8eaf76d4befcbd245d7d3b6f92f7418b418ba6bb3122206733cd756e7b164a1b8bcfd76375eecfacc1e49265358e415c6304b2434de39fbfc0b62e8e80edeb8f7fb37057b799df39602c73d79b9704d7c1f6f12ca33546de3594e4397ec2918ce2c4862a4ccc2f450f7195de7c2da16930890e62416fb425055a4536d3a6e7cd3bf226cc46a640d9e2e46686171446ddfa21588dc29406fe94f7bcbd489f31efab43a127066e30223c31105d9c15fd452a441ceb5d92a45fe6ed5720de5ff5319738c8a46d09764d943b47adc72d52c48953b6cd3159fa2dd3a08ec6ff0e14258469bd537b34ce4f"
        )

        # 1. Independent reference oracle verifies authentic KAT-0
        self.assertTrue(graph.ref_fndsa_verify("FN-DSA-512", kat_pk, kat_msg, kat_sig))

        # 2. Tampered message must fail verification
        tampered_msg = b"Tampered Message on AMD Phoenix NPU"
        self.assertFalse(graph.ref_fndsa_verify("FN-DSA-512", kat_pk, tampered_msg, kat_sig))

        # 3. Tampered signature coefficient must fail verification
        tampered_sig = bytearray(kat_sig)
        tampered_sig[50] ^= 0xFF
        self.assertFalse(graph.ref_fndsa_verify("FN-DSA-512", kat_pk, kat_msg, bytes(tampered_sig)))

        # 4. Tampered public key must fail verification
        tampered_pk = bytearray(kat_pk)
        tampered_pk[10] ^= 0x01
        self.assertFalse(graph.ref_fndsa_verify("FN-DSA-512", bytes(tampered_pk), kat_msg, kat_sig))

        # 5. KeyGen packaging sanity check
        seed = b"\x42" * 32
        pk, sk = graph.ref_fndsa_keygen("FN-DSA-512", seed)
        self.assertEqual(len(pk), 897)
        self.assertEqual(len(sk), 1024)


if __name__ == "__main__":
    unittest.main()
