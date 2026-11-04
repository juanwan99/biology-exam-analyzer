#!/usr/bin/env bash
# 每日整跑（正本 §1：卡验收不进发版门，关单时跑一次、每天整跑一次）。只读现网（不重启、不改文件）。
#   1. check-live.sh 全流程（容器 / 健康 / 前端 / 专家登录 / 样卷，会调一次 LLM）
#   2. 现网 HEAD 的全量单测：git archive 进一次性容器跑（biology-backend 镜像、--network none），不碰现网目录
#   3. 运维项：后端 24 h ERROR 数（>0 判 FAIL）；千问兜底开关、deepseek /models 状态码只打印（key 归业主）
#
# 用法：bash ops/daily.sh
# 环境：BEA_SSH（默认 ecs）、BEA_LIVE_DIR（默认 /home/ops/projects/biology-exam-analyzer）；check-live 的环境变量照传
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SSH_HOST="${BEA_SSH:-ecs}"
LIVE_DIR="${BEA_LIVE_DIR:-/home/ops/projects/biology-exam-analyzer}"
FAILS=0
START=$SECONDS

echo "== 审题每日整跑 $(date '+%F %T')"

bash "$HERE/check-live.sh" || FAILS=$((FAILS + 1))

echo "== 全量单测（现网 HEAD，一次性容器）"
ut="$(timeout 600 ssh "$SSH_HOST" "cd '$LIVE_DIR' && echo HEAD \$(git rev-parse --short HEAD) && git archive HEAD backend prompts | docker run --rm -i --network none -e PYTHONDONTWRITEBYTECODE=1 --entrypoint sh biology-backend -c 'mkdir -p /tmp/w && tar -x -C /tmp/w && cp -r /tmp/w/prompts /tmp/w/backend/subject_prompts && cd /tmp/w/backend && python -m pytest -q -p no:cacheprovider 2>&1 | tail -1'" 2>&1)"
summary="$(tail -1 <<<"$ut")"
if [[ "$summary" == *" passed"* && "$summary" != *failed* && "$summary" != *error* ]]; then
  echo "PASS  单测 $(head -1 <<<"$ut") · $summary"
else
  echo "FAIL  单测: $ut"; FAILS=$((FAILS + 1))
fi

echo "== 运维项"
ops="$(timeout 60 ssh "$SSH_HOST" "cd '$LIVE_DIR' && echo ERR \$(docker logs --since 24h biology_backend 2>&1 | grep -c ' ERROR ') && grep -h '^LLM_ENABLE_QWEN_TEXT_FALLBACK=' .env; docker exec biology_backend python -c '
import os, httpx
r = httpx.get(\"https://api.deepseek.com/models\", headers={\"Authorization\": \"Bearer \" + os.environ.get(\"DEEPSEEK_API_KEY\", \"\")}, timeout=15)
print(\"DEEPSEEK\", r.status_code)'" 2>&1)"
errs="$(grep -oP '^ERR \K\d+' <<<"$ops")"
if [ "${errs:-x}" = 0 ]; then echo "PASS  后端 24 h ERROR 0"; else echo "FAIL  后端 24 h ERROR: ${errs:-$ops}"; FAILS=$((FAILS + 1)); fi
echo "INFO  千问兜底开关 $(grep -oP '^LLM_ENABLE_QWEN_TEXT_FALLBACK=\K.*' <<<"$ops" || echo '?')"
echo "INFO  deepseek /models $(grep -oP '^DEEPSEEK \K\d+' <<<"$ops" || echo "? $ops")（200 = key 可用）"

echo "== 每日整跑 $([ "$FAILS" = 0 ] && echo '全部 PASS' || echo "FAIL $FAILS 处")，用时 $((SECONDS - START)) s"
[ "$FAILS" = 0 ]
