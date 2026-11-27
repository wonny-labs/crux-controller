/* SPDX-License-Identifier: Apache-2.0 */
#ifndef CONTROLLER_VERSION_H
#define CONTROLLER_VERSION_H

/*
 * The version of the controller framework, as compile-time macros (Semantic Versioning 2.0.0).
 *
 * This header is the one place the number is kept, as <crux/version.h> is for Crux. It is the
 * framework's version, not an image's: an application image sets its own version in a Zephyr
 * VERSION file. On the main branch the numeric parts name the next planned release and
 * CONTROLLER_VERSION_PRERELEASE is "dev", so a snapshot of main and that release have the same
 * numbers. Before 1.0, code must not test features by version number. No release and no tag
 * exist yet.
 */

/* Major version. */
#define CONTROLLER_VERSION_MAJOR 0

/* Minor version. */
#define CONTROLLER_VERSION_MINOR 1

/* Patch version. */
#define CONTROLLER_VERSION_PATCH 0

/* Pre-release identifier: "dev" on the main branch, "rc.N" for a candidate, "" in a release. */
#define CONTROLLER_VERSION_PRERELEASE "dev"

/* The full version without a leading "v", such as "0.1.0-dev" or "0.1.0". */
#define CONTROLLER_VERSION_STRING "0.1.0-dev"

#endif
