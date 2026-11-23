# J-Link package folder

Put the SEGGER J-Link software package for Linux, the 64-bit x86 Debian file (`JLink_Linux_<version>_x86_64.deb`), in this folder, then run **Dev Containers: Rebuild Container**. Without it the Dev Container still builds and opens, without the J-Link software. Download it yourself from SEGGER and accept its licence there. Git ignores every other file in this folder.

Instead of a file here, an organisation that hosts a copy after accepting the SEGGER licence itself can set the build arguments `CRUX_JLINK_URL` and `CRUX_JLINK_DEB_SHA256`. A file here wins over the URL.

The [board route guide](../../../docs/board-jlink-usbipd.md#steps) explains the rest.
