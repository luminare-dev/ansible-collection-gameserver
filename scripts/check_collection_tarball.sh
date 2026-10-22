#!/usr/bin/env bash
# Checks a built collection tarball the way a user installs it, before a release publishes it:
# installs luminare-gameserver-X.Y.Z.tar.gz into an empty temporary folder, then runs
# "ansible-playbook --syntax-check" on the installed playbook luminare.gameserver.gameserver with
# the installed example inventory, and on a play that uses every role of the installed collection.
# A tarball that misses a file the playbook, its pre-check or a role needs fails here.
#
#   bash scripts/check_collection_tarball.sh dist/luminare-gameserver-X.Y.Z.tar.gz
#
# release.yml runs it in extra-dist-command, after ansible-galaxy collection build; the unit test
# tests/test_collection_tarball.py runs it on a tarball built from the checkout. Needs
# ansible-galaxy and ansible-playbook (ansible-core) on the PATH.
set -euo pipefail

if [ "$#" -ne 1 ] || [ ! -f "$1" ]; then
  echo "usage: $0 <collection tarball>" >&2
  exit 2
fi
tarball="$1"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

# Only the installed collection counts: no collections or roles from the checkout or the home
# folder (a luminare.gameserver installed there would otherwise satisfy the install).
export ANSIBLE_COLLECTIONS_PATH="$work/collections"
export ANSIBLE_ROLES_PATH="$work/roles"
ansible-galaxy collection install --collections-path "$work/collections" "$tarball"
installed="$work/collections/ansible_collections/luminare/gameserver"

ansible-playbook --syntax-check -i "$installed/examples/inventory" luminare.gameserver.gameserver

roles=()
for dir in "$installed"/roles/*/; do
  roles+=("$(basename "$dir")")
done
if [ "${#roles[@]}" -eq 0 ]; then
  echo "the tarball has no roles" >&2
  exit 1
fi
{
  echo "- name: Every role of the installed collection"
  echo "  hosts: gameservers"
  echo "  gather_facts: false"
  echo "  roles:"
  for role in "${roles[@]}"; do
    echo "    - role: luminare.gameserver.${role}"
  done
} > "$work/every-role.yml"
ansible-playbook --syntax-check -i "$installed/examples/inventory" "$work/every-role.yml"
echo "ok: $(basename "$tarball") installs, and the playbook and the roles ${roles[*]} pass --syntax-check"
