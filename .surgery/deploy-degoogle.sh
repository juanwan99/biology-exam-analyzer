#!/bin/bash
# 目标1 摘谷歌远程部署脚本（在 jdcloud 上执行）
set -e
cd ~/biology-exam-analyzer

echo "=== 1. 拉取手术分支 ==="
git fetch origin 2>/dev/null || true   # origin 是 GitHub？不，本仓库是源头。从本地 push 过来的分支直接 checkout
git checkout upgrade/degoogle

echo "=== 2. 删除 gitignored 谷歌文件 ==="
rm -f backend/services/discovery_engine_client.py backend/services/evidence_gateway.py \
      backend/services/evidence_context.py backend/services/evidence_audit.py \
      backend/services/_kb_backend.py backend/services/agent_search_corpus.py \
      backend/test_discovery_engine_client.py backend/test_evidence_context.py
rm -rf backend/services/__pycache__ .credentials

echo "=== 3. 清理 .env 谷歌段 ==="
cp .env /tmp/env-backup-degoogle-$(date +%s)
for var in LLM_SA_CREDENTIALS LLM_PROJECT LLM_LOCATION HTTPS_PROXY LLM_API_KEY LLM_SDK_MODULE LLM_CLOUD_MODE \
           REPORT_GROUNDING_ENABLED EVIDENCE_RANKING_ENABLED EXAM_REVIEW_CHANNEL \
           LLM_EXAM_REVIEW_FLASH_MODEL LLM_EXAM_REVIEW_PRO_MODEL LLM_ENABLE_NATIVE_TEXT_FALLBACK; do
  sed -i "/^${var}=/d" .env
done
sed -i "/^DISCOVERY_ENGINE_/d" .env

echo "=== 4. 重建容器 ==="
docker compose up -d --build backend frontend

echo "=== 5. 等待健康 ==="
for i in $(seq 1 20); do
  sleep 5
  if curl -sf http://127.0.0.1:8001/health > /dev/null 2>&1; then echo "backend healthy"; break; fi
  if [ $i -eq 20 ]; then echo "FAIL: backend 未就绪"; exit 1; fi
done
curl -s http://127.0.0.1:8001/health
echo ""
docker exec biology_backend env | grep -icE "proxy|google|discovery|grounding" || echo "容器 env 谷歌/代理残留: 0"
