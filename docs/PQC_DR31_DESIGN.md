# DR31 Architecture & Design: On-Device X.509 Post-Quantum PKI & Certificate Engine on AMD Phoenix AIE2 Silicon

<div align="center">

![Standards: RFC 5280 / RFC 9618](https://img.shields.io/badge/Standards-RFC%205280%20%2F%20RFC%209618-005ea8)
![PKI: ML-DSA / SLH-DSA / LMS / Composite](https://img.shields.io/badge/PKI-ML--DSA%20%2F%20SLH--DSA%20%2F%20LMS%20%2F%20Composite-purple)
![Target: AMD Phoenix NPU (AIE2 / XDNA1)](https://img.shields.io/badge/Hardware-AMD%20Phoenix%20AIE2%20(512--bit%20SIMD)-red)
![Residency: 100% On-Device Silicon](https://img.shields.io/badge/Residency-100%25%20On--Device%20(Zero%20Host%20Fallback)-brightgreen)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22164124.svg)](https://doi.org/10.5281/zenodo.22164124)

</div>

---

## 1. Executive Summary & Enterprise PKI Threat Model

Milestone **DR31** implements an **On-Device X.509 Post-Quantum Public Key Infrastructure (PKI) Engine** on the AMD Phoenix NPU (AIE2 / XDNA1 Architecture).

In production secure networks (HTTPS, TLS 1.3, mTLS, code signing, secure boot attestation), cryptographic public keys and signatures do not operate in isolation—they are structured inside **ASN.1 DER-encoded X.509 v3 Certificates**.

### Host Parser Vulnerability Addressed:
If X.509 parsing and certificate path validation occur on the host CPU in software, adversaries can exploit complex ASN.1 parsing vulnerabilities (length confusion, buffer overflows, integer wraparounds, recursion depth attacks). 

**DR31 Solution:**
1. **Bounded-Memory AIE2 DER Parser**: Performs deterministic zero-allocation parsing of X.509 v3 certificate trees directly in AIE2 local SRAM.
2. **On-Silicon Path Validation (RFC 5280 Section 6)**: Validates validity dates, basic constraints (`isCA`), key usages, and subject/issuer name matches on hardware.
3. **Multi-Tier Quantum-Resilient Signatures**: Verifies Root CA $\to$ Intermediate CA $\to$ Leaf Certificate signature chains directly on AIE2 vector tiles (using DR11-DR15 ML-DSA, DR21 SLH-DSA, and DR28 LMS).

---

## 2. ASN.1 DER Architecture & Object Identifier (OID) Tables

### 2.1 Post-Quantum & Composite OID Mapping
In compliance with IETF RFC 5280, RFC 9618, and NIST standards:

| Algorithm / Structure | OID Dotted String | ASN.1 AlgorithmIdentifier | Hardware Verifier Gate |
| :--- | :--- | :--- | :---: |
| **ML-DSA-44** | `2.16.840.1.101.3.4.3.17` | `id-ml-dsa-44` | Gate 16 (DR13) |
| **ML-DSA-65** | `2.16.840.1.101.3.4.3.18` | `id-ml-dsa-65` | Gate 17 (DR14) |
| **ML-DSA-87** | `2.16.840.1.101.3.4.3.19` | `id-ml-dsa-87` | Gate 18 (DR15) |
| **SLH-DSA-SHAKE-128s**| `2.16.840.1.101.3.4.3.22` | `id-slh-dsa-shake-128s` | Gate 25 (DR21) |
| **LMS / HSS** | `1.2.840.113549.1.9.16.3.17`| `id-alg-hss-lms-hashsig` | Gate 26 (DR28) |
| **Composite ML-DSA+ECDSA**| `1.3.6.1.4.1.18227.2.1` | `id-composite-mldsa44-p256` | Dual AIE2 Core |

### 2.2 X.509 v3 Certificate Binary Layout (RFC 5280)
```
Certificate  ::=  SEQUENCE  {
     tbsCertificate       TBSCertificate,
     signatureAlgorithm   AlgorithmIdentifier,
     signatureValue       BIT STRING  
}

TBSCertificate  ::=  SEQUENCE  {
     version         [0]  EXPLICIT Version DEFAULT v1,
     serialNumber         CertificateSerialNumber,
     signature            AlgorithmIdentifier,
     issuer               Name,
     validity             Validity,
     subject              Name,
     subjectPublicKeyInfo SubjectPublicKeyInfo,
     extensions      [3]  EXPLICIT Extensions OPTIONAL
}
```

---

## 3. Microarchitectural Tile Mapping on AMD Phoenix AIE2

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                 XRT OBJECTFIFO INGRESS INTERFACE                                 │
│         ObjectFIFOs: dr31_cert_chain_in, dr31_trust_anchor_in, dr31_validation_out               │
└────────────────────────────────────────────┬─────────────────────────────────────────────────────┘
                                             │ Zero-Copy DMA
═════════════════════════════════════════════╪═════════════════════════════════════════════════════
                                             │ PHYSICAL AIE2 TILE ARRAY
┌────────────────────────────────────────────▼─────────────────────────────────────────────────────┐
│  TILE (3,2): Bounded-Memory ASN.1 DER Parser & Digest Core                                      │
│   • Parses TBSCertificate boundaries and computes SHA3-256 / SHAKE / SHA-256 hash digest        │
│   • Extracts SubjectPublicKeyInfo (SPKI) and raw public key bytes                                │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│  TILE (3,1): RFC 5280 Certificate Extension & Policy Validator                                   │
│   • Checks BasicConstraints (isCA == True for issuing certificates, pathLenConstraint)          │
│   • Checks KeyUsage (keyCertSign, digitalSignature, crlSign)                                     │
│   • Checks Validity timestamps (notBefore <= currentTime <= notAfter)                            │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│  TILE (3,0): Multi-Tier Signature Verification Pipeline (Chain Validator)                        │
│   • Validates Leaf Signature using Intermediate CA SPKI                                          │
│   • Validates Intermediate Signature using Root CA SPKI                                          │
│   • Validates Root CA Self-Signature or Trust Anchor Binding                                     │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│  TILE (3,3): Execution Lock Gate & DR10 Zeroizer                                                 │
│   • If Entire Chain Valid: Output VERIFIED_AUTHENTIC (0x00000000) -> Unlock Connection           │
│   • If Any Node Invalid / Expired: Hard-fault REJECT_UNTRUSTED (0x00000001) & Zeroize            │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. References & Standards Citations

1. **IETF RFC 5280 (May 2008):** *Internet X.509 Public Key Infrastructure Certificate and Certificate Revocation List (CRL) Profile*.
2. **IETF RFC 9618 (2024):** *Composite Signatures for use in Internet PKI*.
3. **NIST FIPS PUB 204 (August 2024):** *Module-Lattice-Based Digital Signature Standard (ML-DSA)*.
4. **NIST FIPS PUB 205 (August 2024):** *Stateless Hash-Based Digital Signature Standard (SLH-DSA)*.
5. **Project Provenance & Scientific Repository:** [DOI: 10.5281/zenodo.22164124](https://doi.org/10.5281/zenodo.22164124).
