#!/usr/bin/env bash
# 镜像一致性检查：仓库根目录的散装文件与 skill/wildidea/ 打包分发版必须逐字节一致。
# 本地或 CI 均可运行：bash scripts/check_mirrors.sh
set -u
cd "$(dirname "$0")/.."

fail=0
check() {
  if ! diff -q "$1" "$2" >/dev/null 2>&1; then
    echo "MIRROR DRIFT: $1 <> $2"
    fail=1
  fi
}

check SKILL.md                                  skill/wildidea/SKILL.md
check agents/openai.yaml                        skill/wildidea/agents/openai.yaml
check templates/poster.html                     skill/wildidea/templates/poster.html
# skill 包里的 wildidea-skill.md 镜像源是 docs/（根 references/ 刻意不含它）
check docs/wildidea-skill.md                    skill/wildidea/references/wildidea-skill.md

for f in common-chinese-chars.txt domains.json mechanism-transfer.md \
         output-innovation-recipes.md poster-guide.md poster-palettes.md \
         search-integration.md; do
  check "references/$f" "skill/wildidea/references/$f"
done

# scripts/ 只有这 6 个文件是镜像；install.sh 与根目录其余脚本是仓库级工具，刻意不随 Skill 分发
for f in pick_domain_slots.py pick_seed.py search_char.py search_helper.py \
         validate_poster.py validate_search.py; do
  check "scripts/$f" "skill/wildidea/scripts/$f"
done

if [ "$fail" -eq 0 ]; then
  echo "All mirrors in sync."
fi
exit "$fail"
