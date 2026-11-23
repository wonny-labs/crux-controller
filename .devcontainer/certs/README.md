# Organisation root certificate folder

Behind a proxy that re-signs HTTPS with your organisation's root certificate authority (CA), place that CA certificate here as a `.crt`, `.pem` or `.cer` file and run **Dev Containers: Rebuild Container**. Each developer places their own file: Git ignores everything in this folder except this README and `.gitkeep`, so a certificate is never committed.

What the image build does with the file, and what stops it, is in [Behind a proxy or with a company certificate](../../docs/dev-container.md#behind-a-proxy-or-with-a-company-certificate).
