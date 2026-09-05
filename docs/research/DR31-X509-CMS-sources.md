# DR31 Research and Citation Provenance: X.509 Post-Quantum Certificates & Hybrid CMS Co-Processor

## Milestone Deliverable Context
- Deliverable: **DR31 (NIST SP 800-208 / RFC 5280 / RFC 5652 X.509 Post-Quantum Certificates & Hybrid CMS Co-Processor)**
- Target: AMD Phoenix NPU (AIE2 / XDNA1 Architecture)
- Standards: RFC 5280, RFC 5652, NIST SP 800-208, RFC 9688 / IETF LAMPS Post-Quantum PKI Profiles

## Citation Ledger

### Citation 1: RFC 5280: Internet X.509 Public Key Infrastructure Certificate and CRL Profile
- Source Title: Internet X.509 Public Key Infrastructure Certificate and Certificate Revocation List (CRL) Profile
- Authors: D. Cooper, S. Santesson, S. Farrell, S. Boeyen, R. Housley, W. Polk
- Issuing Organization: Internet Engineering Task Force (IETF), PKIX Working Group
- Standard Identifier: RFC 5280 (May 2008)
- URL: https://datatracker.ietf.org/doc/html/rfc5280
- Relevant Sections: Section 4.1 (Basic Certificate Fields), Section 4.1.1.2 (signatureAlgorithm), Section 4.1.1.3 (signatureValue), Section 4.1.2 (TBSCertificate)
- Exact Technical Principles:
  - An X.509 v3 certificate consists of three major ASN.1 fields: `tbsCertificate`, `signatureAlgorithm` (AlgorithmIdentifier), and `signatureValue` (BIT STRING).
  - Verification requires digesting the DER-encoded `tbsCertificate` sequence under the algorithm specified in `signatureAlgorithm` and verifying `signatureValue` using the issuer's public key from `subjectPublicKeyInfo`.
  - Separation of concerns: Recursive variable-length ASN.1 TLV parsing must be isolated from cryptographic verification. The host parses DER structures and marshals canonical TBS digests, public keys, and signature bytes to accelerator hardware.
- Implementation Impact: Defined strict execution boundary separating host ASN.1 DER extraction from AIE2 tile-resident signature verification and key authentication.

### Citation 2: RFC 5652: Cryptographic Message Syntax (CMS)
- Source Title: Cryptographic Message Syntax (CMS)
- Author: R. Housley
- Issuing Organization: Internet Engineering Task Force (IETF)
- Standard Identifier: RFC 5652 (September 2009)
- URL: https://datatracker.ietf.org/doc/html/rfc5652
- Relevant Sections: Section 5 (Signed-data Content Type), Section 6 (Enveloped-data Content Type)
- Exact Technical Principles:
  - `SignedData` verification: Validates `SignerInfo` signatures over `signedAttrs` (including `messageDigest` and `contentType`), authenticating the encapsulated content.
  - `EnvelopedData` decryption: Processes `RecipientInfo` to recover the Content Encryption Key (CEK). Under post-quantum KEM profiles (RFC 9688 / KEMRecipientInfo), recipient decapsulates the shared secret and unwraps the symmetric CEK.
- Implementation Impact: Implemented hardware modes for atomic CMS `SignedData` signature verification and `EnvelopedData` KEM decapsulation + key unwrapping on AIE2 vector tiles.

### Citation 3: NIST SP 800-208 & RFC 9688: Stateful Hash Signatures and Post-Quantum PKI Profiles
- Source Title: Recommendation for Stateful Hash-Based Signature Schemes (SP 800-208) / Use of ML-DSA and ML-KEM in X.509 and CMS
- Issuing Organization: National Institute of Standards and Technology (NIST) / IETF LAMPS WG
- Standard Identifier: NIST SP 800-208 (October 2020) / RFC 9688 (2024)
- URLs:
  - https://csrc.nist.gov/pubs/sp/800/208/final
  - https://datatracker.ietf.org/doc/draft-ietf-lamps-dilithium-certificates/
- Relevant Sections: Algorithm Object Identifiers (OIDs) for ML-DSA (2.16.840.1.101.3.4.3.17/18/19), ML-KEM (2.16.840.1.101.3.4.4.1/2/3), SLH-DSA (2.16.840.1.101.3.4.3.20), LMS (1.3.6.1.4.1.2.267.1.*).
- Exact Technical Principles:
  - Post-quantum public keys and signatures inside `SubjectPublicKeyInfo` and `SignatureValue` are stored as raw octet strings inside the ASN.1 wrappers.
  - Composite and hybrid certificates (ITU-T X.509 v3 / draft-ietf-lamps-cert-binding-for-multi-auth): Require dual signature verification (classical e.g. Ed25519/ECDSA AND post-quantum ML-DSA). The certificate is valid if and only if both signatures verify.
- Implementation Impact: Designed the DR31 co-processor with dual-algorithm verification modes supporting ML-DSA, SLH-DSA, LMS, and hybrid classical+PQC certificate validation.
