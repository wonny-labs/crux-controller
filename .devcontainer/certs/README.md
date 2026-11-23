# Organisation root certificate folder

You need this folder only behind a proxy that inspects TLS: it decrypts HTTPS and re-signs it with a certificate of your organisation, and tools in the Dev Container then fail with errors such as `curl: (60) SSL certificate problem: unable to get local issuer certificate`.

Place your organisation's root certificate authority (CA) certificate here as a `.crt`, `.pem` or `.cer` file, then run **Dev Containers: Rebuild Container** (or `bash scripts/dev-shell.sh` again). The first step of the image build installs every such file as a system certificate, before any download: PEM files as they are, DER files converted to PEM. A file that is neither, or that holds a private key, is skipped with a message that names it. An empty folder changes nothing.

Each developer places their own file. Git ignores everything in this folder except this README and `.gitkeep`, so a certificate is never committed, here or in any copy of the repository.

How to export the certificate on Windows, check which CA signs the proxy's certificates and convert a DER file is in [Behind a proxy or with a company certificate](../../docs/dev-container.md#behind-a-proxy-or-with-a-company-certificate).
