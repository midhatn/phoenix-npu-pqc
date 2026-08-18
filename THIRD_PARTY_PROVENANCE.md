# Third-party provenance manifest

This manifest binds redistributed derivative source and test-vector material
to local SHA-256 identities and immutable upstream records. It supplements
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md); file-level notices and SPDX
identifiers remain authoritative.

## Confidence labels

- **Verified extraction** means parsed local JSON was proven to be a subset or
  formatting-only transformation of data at the identified upstream commit.
- **Comparison anchor** means the immutable upstream revision is suitable for
  reviewing the declared lineage, but repository history does not prove it was
  the historical source used to create the local file.

No comparison anchor is represented as an exact derivation revision.

## Upstream anchors

| ID | Upstream and immutable revision | License / notice | Confidence |
| --- | --- | --- | --- |
| `KYBER-REF` | pq-crystals/kyber commit [`3edd5af5991927164edd4aacebfcbee00b8064e7`](https://github.com/pq-crystals/kyber/commit/3edd5af5991927164edd4aacebfcbee00b8064e7), reference tree [`ref/`](https://github.com/pq-crystals/kyber/tree/3edd5af5991927164edd4aacebfcbee00b8064e7/ref), and [`LICENSE`](https://github.com/pq-crystals/kyber/blob/3edd5af5991927164edd4aacebfcbee00b8064e7/LICENSE). | Upstream offers CC0 or Apache-2.0 and identifies separately attributed public-domain Keccak/AES code. Local file-level licenses are retained; this manifest does not relicense a file. | Comparison anchor only. Exact historical derivation revision is unproven. |
| `DILITHIUM-REF` | pq-crystals/dilithium commit [`d35ba3fe5449bee3e6d43e1f296c3ca818bd36be`](https://github.com/pq-crystals/dilithium/commit/d35ba3fe5449bee3e6d43e1f296c3ca818bd36be), reference tree [`ref/`](https://github.com/pq-crystals/dilithium/tree/d35ba3fe5449bee3e6d43e1f296c3ca818bd36be/ref), and [`LICENSE`](https://github.com/pq-crystals/dilithium/blob/d35ba3fe5449bee3e6d43e1f296c3ca818bd36be/LICENSE). | Upstream offers CC0, Apache-2.0, or GPL-2.0 and identifies separately attributed public-domain Keccak/random code. Local file-level licenses are retained; this manifest does not relicense a file. | Comparison anchor only. Exact historical derivation revision is unproven. |
| `NIST-ACVP-975DE31` | usnistgov/ACVP-Server commit [`975de31eb83d87039ec88934fdc47d8c312b892d`](https://github.com/usnistgov/ACVP-Server/commit/975de31eb83d87039ec88934fdc47d8c312b892d), generated-vector tree [`gen-val/json-files`](https://github.com/usnistgov/ACVP-Server/tree/975de31eb83d87039ec88934fdc47d8c312b892d/gen-val/json-files), and repository [`README.md`](https://github.com/usnistgov/ACVP-Server/blob/975de31eb83d87039ec88934fdc47d8c312b892d/README.md#license). | Retain [`LICENSES/NIST-ACVP-NOTICE.txt`](LICENSES/NIST-ACVP-NOTICE.txt), identify modifications with date and nature, and acknowledge NIST as the source. | Verified extraction for the ten vectors below. |

## Local derivative-source inventory

Hashes identify the redistributed local bytes. These are project-specific
adaptations, tests, or comparison tools, not asserted upstream byte copies.

| Local path | SHA-256 | Anchor |
| --- | --- | --- |
| `tests/m32_mlkem/kpke_kernel.cc` | `f79700a0c1d9699c1cb71a1e745933c044c2d10f285be5c91d1cc36b07645405` | `KYBER-REF`; explicit local MIT SPDX exception retained. |
| `tests/m32_mlkem/ntt_kernel.cc` | `c882320d5cecd4a482c30b95864f3f08117723e17bbb5d0afef8fd4a8a107ad7` | `KYBER-REF` |
| `tests/m32_mlkem/mlkem_composer.py` | `c465c1f3c42168dabb1a10e6e78c8728c74923843dab41359ea7266573eb6dee` | `KYBER-REF` |
| `tests/m32_mlkem/test_ntt_m32b.py` | `b34eb228b14acb6506dac4dd4e345c935eb84c8ea3e8d578c3fd963d35646531` | `KYBER-REF` |
| `tests/m32_mlkem/test_kpke_m32d.py` | `757cad7572afb5559434fdd5c71bc9de4886cb2f42067ce41a5ac04a3c363f17` | `KYBER-REF` |
| `tools/m32b_kernel_transliteration_check.py` | `61406b51df6a08cfa6c7c5b53ee1dc917eac72318913067f195529193ab581eb` | `KYBER-REF` |
| `tools/m32d_kernel_transliteration_check.py` | `728d049b519c9d1929bb8a1e007db00b864e6a6174fdde0858911b43e792c0a1` | `KYBER-REF` |
| `tools/m32e_kernel_transliteration_check.py` | `7ea112d42c3d841d121713def3fc6923a7d6f954e75a154bad365af7be5f3120` | `KYBER-REF` |
| `tests/m33_mldsa/dilithium_ntt_kernel.cc` | `1f2005bd0f10b94005a155c12ac7d29822299a3edb85afd6f3cfcc8831da06ec` | `DILITHIUM-REF` |
| `tests/m33_mldsa/dilithium_sampler_kernel.cc` | `99ec00d9ca92d9d798e6b78acc880f4e637d34b2562896d44c922a2e39174a57` | `DILITHIUM-REF` |
| `tests/m33_mldsa/mldsa_composer.py` | `1991255534ff87cbe0b2cfe0ee1bd6691df158948d5e6ecab10efef1adeeb0c7` | `DILITHIUM-REF` |
| `tests/m33_mldsa/test_dilithium_ntt_m33a.py` | `09a6d8d75cb53114b6d2808cbea1deca68dca281805019664a11fdda4ccaab51` | `DILITHIUM-REF` |
| `tests/m33_mldsa/test_dilithium_sampler_m33b.py` | `3aef8004e222570ff1b2d4d6ce18e124e61cbe7de02e8a019a23c6b5d55a0473` | `DILITHIUM-REF` |
| `tools/m33a_kernel_transliteration_check.py` | `f145bfa25a1fdf6db2c5e5e11531ed805bcc1b994b503517b26bf8617876a81f` | `DILITHIUM-REF` |
| `tools/m33b_kernel_transliteration_check.py` | `4a1b1c37aeeb4da050000efe61f30f94d2fa99d9a900b9ae6c14574d6722132d` | `DILITHIUM-REF` |
| `phoenix_sdr_dsp/pqc/kernels/m33a_arithmetic.hpp` | `c490a3249d01a59de62e007261b5a4c6088d3a98c3979b165c6e0bc5fc7eb935` | `DILITHIUM-REF` |

## NIST ACVP vector inventory

Verification on 2026-08-18 parsed local and upstream JSON. The four ML-KEM
files select ML-KEM-512 groups from larger upstream files and use compact
formatting. The six ML-DSA files preserve the complete upstream bytes. No
vector bytes or protected evidence were changed when this manifest was added.

| Local path | Local SHA-256 | Immutable upstream file | Upstream SHA-256 | Relationship |
| --- | --- | --- | --- | --- |
| `tests/m32_mlkem/vectors/keygen_prompt.json` | `62931c48765a8afca042795d73d52ad963cec715dadbcb008d24984120947512` | [`ML-KEM-keyGen-FIPS203/prompt.json`](https://github.com/usnistgov/ACVP-Server/blob/975de31eb83d87039ec88934fdc47d8c312b892d/gen-val/json-files/ML-KEM-keyGen-FIPS203/prompt.json) | `3f9ce34f6c836c77958bad2729e837c3b213f44ac36c3065976e7acca6389523` | ML-KEM-512 extraction; compacted. |
| `tests/m32_mlkem/vectors/keygen_expected.json` | `e14ee666b21302f75bae27da6e941ca5c11c842f60f5910291baabced0320d19` | [`ML-KEM-keyGen-FIPS203/expectedResults.json`](https://github.com/usnistgov/ACVP-Server/blob/975de31eb83d87039ec88934fdc47d8c312b892d/gen-val/json-files/ML-KEM-keyGen-FIPS203/expectedResults.json) | `a253d0ad91c95ebea5b409673defef0aa49d65d4ed72286399e2e798ddf073a4` | ML-KEM-512 extraction; compacted. |
| `tests/m32_mlkem/vectors/encapdecap_prompt.json` | `9909fe1c488e421100097ae67c53ff20e98e3028e4b1a45368f5a635d12af821` | [`ML-KEM-encapDecap-FIPS203/prompt.json`](https://github.com/usnistgov/ACVP-Server/blob/975de31eb83d87039ec88934fdc47d8c312b892d/gen-val/json-files/ML-KEM-encapDecap-FIPS203/prompt.json) | `998e22dfb12efb14ce9fdff911ca634b13612819a1806f25da69adba7e16db91` | ML-KEM-512 extraction; compacted. |
| `tests/m32_mlkem/vectors/encapdecap_expected.json` | `351d0c5c6d12ddc915c7b215b69960cec16b105764dfaae101c82c86da707632` | [`ML-KEM-encapDecap-FIPS203/expectedResults.json`](https://github.com/usnistgov/ACVP-Server/blob/975de31eb83d87039ec88934fdc47d8c312b892d/gen-val/json-files/ML-KEM-encapDecap-FIPS203/expectedResults.json) | `9089ec6ff2424da9f2782b89b2f831a329a3e28d6e5e24b802b78ff36ac61cdf` | ML-KEM-512 extraction; compacted. |
| `tests/m33_mldsa/vectors/ML-DSA-keyGen-FIPS204_prompt.json` | `43e81ad820e495dbcad086fe27c1008393a8c32100bbbff77c558c3f06dcefef` | [`ML-DSA-keyGen-FIPS204/prompt.json`](https://github.com/usnistgov/ACVP-Server/blob/975de31eb83d87039ec88934fdc47d8c312b892d/gen-val/json-files/ML-DSA-keyGen-FIPS204/prompt.json) | `43e81ad820e495dbcad086fe27c1008393a8c32100bbbff77c558c3f06dcefef` | Parsed data and bytes identical. |
| `tests/m33_mldsa/vectors/ML-DSA-keyGen-FIPS204_expectedResults.json` | `361f47ca19d592adcc66ff2cb591686ad785fea157b295648738bed6921a68df` | [`ML-DSA-keyGen-FIPS204/expectedResults.json`](https://github.com/usnistgov/ACVP-Server/blob/975de31eb83d87039ec88934fdc47d8c312b892d/gen-val/json-files/ML-DSA-keyGen-FIPS204/expectedResults.json) | `361f47ca19d592adcc66ff2cb591686ad785fea157b295648738bed6921a68df` | Parsed data and bytes identical. |
| `tests/m33_mldsa/vectors/ML-DSA-sigGen-FIPS204_prompt.json` | `447749d72817b211160d243311ce32302f3023e59c355b0f70be2bd3e9e7830d` | [`ML-DSA-sigGen-FIPS204/prompt.json`](https://github.com/usnistgov/ACVP-Server/blob/975de31eb83d87039ec88934fdc47d8c312b892d/gen-val/json-files/ML-DSA-sigGen-FIPS204/prompt.json) | `447749d72817b211160d243311ce32302f3023e59c355b0f70be2bd3e9e7830d` | Parsed data and bytes identical. |
| `tests/m33_mldsa/vectors/ML-DSA-sigGen-FIPS204_expectedResults.json` | `228d011bbe274aeb93e22eea1e0d57b78f43795cf6a64fb5ef1e626485a0bedb` | [`ML-DSA-sigGen-FIPS204/expectedResults.json`](https://github.com/usnistgov/ACVP-Server/blob/975de31eb83d87039ec88934fdc47d8c312b892d/gen-val/json-files/ML-DSA-sigGen-FIPS204/expectedResults.json) | `228d011bbe274aeb93e22eea1e0d57b78f43795cf6a64fb5ef1e626485a0bedb` | Parsed data and bytes identical. |
| `tests/m33_mldsa/vectors/ML-DSA-sigVer-FIPS204_prompt.json` | `e2cba4589389756fa0bea1a7e6837138bf0a81f9d14234c9ee8f6d33caa1654e` | [`ML-DSA-sigVer-FIPS204/prompt.json`](https://github.com/usnistgov/ACVP-Server/blob/975de31eb83d87039ec88934fdc47d8c312b892d/gen-val/json-files/ML-DSA-sigVer-FIPS204/prompt.json) | `e2cba4589389756fa0bea1a7e6837138bf0a81f9d14234c9ee8f6d33caa1654e` | Parsed data and bytes identical. |
| `tests/m33_mldsa/vectors/ML-DSA-sigVer-FIPS204_expectedResults.json` | `e1d84ef1b2f35196278ab0b0ed6a46ec62cc03d2dfa92c564199e1999bfb8ea6` | [`ML-DSA-sigVer-FIPS204/expectedResults.json`](https://github.com/usnistgov/ACVP-Server/blob/975de31eb83d87039ec88934fdc47d8c312b892d/gen-val/json-files/ML-DSA-sigVer-FIPS204/expectedResults.json) | `e1d84ef1b2f35196278ab0b0ed6a46ec62cc03d2dfa92c564199e1999bfb8ea6` | Parsed data and bytes identical. |

## NIST modification notice

The four ML-KEM files were extracted from the complete ACVP files on
2026-08-16 by retaining the ML-KEM-512 test groups and serializing compact
JSON. The six ML-DSA files were imported without changing their parsed data.
Phoenix NPU PQC acknowledges the National Institute of Standards and
Technology as the source. The complete upstream notice is retained at
[`LICENSES/NIST-ACVP-NOTICE.txt`](LICENSES/NIST-ACVP-NOTICE.txt).

## Maintenance

Any change to a listed local file must update its SHA-256 here in the same
commit. An upstream-anchor change must preserve the prior record in Git history
and state whether exactness was reverified. The checksum-protected
`docs/pqc_dr2_evidence_20260818/` tree must not be rewritten to normalize
provenance metadata.
