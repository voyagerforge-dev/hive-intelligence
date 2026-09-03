# The packages this repository releases, in dependency order (hive-gen before hive-serve).
#
# The ONE place this set is stated. Sourced by tools/set-release-version.sh,
# tools/build-release.sh and tools/verify-clean-install.sh; the proof scripts run inside a
# container that cannot source it, so the harness passes the same names in as the
# RELEASED_PACKAGES environment variable and tools/released.py reads them there. Adding a name
# here therefore builds, installs, probes and version-checks it everywhere - but does NOT
# write it a step in tools/smoke-installed.py, and a distribution no step exercises fails that
# run rather than shipping unproven. tooling/hive-author is NOT here on purpose: see
# set-release-version.sh.
#
# Sourced, never executed, so it carries no shebang; the directive below names the shell
# to check it as, and says the array is read by the scripts that source it, not here.
# shellcheck shell=bash disable=SC2034
RELEASED_PACKAGES=(hive-gen hive-prep hive-serve hive-dbparse hive-zendesk)
