#!/usr/bin/env bash
# 每日整跑（正本 §1：卡验收不进发版门，关单时跑一次、每天整跑一次）。只读现网（不重启、不改文件）。
#   1. check-live.sh 全流程（容器 / 健康 / 前端 / 专家登录 / 样卷，会调一次 LLM，跑完删本次测试记录）
#   2. 现网 HEAD 的全量单测：git archive 进一次性容器跑（biology-backend 镜像、--network none），不碰现网目录
#   3. PDF 真卷回归（#7/#27）：同样一次性容器，卷子 mock2026 只读挂进去，21 题 + 分值一变或卷子不在都判 FAIL
#   4. 运维项：后端 24 h ERROR 数（>0 判 FAIL）；现网文字链、deepseek /models 状态码只打印（key 归业主）
#
# 用法：bash ops/daily.sh
# 环境：BEA_SSH（默认 ecs）、BEA_LIVE_DIR（默认 /home/ops/projects/biology-exam-analyzer）、
#       BEA_PDF_DIR（ECS 上放 mock2026.pdf 的非仓目录，默认 /home/ops/bea-work7）；check-live 的环境变量照传
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SSH_HOST="${BEA_SSH:-ecs}"
LIVE_DIR="${BEA_LIVE_DIR:-/home/ops/projects/biology-exam-analyzer}"
PDF_DIR="${BEA_PDF_DIR:-/home/ops/bea-work7}"
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

echo "== PDF 真卷回归 mock2026（现网 HEAD，一次性容器）"
reg="$(timeout 300 ssh "$SSH_HOST" "cd '$LIVE_DIR' && { test -r '$PDF_DIR/mock2026.pdf' || { echo 卷子不可读; exit 1; }; } && git archive HEAD backend | docker run --rm -i --network none -e PYTHONDONTWRITEBYTECODE=1 -e BEA_PDF_MOCK2026=/w/mock2026.pdf -v '$PDF_DIR/mock2026.pdf:/w/mock2026.pdf:ro' --entrypoint sh biology-backend -c 'mkdir -p /tmp/w && tar -x -C /tmp/w && cd /tmp/w/backend && python -m pytest -q -p no:cacheprovider tests/test_pdf_splitter.py::test_mock2026_pdf_regression 2>&1 | tail -15'" 2>&1)"
last="$(tail -1 <<<"$reg")"
if [[ "$last" == "1 passed"[\ ,]* && "$last" != *skipped* && "$last" != *failed* && "$last" != *error* ]]; then
  echo "PASS  PDF 回归 21 题 + 分值"
else
  echo "FAIL  PDF 回归（卷子 $PDF_DIR/mock2026.pdf）: ${reg:-超时或无输出}"; FAILS=$((FAILS + 1))
fi

echo "== 运维项"
ops="$(timeout 60 ssh "$SSH_HOST" "cd '$LIVE_DIR' && echo ERR \$(docker logs --since 24h biology_backend 2>&1 | grep -c ' ERROR ') && docker exec biology_backend python -c '
import os, httpx
from llm_config import get_providers
print(\"CHAIN\", \" → \".join(p[\"name\"] for p in get_providers(\"question_analysis\")))
r = httpx.get(\"https://api.deepseek.com/models\", headers={\"Authorization\": \"Bearer \" + os.environ.get(\"DEEPSEEK_API_KEY\", \"\")}, timeout=15)
print(\"DEEPSEEK\", r.status_code)'" 2>&1)"
errs="$(grep -oP '^ERR \K\d+' <<<"$ops")"
if [ "${errs:-x}" = 0 ]; then echo "PASS  后端 24 h ERROR 0"; else echo "FAIL  后端 24 h ERROR: ${errs:-$ops}"; FAILS=$((FAILS + 1)); fi
echo "INFO  文字链 $(grep -oP '^CHAIN \K.*' <<<"$ops" || echo '?')"
echo "INFO  deepseek /models $(grep -oP '^DEEPSEEK \K\d+' <<<"$ops" || echo "? $ops")（200 = key 可用）"

echo "== 每日整跑 $([ "$FAILS" = 0 ] && echo '全部 PASS' || echo "FAIL $FAILS 处")，用时 $((SECONDS - START)) s"
[ "$FAILS" = 0 ]
