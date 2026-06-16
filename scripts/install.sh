#!/usr/bin/env bash
set -euo pipefail

repo_url="https://github.com/liwenyu2002/wildidea"
ref="${WILDIDEA_REF:-main}"
skills_dir="${SKILLS_DIR:-${WILDIDEA_SKILLS_DIR:-$HOME/.codex/skills}}"

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

echo "Installing WildIdea from ${repo_url}..."

curl -fsSL "${repo_url}/archive/refs/heads/${ref}.tar.gz" | tar -xz -C "$tmp_dir"
repo_dir="$(find "$tmp_dir" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
source_dir="${repo_dir}/skill/wildidea"
target_dir="${skills_dir}/wildidea"

if [ ! -d "$source_dir" ]; then
  echo "WildIdea skill package was not found in the downloaded archive." >&2
  exit 1
fi

mkdir -p "$skills_dir"
rm -rf "$target_dir"
cp -R "$source_dir" "$target_dir"

echo "WildIdea installed to ${target_dir}"
