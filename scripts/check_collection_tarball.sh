#!/usr/bin/env bash
# Installs a built collection tarball into an empty folder and syntax-checks the installed playbook
# and every role:  bash scripts/check_collection_tarball.sh dist/luminare-gameserver-X.Y.Z.tar.gz
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
