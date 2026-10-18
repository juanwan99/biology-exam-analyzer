#!/usr/bin/env bash
# 仓 = 现网对账：逐文件比 sha256，0 差异才算对齐。只读现网（不重启、不改文件）。
#   1. 仓 HEAD 的部署文件 vs ECS 宿主目录（backend/ frontend/ database/ prompts/ docker-compose.yml）
#   2. 仓 HEAD 的 backend/、prompts/ vs 后端容器内 /app、/app/subject_prompts（compose 挂载）
#   3. 本机用仓里 frontend/ docker build 出的静态文件 vs 现网前端容器 /usr/share/nginx/html
# 宿主 / 容器里多出的文件若被仓 .gitignore 忽略（.env、logs、uploads、runtime.sqlite…），只计数不判差异。
#
# 用法：bash ops/diff-live.sh [--no-frontend]
# 环境：BEA_SSH（默认 ecs）、BEA_LIVE_DIR（默认 /home/ops/projects/biology-exam-analyzer）
set -uo pipefail

ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
SSH_HOST="${BEA_SSH:-ecs}"
LIVE_DIR="${BEA_LIVE_DIR:-/home/ops/projects/biology-exam-analyzer}"
FRONTEND=1
[ "${1:-}" = "--no-frontend" ] && FRONTEND=0

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
SCOPE=(backend frontend database prompts docker-compose.yml)
HASH='find "$@" -type f ! -path "*/__pycache__/*" ! -name "*.pyc" ! -path "*/node_modules/*" -print0 | xargs -0 -r sha256sum'

cd "$ROOT"
HEAD_SHA="$(git rev-parse --short HEAD)"
echo "== 仓 $HEAD_SHA vs 现网 $SSH_HOST:$LIVE_DIR · $(TZ=Asia/Shanghai date '+%F %T')"
[ -z "$(git status --porcelain -- "${SCOPE[@]}")" ] || echo "WARN  工作树有未提交改动，比的是 HEAD"

git archive HEAD "${SCOPE[@]}" | tar x -C "$WORK" --one-top-level=repo
(cd "$WORK/repo" && bash -c "$HASH" _ "${SCOPE[@]}") >"$WORK/repo.sha"

timeout 120 ssh "$SSH_HOST" "cd '$LIVE_DIR' && bash -c '$HASH' _ ${SCOPE[*]}" >"$WORK/host.sha" \
  || { echo "FAIL  读不到宿主目录"; exit 1; }
timeout 120 ssh "$SSH_HOST" "docker exec biology_backend sh -c 'cd /app && $HASH' _ ." >"$WORK/app.sha" \
  || { echo "FAIL  读不到后端容器"; exit 1; }

compare() {  # compare <label> <repo.sha> <live.sha> [仓前缀改写 from=to] [!跳过的仓前缀]
  python3 - "$@" <<'PY'
import subprocess, sys

label, repo_file, live_file = sys.argv[1:4]
rewrite = [r.split("=", 1) for r in sys.argv[4:] if not r.startswith("!")]
skip = [r[1:] for r in sys.argv[4:] if r.startswith("!")]  # 被运行期挂载盖住的仓路径

def load(path, rewrite=()):
    out = {}
    for line in open(path, encoding="utf-8", errors="surrogateescape"):
        h, _, p = line.rstrip("\n").partition("  ")
        p = p.removeprefix("./")
        if any(p.startswith(x) for x in skip):
            continue
        for src, dst in rewrite:
            if p.startswith(src):
                p = dst + p[len(src):]
                break
        else:
            if rewrite:
                continue  # 有改写规则时，只比规则覆盖的部分
        out[p] = h
    return out

repo = load(repo_file, rewrite)
live = load(live_file)
missing = sorted(set(repo) - set(live))
changed = sorted(p for p in set(repo) & set(live) if repo[p] != live[p])
extra = sorted(set(live) - set(repo))
ignored = set()
if extra:
    # 宿主 / 容器路径映射回仓路径后交给 git check-ignore 判断
    back = {}
    for p in extra:
        rp = p
        for src, dst in rewrite:
            if p.startswith(dst):
                rp = src + p[len(dst):]
                break
        back[rp] = p
    res = subprocess.run(["git", "check-ignore", "--no-index", "--stdin"],
                         input="\n".join(back), capture_output=True, text=True)
    ignored = {back[l] for l in res.stdout.splitlines() if l in back}
untracked = [p for p in extra if p not in ignored]

bad = len(missing) + len(changed) + len(untracked)
for tag, items in (("缺", missing), ("不同", changed), ("多出", untracked)):
    for p in items[:30]:
        print(f"  {tag}  {p}")
    if len(items) > 30:
        print(f"  … {tag} 共 {len(items)} 个")
print(("PASS  " if bad == 0 else "FAIL  ") +
      f"{label}：仓 {len(repo)} 个文件，缺 {len(missing)} / 不同 {len(changed)} / 多出 {len(untracked)}"
      f"（运行期忽略 {len(ignored)}）")
sys.exit(1 if bad else 0)
PY
}

FAILS=0
compare "宿主目录" "$WORK/repo.sha" "$WORK/host.sha" || FAILS=$((FAILS + 1))
# 容器 /app = ./backend；/app/subject_prompts = ./prompts（compose 挂载）。
# backend/reports/（无人 import 的旧包）在容器里被 ./reports:/app/reports 运行期挂载盖住，不比。
compare "后端容器 /app" "$WORK/repo.sha" "$WORK/app.sha" "!backend/reports/" "prompts/=subject_prompts/" "backend/=" || FAILS=$((FAILS + 1))

if [ "$FRONTEND" = 1 ]; then
  IMG="bea-frontend-diff:$HEAD_SHA"
  if docker build -q -t "$IMG" "$WORK/repo/frontend" >"$WORK/build.log" 2>&1; then
    LIST='cd /usr/share/nginx/html && find . -type f -print0 | xargs -0 sha256sum; sha256sum /etc/nginx/conf.d/default.conf'
    docker run --rm --entrypoint sh "$IMG" -c "$LIST" | sed 's#  \./#  html/#' >"$WORK/fe-repo.sha"
    timeout 60 ssh "$SSH_HOST" "docker exec biology_frontend sh -c '$LIST'" | sed 's#  \./#  html/#' >"$WORK/fe-live.sha"
    compare "前端容器（仓 build vs 现网）" "$WORK/fe-repo.sha" "$WORK/fe-live.sha" || FAILS=$((FAILS + 1))
    docker rmi -f "$IMG" >/dev/null 2>&1
  else
    echo "FAIL  前端 docker build 失败：$(tail -5 "$WORK/build.log")"
    FAILS=$((FAILS + 1))
  fi
fi

echo "== $([ "$FAILS" = 0 ] && echo '0 差异：仓 = 现网' || echo "FAIL $FAILS 处")"
[ "$FAILS" = 0 ]
