# AcuCalyx™ Core Postmarket Cybersecurity, CVD & Patch Management SOP
## Lifecycle Vulnerability Management & Secure Update Procedures per FD&C Act §524B(b)(3)

**Document Identifier:** SOP-ACU-CYBER-PMS-2026A  
**Regulatory Baseline:** FD&C Act §524B(b)(3) & FDA Postmarket Cybersecurity Guidance  
**Target Milestone:** Milestone M8 (Commercial Operations)  

---

## 1. Statutory Scope & Section 524B Compliance

Under Section 524B of the Federal Food, Drug, and Cosmetic Act (FD&C Act), sponsors of cyber devices must maintain processes to monitor, identify, and address postmarket cybersecurity vulnerabilities and exploits, provide postmarket software updates and patches, and maintain a Coordinated Vulnerability Disclosure (CVD) policy.

---

## 2. Coordinated Vulnerability Disclosure (CVD) Operations

AcuCalyx operates a formal CVD program to facilitate external security researcher engagement:
- **Designated Security Mailbox:** `security@acucalyx.com`
- **PGP Encryption Key:** Published and maintained on the manufacturer's security trust center.
- **Operational Response SLAs:**
  - *Receipt Acknowledgment:* Within **48 hours** of report receipt.
  - *Initial Triage & Impact Assessment:* Within **7 calendar days**.
  - *Remediation Timeline & Coordination:* Within **30 calendar days**.

---

## 3. Vulnerability Monitoring & Remediation SLAs

### 3.1 Continuous Monitoring Architecture
The security operations pipeline executes scheduled daily scans:
1. **CISA Known Exploited Vulnerabilities (KEV) Catalog:** Automated matching against active SOUP components.
2. **National Vulnerability Database (NVD):** CVSS v3.1 tracking for Python, NumPy, PyTorch, and SimpleITK.

### 3.2 Risk-Based Remediation Target SLAs
> [!NOTE]
> **Internal Risk-Based SLA Targets:**  
> In alignment with FDA postmarket cybersecurity recommendations, the manufacturer establishes internal operational target timelines for patch development and deployment based on CVSS severity and clinical risk:
> - **Critical / Actively Exploited (CVSS 9.0–10.0 or KEV):** Target expedited release within **30 calendar days**.
> - **High Severity (CVSS 7.0–8.9):** Target release within **60 calendar days**.
> - **Medium / Low Severity:** Evaluated and bundled into scheduled quarterly maintenance updates.

---

## 4. Cryptographic Patch Verification & Rollback Protection

To prevent malicious software tampering and enforce anti-downgrade protection, all commercial software patches (`.acupkg`) must satisfy three cryptographic checks before installation:

```
┌────────────────────────────────────────────────────────────────────────┐
│               CRYPTOGRAPHIC PATCH VERIFICATION PIPELINE                │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│   UPDATE ARCHIVE (.acupkg) RECEIVED BY HOSPITAL WORKSTATION            │
│     │                                                                  │
│     ├── STEP 1: Asymmetric Digital Signature Verification             │
│     │     • Verified against manufacturer's embedded public key        │
│     │       (RSA-4096 / ECDSA P-384).                                  │
│     │     • Fails if signature is invalid or key untrusted.            │
│     │                                                                  │
│     ├── STEP 2: SHA-256 Cryptographic Digest Verification              │
│     │     • Package digest computed and matched against manifest.      │
│     │     • Fails if archive is truncated or tampered.                 │
│     │                                                                  │
│     └── STEP 3: Version Monotonicity Guard (Anti-Downgrade)            │
│           • Package semantic version compared against installed build. │
│           • Rejects attempts to install older software versions        │
│             with known vulnerabilities.                                │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```
