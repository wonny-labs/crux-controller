# Controller framework threat model

This page lists the assets, interfaces and threats of the [controller framework](controller-framework.md) and its base image, and says which points of Annex I of the EU Cyber Resilience Act apply, with the reason.
It serves requirements T1 and M1 of the [specification](controller-framework-spec.md#2-requirements), which holds the requirements and criteria that the mitigations name.
A product extends this page with its own assets, interfaces and threats (section 6).
The source labels and the marker `not verified` follow [specification section 1](controller-framework-spec.md#1-scope-and-conventions).

## 1. Scope and assumptions

- The scope is the framework module and the base image at the Crux pin, on the reference board configuration.
- The network that reaches device management is untrusted.
- Physical access to the serial port, the medium and the debug port is part of the trust model: a person with it is treated as a possible attacker, and the product decides the physical protection (D16, S9).
- The application runs in the same image with no memory isolation from the framework (specification section 7.4), so it is trusted code.
- Image signing, the boot loader and the update path come from Crux's secure boot work (D7).
- The threat categories follow STRIDE (spoofing, tampering, repudiation, information disclosure, denial of service, elevation of privilege): standard practice, source `not verified`.

## 2. Assets

| Asset | Where | Needs |
|---|---|---|
| Account credentials: password verifiers and public keys | Crux credential store on the volume | Integrity, confidentiality |
| Device identity: TLS key and certificate | Crux credential store | Confidentiality of the key, integrity |
| Configuration: framework and application parameters | Settings file on the volume | Integrity |
| Application data | Application data root on the volume | Defined by the product |
| Security events | Crux RAM ring and the log; storage when persisted (L1) | Integrity, availability |
| Retained record and boot counter | Retained on-chip RAM | Integrity |
| Firmware image and its state | Image slots; Crux secure boot work | Integrity, authenticity |
| Controller function and outputs | Application; output safe state | Availability |
| Wall time | Crux Time, set from SNTP | Integrity |

Data minimisation (M1): the framework stores only the assets above.
The personal data among them are account names and the source network addresses in security events.

## 3. Interfaces

| Interface | Direction | Reached by | Protection |
|---|---|---|---|
| HTTPS web management | Inbound | The network | TLS (S7); an Access session on every route except the login, its attempt result and static sign-in assets (S4) |
| Serial command line | Inbound | Physical access to the console UART | An Access login on every command except the login and first-account setup (S4) |
| SSH command line (build option) | Inbound | The network | Crux Access and SSH on the Wolf profile (C7) |
| SNTP client | Outbound | The configured time servers | None: SNTP is unauthenticated |
| DHCP client and address resolution | Both | The local network | None |
| Removable medium (reference board) | Physical | A person who removes the card | Crux credential store tag and device binding (S9) |
| Debug port | Physical | A person at the board | Product lockdown, recorded in the product security documentation (T2) |
| Update path | Inbound | Open (D17) | Image signature checked by the boot loader (D7); security counter (U1) |
| Application interface | In the image | Application code | None: trusted code |

Outbound traffic inventory (M1): the base image opens no outbound connection other than SNTP queries and DHCP, and criterion 46 checks this.

## 4. Threats

| # | Target | Threat | Category | Mitigation | Residual risk |
|---|---|---|---|---|---|
| 1 | Web, serial | Password guessing | Spoofing | Crux Access login delay per source and per name, with events (S5) | A flood from many sources can keep network login delayed up to the cap |
| 2 | Web, serial | A route or command that skips authentication | Elevation | Mandatory access class per route, login on every command (S4) | None known |
| 3 | Web | Session theft or cross-site request forgery | Spoofing | Crux web session CSRF and Origin rules; idle and absolute session limits; TLS (S7) | — |
| 4 | Web | Eavesdropping or protocol downgrade | Disclosure, tampering | TLS 1.3 alone on the Crux listener at the pin (S7) | — |
| 5 | Web | Certificate substitution at the first connection | Spoofing | Fingerprint check at first enrolment (specification section 6.2) | An operator who skips the check |
| 6 | Medium | Card removed and read | Disclosure | Product record (S9) | The Crux store is not confidential against the medium and the chip ID ([C19](controller-framework-platform-gaps.md#c19-credential-store-at-rest)) |
| 7 | Medium | Card blanked or replaced | Tampering, elevation | A store from another device reads unusable; first-account setup is offered only on the serial command line (S1) | A blanked store reopens first-account setup to a person who also reaches the serial port (C19) |
| 8 | Update path | Malicious or older image | Tampering | Boot loader signature check (D7), security counter (U1), health-gated confirmation | No counter storage at the pin ([C16](controller-framework-platform-gaps.md#c16-security-counter)) |
| 9 | Network | Connection or request flood | Denial of service | Network limits (A1); supervision in a higher priority band (specification section 7.4) | No request rate limit at the pin ([C18](controller-framework-platform-gaps.md#c18-request-rate-limit)) |
| 10 | Wall time | Forged SNTP replies | Tampering | Every timing decision uses the monotonic clock | Audit timestamps can be falsified |
| 11 | Console, debug port | Access in production | Elevation | Console choice (D16) and debug-port lockdown recorded by the product (T2) | Defined by the product |
| 12 | Controller | Fault or reset loop | Denial of service | Watchdog, boot counter and safe mode (R1 to R3) | Safe mode cannot escape a fault in its own services |
| 13 | Image | Memory corruption in the application or framework | Elevation | Stack canaries and hardware stack protection (S6) | No memory partition between application and framework |
| 14 | Security events | Loss or forgery of records | Repudiation | Event list (L1); persistence with an opt-out | Records are not tamper-proof, and the RAM ring is lost at a reset unless persisted ([C17](controller-framework-platform-gaps.md#c17-security-event-persistence)) |
| 15 | All | A component with a known vulnerability | All | SBOM and vulnerability matching (V1, V2) | Matching needs identifiers that `west spdx` does not always emit (specification section 6.3) |
| 16 | Volume | Data left after a factory reset | Disclosure | Factory reset scope and the recorded erase method (S8) | File removal leaves old blocks on the medium unless the product erases them |

## 5. Annex I applicability

The point texts come from an unofficial reproduction of Regulation (EU) 2024/2847, `not verified` against the Official Journal.
[Specification section 6.5](controller-framework-spec.md#65-cra-annex-i-traceability) maps each point to requirements and criteria.

| Point | Applies | Reason |
|---|---|---|
| Part I (1) risk-based design | Yes | This page is the framework's part of the risk assessment |
| Part I (2)(a) no known exploitable vulnerabilities | Yes | The image contains third-party components |
| Part I (2)(b) secure by default, reset to the original state | Yes | The framework sets the default configuration and the factory reset |
| Part I (2)(c) security updates | In part | Security updates apply; automatic installation by default suits a controller poorly, because an update interrupts its function, so the product records its default and the reason in its technical documentation (Article 13(4)) |
| Part I (2)(d) protection from unauthorised access | Yes | Device management is reachable from the network |
| Part I (2)(e) confidentiality | Yes | In transit by TLS; at rest by a product record, because the protection depends on the medium and SoC |
| Part I (2)(f) integrity | Yes | Configuration, retained record, credentials and image |
| Part I (2)(g) data minimisation | Yes | The framework stores accounts and events (section 2) |
| Part I (2)(h) availability, resilience to denial of service | Yes | Device management is reachable from the network |
| Part I (2)(i) impact on other networks | Yes, small | The base image sends SNTP and DHCP traffic only |
| Part I (2)(j) limit attack surfaces | Yes | Services, console and debug port are build or product choices |
| Part I (2)(k) reduce the impact of an incident | Yes | Exploitation mitigation of the image |
| Part I (2)(l) record internal activity, with an opt-out | Yes | The framework records security events |
| Part I (2)(m) remove all data and settings | Yes | The framework owns the factory reset |
| Part II (1) to (7) vulnerability handling | Yes | The repository supplies the SBOM, the scan, the disclosure text and the release evidence |
| Part II (8) security updates free of charge | No | An organisational duty of the manufacturer (specification section 6.6) |

## 6. Product extension

A product copies this page's structure and adds:

- its own assets, such as process data and outputs, and its interfaces, such as field networks and its own ports;
- its threats and mitigations, and the residual risks that it accepts;
- its records for S9, D16 and the debug port, and its update default under Part I (2)(c);
- the risk sign-off, which is an organisational duty (specification section 6.6).

The product template for this extension is a deliverable of delivery stage 5 (specification section 6.3).
