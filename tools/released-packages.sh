# The packages this repository releases, in dependency order (hive-gen before hive-serve).
#
# The ONE place this set is stated. Sourced by tools/set-release-version.sh,
# tools/build-release.sh and tools/verify-clean-install.sh; the proof scripts run inside a
# container that cannot source it, so the harness passes the same names in as the
# RELEASED_PACKAGES environment variable and tools/released.py reads them there. Adding a name
# here therefore builds, installs, probes and version-checks it everywhere - but does NOT
# write it a step in tools/smoke-installed.py, and a distribution no step exercises fails that
# run rather than shipping unproven.
#
# hive-author joined the set for 0.7.0. It is a service rather than a library, which is why it
# was held back, but a deployment still has to GET it from somewhere, and doing that from the
# same pin as the rest is what stops one component being placed on a host by hand.
#
# Sourced, never executed, so it carries no shebang; the directive below names the shell
# to check it as, and says the array is read by the scripts that source it, not here.
# shellcheck shell=bash disable=SC2034
RELEASED_PACKAGES=(hive-gen hive-prep hive-serve hive-dbparse hive-zendesk hive-author)
