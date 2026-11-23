# J-Link package folder

You do not need to put anything here. **Dev Containers: Rebuild Container** downloads the J-Link version pinned in the [Dockerfile](../../Dockerfile) from SEGGER's download endpoint and installs it only if its SHA-256 matches. That download accepts SEGGER's terms of use. If it fails or the SHA-256 does not match, the Dev Container still builds and opens, without the J-Link software.

This folder is an override. Put the SEGGER J-Link software package for Linux, the 64-bit x86 Debian file (`JLink_Linux_<version>_x86_64.deb`), here, then run **Dev Containers: Rebuild Container**, to use a package you downloaded yourself from SEGGER, accepting its licence there. Git ignores every other file in this folder.

Instead of a file here, an organisation that hosts a copy after accepting the SEGGER licence itself can set the build arguments `CRUX_JLINK_URL` and `CRUX_JLINK_DEB_SHA256`. A file here wins over the URL, and both win over the download.

The [board route](../../../docs/board-bring-up.md#3-open-the-dev-container-with-the-probe) explains the rest.
