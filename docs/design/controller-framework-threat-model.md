# Controller framework threat model

This page lists the assets, interfaces and threats of the [controller framework](controller-framework.md) and its base image, and says which points of Annex I of the EU Cyber Resilience Act apply, with the reason.
It serves requirements H1 and M1 of the [specification](controller-framework-spec.md#2-requirements), which holds the requirements and criteria that the mitigations name.
A product extends this page with its own assets, interfaces and threats (section 6).
The source labels follow [specification section 1](controller-framework-spec.md#1-scope-and-conventions).

## 1. Scope and assumptions

- The scope is the framework module, its application interface (specification section 3) and the base image at the Crux pin, on the reference board configuration.
- The application template (specification section 7.5) is outside the scope: a copy of it is product code, which the product's extension covers (section 6).
- The network that reaches device management is untrusted.
- Physical access to the serial port, the medium and the debug port is part of the trust model: a person with it is treated as a possible attacker, and the product decides the physical protection (D16, S9).
- The application runs in the same image with no memory isolation from the framework (specification section 7.4), so it is trusted code.
- Image signing, the boot loader and the update path come from Crux's secure boot work (D7).
- The threat categories follow STRIDE (not read): spoofing, tampering, repudiation, information disclosure, denial of service and elevation of privilege.

## 2. Assets

| Asset | Where | Needs |
|---|---|---|
| Account credentials: password verifiers and public keys | Crux credential store on the volume | Integrity, confidentiality |
| Device identity: TLS key and certificate | Crux credential store | Confidentiality of the key, integrity |
| Configuration: framework and application parameters | Settings file on the volume once the framework initialises Crux's save provider through the composition interface that Crux publishes at the pin (C22); in RAM only until then | Integrity |
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
| Address resolution (ARP) | Both | The local network | None |
| DHCP client (off in the reference configuration) | Both | The local network | None |
| DNS client (only when the time server is given by name) | Outbound | The configured DNS server | None |
| Removable medium (reference board) | Physical | A person who removes the card | Crux credential store tag and device binding (S9) |
| Debug port | Physical | A person at the board | Product lockdown, recorded in the product security documentation (H2) |
| Update path | Inbound | Open (D17) | Image signature checked by the boot loader (D7); security counter (U1) |
| Application interface | In the image | Application code | None: trusted code; the framework accepts registrations only inside `init` and only through the context it gave |
| Application control commands (`application stop`, `application start`) | Inbound | Serial command line | An Access login and the permission `system.reboot` (S4) |
| Application status items and parameter table | Inbound, through web management and the serial command line | Sessions | The read and write permissions that the application names for each item and parameter, which Crux requires (S4) |
| Application data root (File root 3, directory `app`) | In the image | Application code | Crux File confines access to the root and refuses growth beyond its byte limit (`CONFIG_CRUX_CONTROLLER_APP_ROOT_MAX_BYTES`, [C15](controller-framework-platform-gaps.md#c15-size-limit-of-the-application-data-root)) |
| Factory reset command (`factory reset`) | Inbound | Serial command line | An Access login and the permission `access.manage` (S2, S4); a session without it does not see the command |
| Crux service thread progress | In the image | Crux service threads | None: Crux code calls the framework's progress function, which only feeds task watchdog channels ([C8](controller-framework-platform-gaps.md#c8-crux-service-threads-and-supervision)) |

Outbound traffic inventory (M1): in the reference configuration, the base image sends SNTP queries to the configured time server and ARP on the local network, and opens no other outbound connection.
DHCP is off there, and a build that turns it on adds DHCP traffic.
DNS queries occur only when the time server is given by name, which needs a DNS resolver in the image.
Criterion 46 checks this inventory.

## 4. Threats

Status says where each mitigation stands: at the pin (Crux provides it), Crux `main`, Planned in Crux, Crux change needed, specified (these pages specify it, not yet implemented), implemented (this repository implements it, with `native_sim` evidence and no board run) or product (the product provides it).

| # | Target | Threat | Category | Mitigation | Residual risk | Status |
|---|---|---|---|---|---|---|
| 1 | Web, serial | Password guessing | Spoofing | Crux Access login delay per source and per name, with events (S5); the storage scenario shows the delay and the events on both interfaces (criterion 43) | A flood from many sources can keep network login delayed up to the cap | Implemented |
| 2 | Web, serial | A route or command that skips authentication or its permission | Elevation | Mandatory access class per route, login on every command, and the permission that a route or command names (S4) | The checks of a session without a route's or command's permission follow the delivery stage of that route or command (criterion 34) | At the pin |
| 3 | Web | Session theft or cross-site request forgery | Spoofing | Crux web session CSRF and Origin rules; idle and absolute session limits; TLS (S7) | — | At the pin |
| 4 | Web | Eavesdropping or protocol downgrade | Disclosure, tampering | TLS 1.3 alone on the Crux listener at the pin (S7) | — | At the pin |
| 5 | Web | Certificate substitution at the first connection | Spoofing | Fingerprint check at first enrolment (specification section 6.2) | An operator who skips the check | Specified |
| 6 | Medium | Card removed and read | Disclosure | Product record (S9) | The Crux store is not confidential against the medium and the chip ID ([C19](controller-framework-platform-gaps.md#c19-credential-store-at-rest)) | Product |
| 7 | Medium | Card blanked, replaced or rolled back | Tampering, elevation | A store from another device reads unusable; first-account setup is offered only on the serial command line (S1) | A blanked store reopens first-account setup to a person who also reaches the serial port, and a rollback to an older copy of the store is not detected (C19) | At the pin |
| 8 | Update path | Malicious or older image | Tampering | Boot loader signature check (D7), security counter (U1), health-gated confirmation | No counter storage at the pin ([C16](controller-framework-platform-gaps.md#c16-security-counter)) | Crux change needed |
| 9 | Network | Connection, request or event flood | Denial of service | Network limits (A1); supervision in a higher priority band (specification section 7.4); a size limit and rotation of persisted events | No request rate limit at the pin ([C18](controller-framework-platform-gaps.md#c18-request-rate-limit)) | At the pin; Crux change needed |
| 10 | Wall time | Forged SNTP replies | Tampering | Every timing decision uses the monotonic clock | Audit timestamps can be falsified | Specified |
| 11 | Console, debug port | Access in production | Elevation | Console choice (D16) and debug-port lockdown recorded by the product (H2) | Defined by the product | Product |
| 12 | Controller | Fault or reset loop | Denial of service | Watchdog, boot counter and safe mode (R1 to R3) | Safe mode cannot escape a fault in its own services | Specified |
| 13 | Image | Memory corruption in the application or framework | Elevation | Stack canaries and hardware stack protection (S6) | No memory partition between application and framework | Specified |
| 14 | Security events | Loss or forgery of records, or events that fill the volume | Repudiation, denial of service | Event list (L1); persistence with an opt-out, a size limit and rotation | Records are not tamper-proof, rotation drops the oldest, and the RAM ring is lost at a reset unless persisted ([C17](controller-framework-platform-gaps.md#c17-security-event-persistence)) | Planned in Crux |
| 15 | All | A component with a known vulnerability | All | SBOM and vulnerability matching (V1, V2) | Matching needs identifiers that `west spdx` does not always emit (specification section 6.3) | Specified |
| 16 | Volume | Data left after a factory reset, or a reset cut by a power loss | Disclosure, tampering | Factory reset scope and the recorded erase method (S8): the command removes the data root's files and the settings file, then erases the accounts last and keeps the device identity; a cut reset is repeated until the erase completes (specification section 5.3; the storage scenario cuts the power before the erase) | File removal leaves old blocks on the medium unless the product erases them; the kept TLS key is as readable as the rest of the store to a person with the medium and the chip ID, so a change of owner needs device preparation again (Crux `credential_store_zephyr.h`) | Implemented; product |
| 17 | Web, serial | Malformed input | Tampering, denial of service | Crux Web request body and time limits; host fuzzing of the retained-record decode and the framework's management text parsers (Q1); Crux fuzzes its command line and its configuration routes | Zephyr's HTTP parser is not fuzzed by this repository | At the pin; implemented |
| 18 | Serial | An operator stop or start of the application by a session without the right | Elevation | Both commands need an Access login and the permission `system.reboot` (S4); the application scenario shows both refused to an account of the read-only role | Every session that may restart the controller may also stop the application; no permission of its own yet | Implemented |
| 19 | Application status items and parameters | An item or parameter exposed with a weak permission | Disclosure, tampering | Crux requires a read permission for every item and parameter, and a write permission for a writable parameter; the product reviews its application's tables | The framework does not judge the permissions that the application names | Product |
| 20 | Volume | Application data fills the volume and leaves no space for the credential store and the settings | Denial of service | A byte limit of the application data root, enforced by Crux File, and storage reported degraded at the limit (specification section 5.4) | Files written outside Crux File are not counted (Crux `docs/file-contract.md`, "Root byte limits") | Implemented |
| 21 | Controller | An application that hangs, stalls a thread or fails | Denial of service | A channel per application thread, deadlines on `init`, `start` and `stop`, `safe_state` before a reset, and a reset on a hang (specification sections 3 and 4) | Outputs keep a safe state across a reset only through the board's hardware default, and application threads can overwrite outputs after the supervisor's `safe_state` until the reset (specification section 3.3) | Implemented |
| 22 | Controller | A Crux service thread of device management that hangs | Denial of service | A task watchdog channel per started Crux service thread, fed from Crux's progress function, and a reset on an expiry (specification section 4.3, C8) | The HTTP server thread and Zephyr's network and logging threads are still supervised indirectly | Implemented |

## 5. Annex I applicability

The point texts are unofficial text of Regulation (EU) 2024/2847, not checked against the Official Journal.
[Specification section 6.5](controller-framework-spec.md#65-cra-annex-i-traceability) maps each point to requirements and criteria.

| Point | Applies | Reason |
|---|---|---|
| Part I (1) risk-based design | Yes | This page is the framework's part of the risk assessment |
| Part I (2)(a) no known exploitable vulnerabilities | Yes | The image contains third-party components |
| Part I (2)(b) secure by default, reset to the original state | Yes | The framework sets the default configuration and the factory reset |
| Part I (2)(c) security updates | In part | Security updates apply; the product decides its update default from its risk assessment and records the default and the reason in its technical documentation (Article 13(4)) |
| Part I (2)(d) protection from unauthorised access | Yes | Device management is reachable from the network |
| Part I (2)(e) confidentiality | Yes | In transit by TLS; at rest by a product record, because the protection depends on the medium and SoC |
| Part I (2)(f) integrity | Yes | Configuration, retained record, credentials and image |
| Part I (2)(g) data minimisation | Yes | The framework stores accounts and events (section 2) |
| Part I (2)(h) availability, resilience to denial of service | Yes | Device management is reachable from the network |
| Part I (2)(i) impact on other networks | Yes, small | In the reference configuration, the base image sends SNTP and ARP traffic only |
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

The product threat model template for this extension is a deliverable of delivery stage 5 (specification section 6.3).
