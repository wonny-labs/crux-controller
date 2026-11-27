# Organisation root certificate folder

Behind a proxy that re-signs HTTPS with your organisation's root certificate authority (CA), downloads in the image build or in the container fail with a certificate error such as `curl: (60) SSL certificate problem: unable to get local issuer certificate`, or the same from pip, Git or west. Place that CA certificate here, preferably as a PEM `.crt` file (`.pem` and `.cer` are also read), and run **Dev Containers: Rebuild Container**, or **Reopen in Container** for a first start. Each developer places their own file: Git ignores everything in this folder except this README and `.gitkeep`, so a certificate is never committed.

What the image build does with the file, and what stops it, is in [Behind a proxy or with a company certificate](../../docs/dev-container.md#behind-a-proxy-or-with-a-company-certificate).
