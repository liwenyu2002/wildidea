#!/usr/bin/env bash
# 把当前 main 树 + 本地排除的 Web 源码（src/tests/pyproject/deploy 等）
# 打成 `web` 分支的一个新提交并推到 gitee/master。
#
# 仓库拓扑：main（仅 Skill 内容）→ GitHub；web（完整代码）→ gitee/master。
# Web 源码通过 .git/info/exclude 在 main 上保持不可见，仅存在于工作树。
# 重要：不要在本工作树 checkout web 分支——切回 main 时 git 会把 src/ 等
# 从磁盘删除，而这些文件没有其他副本。本脚本用临时索引构建提交，全程不切分支。
#
# 用法：bash scripts/sync_web_branch.sh          # 构建并推送
#       bash scripts/sync_web_branch.sh --no-push # 只构建，不推送
set -euo pipefail
cd "$(dirname "$0")/.."

WEB_PATHS=(src tests pyproject.toml requirements.txt deploy HERMES_DEPLOY.md .env.example assets)
TMP_INDEX=".git/web-sync-index"
trap 'rm -f "$TMP_INDEX"' EXIT

main_commit=$(git rev-parse main)

# 1. 从 main 的树初始化临时索引
GIT_INDEX_FILE="$TMP_INDEX" git read-tree "$main_commit"

# 2. 强制加入被本地排除的 Web 路径（-f 会连带 gitignore 的垃圾，下一步清掉）
GIT_INDEX_FILE="$TMP_INDEX" git add -f "${WEB_PATHS[@]}"
GIT_INDEX_FILE="$TMP_INDEX" git rm -r --cached -q --ignore-unmatch \
  '*.DS_Store' '*__pycache__*' '*.pyc' '*.egg-info*' '.pytest_cache' >/dev/null || true

# 3. 安全检查：绝不允许真实密钥/数据库进树
tree=$(GIT_INDEX_FILE="$TMP_INDEX" git write-tree)
if git ls-tree -r "$tree" --name-only | grep -Ex '\.env|.*\.db'; then
  echo "FATAL: secret or database file would be committed; aborting." >&2
  exit 1
fi

# 4. 在 web 分支上叠加提交（树无变化则跳过）
if git rev-parse -q --verify refs/heads/web >/dev/null; then
  parent=$(git rev-parse refs/heads/web)
  if [ "$(git rev-parse "$parent^{tree}")" = "$tree" ]; then
    echo "web branch already up to date ($parent)"
    exit 0
  fi
  commit=$(git commit-tree "$tree" -p "$parent" -p "$main_commit" \
    -m "Sync web branch from main $(git rev-parse --short "$main_commit")")
else
  # 首次：以 gitee/master 现状为父，保住历史
  parent=$(git rev-parse gitee/master 2>/dev/null || echo "")
  if [ -n "$parent" ]; then
    commit=$(git commit-tree "$tree" -p "$parent" \
      -m "Add web application source (src/, tests/, deploy/)" )
  else
    commit=$(git commit-tree "$tree" -m "Add web application source")
  fi
fi
git update-ref refs/heads/web "$commit"
echo "web branch -> $commit"

# 5. 推送
if [ "${1:-}" != "--no-push" ]; then
  git push gitee web:master
fi
