#!/usr/bin/env bash
# 现网对账：容器 → 健康 → 前端 → 专家账号登录 → 上传样卷跑全流程 → 逐题核分值与结果字段。
# 只读现网（不重启、不改配置）；跑一次分析会调 LLM，并在 score_prediction 表留一条记录（末尾打印 id）。
#
# 用法：
#   bash ops/check-live.sh                    # 默认样卷 ops/fixtures/sample-paper.docx
#   bash ops/check-live.sh --no-analyze       # 只查容器/健康/登录，不跑分析
#   bash ops/check-live.sh --paper 真卷.docx  # 跑别的卷：只核拆题与字段，不核分值（除非给 --expected）
#
# 账号与入口不进仓：优先读环境变量 BEA_BASE / BEA_USER / BEA_PASS，
# 否则从 BEA_CRED_FILE（默认 /home/liang/work/SHENTI.md）里的「地址：」「账号：user / pass」两行读。
# BEA_SSH 为现网 ssh 别名（默认 ecs）。
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PAPER="$HERE/fixtures/sample-paper.docx"
EXPECTED="$HERE/fixtures/sample-paper.expected.json"
ANALYZE=1
TIMEOUT_MIN="${BEA_TIMEOUT_MIN:-15}"

while [ $# -gt 0 ]; do
  case "$1" in
    --no-analyze) ANALYZE=0 ;;
    --paper) PAPER="$2"; EXPECTED=""; shift ;;
    --expected) EXPECTED="$2"; shift ;;
    *) echo "未知参数: $1" >&2; exit 2 ;;
  esac
  shift
done

CRED_FILE="${BEA_CRED_FILE:-/home/liang/work/SHENTI.md}"
SSH_HOST="${BEA_SSH:-ecs}"
if [ -r "$CRED_FILE" ]; then
  : "${BEA_BASE:=$(grep -oP '地址：\s*\Khttps?://[^ （(]+' "$CRED_FILE" | head -1)}"
  : "${BEA_USER:=$(grep -oP '账号：\s*\K[^ /]+' "$CRED_FILE" | head -1)}"
  : "${BEA_PASS:=$(grep -oP '账号：\s*[^ /]+\s*/\s*\K\S+' "$CRED_FILE" | head -1)}"
fi
for v in BEA_BASE BEA_USER BEA_PASS; do
  [ -n "${!v:-}" ] || { echo "缺 $v（设环境变量或检查 $CRED_FILE）" >&2; exit 2; }
done
BASE="${BEA_BASE%/}"

FAILS=0
pass() { echo "PASS  $*"; }
fail() { echo "FAIL  $*"; FAILS=$((FAILS + 1)); }
CURL=(curl -sS --noproxy '*' -m 60)

echo "== 审题现网对账 $(TZ=Asia/Shanghai date '+%F %T') · $BASE · ssh $SSH_HOST"

# 1. 三容器
ps_out="$(timeout 40 ssh -o ConnectTimeout=10 "$SSH_HOST" \
  'docker inspect -f "{{.Name}} {{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{else}}-{{end}}" biology_frontend biology_backend biology_postgres' 2>&1)"
for c in biology_frontend biology_backend biology_postgres; do
  line="$(grep "/$c " <<<"$ps_out")"
  if [[ "$line" == *" running "* && "$line" != *unhealthy* && "$line" != *starting* ]]; then
    pass "容器 $c ($line)"
  else
    fail "容器 $c: ${line:-$ps_out}"
  fi
done

# 2. 后端健康（容器内端口只绑 127.0.0.1，经 ssh 查）
health="$(timeout 30 ssh "$SSH_HOST" 'curl -s -m 10 127.0.0.1:8001/health' 2>&1)"
if [[ "$health" == *'"status":"healthy"'* && "$health" == *'"llm_configured":true'* ]]; then
  pass "后端 /health $health"
else
  fail "后端 /health: $health"
fi

# 3. 前端入口（专家走的就是这个地址）
if "${CURL[@]}" "$BASE/" | grep -q '<div id="root">'; then
  pass "前端 $BASE/ 出页面"
else
  fail "前端 $BASE/ 打不开"
fi

# 4. 专家账号登录
login="$("${CURL[@]}" -H 'Content-Type: application/json' \
  -d "$(python3 -c 'import json,sys; print(json.dumps({"username": sys.argv[1], "password": sys.argv[2]}))' "$BEA_USER" "$BEA_PASS")" \
  "$BASE/api/auth/login")"
TOKEN="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1]).get("token", ""))' "$login" 2>/dev/null)"
if [ -n "$TOKEN" ] && "${CURL[@]}" -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $TOKEN" "$BASE/api/auth/me" | grep -q 200; then
  pass "专家账号登录"
else
  fail "专家账号登录: ${login:0:200}"
fi

# 5. 上传样卷跑全流程（与前端默认一致：deep、不生成报告、生物）
if [ "$ANALYZE" = 1 ] && [ -n "$TOKEN" ]; then
  submit="$("${CURL[@]}" -m 180 -H "Authorization: Bearer $TOKEN" \
    -F "file=@$PAPER" -F mode=deep -F generate_report=false -F subject=biology \
    "$BASE/api/analyze_auto")"
  TASK="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1]).get("task_id", ""))' "$submit" 2>/dev/null)"
  if [ -z "$TASK" ]; then
    fail "上传 $(basename "$PAPER"): ${submit:0:300}"
  else
    pass "上传 $(basename "$PAPER") → task $TASK"
    RESULT="$(mktemp)"
    deadline=$(( $(date +%s) + TIMEOUT_MIN * 60 ))
    status=""
    while [ "$(date +%s)" -lt "$deadline" ]; do
      "${CURL[@]}" -m 30 "$BASE/api/analysis/status/$TASK" >"$RESULT" 2>/dev/null
      status="$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d["status"], d.get("message", ""))' "$RESULT" 2>/dev/null)"
      case "$status" in completed*|failed*) break ;; esac
      sleep 10
    done
    if [[ "$status" != completed* ]]; then
      fail "分析未完成（${TIMEOUT_MIN} 分钟内）: $status $(head -c 300 "$RESULT")"
    else
      python3 - "$RESULT" "$EXPECTED" <<'PY'
import json, sys

result = json.load(open(sys.argv[1]))["result"]
expected = json.load(open(sys.argv[2])) if sys.argv[2] else None
fails = 0

def check(ok, msg):
    global fails
    print(("PASS  " if ok else "FAIL  ") + msg)
    fails += 0 if ok else 1

qs = result.get("questions") or []
if expected:
    check(len(qs) == expected["question_count"], f"拆题 {len(qs)} 道（应 {expected['question_count']}）")
else:
    check(len(qs) > 0, f"拆题 {len(qs)} 道")

for q in qs:
    qid = str(q.get("id"))
    a = q.get("analysis") or {}
    d = q.get("difficulty") or {}
    comp = q.get("competency") or {}
    score = q.get("total_score")
    missing = [name for name, ok in [
        ("知识点", a.get("knowledge_points")),
        ("认知层级", a.get("bloom_level")),
        ("难度", d.get("difficulty_label")),
        ("素养", comp.get("primary_competency")),
    ] if not ok]
    problems = []
    if q.get("error"):
        problems.append(f"error={q['error'][:80]}")
    if missing:
        problems.append("缺" + "/".join(missing))
    if q.get("score_status") != "valid":
        problems.append(f"score_status={q.get('score_status')}")
    if expected and float(score or 0) != float(expected["scores"].get(qid, -1)):
        problems.append(f"分值 {score}≠卷面 {expected['scores'].get(qid)}")
    check(not problems, f"第 {qid} 题 {q.get('question_type')} {score}分 · {d.get('difficulty_label')} · "
          f"bloom {a.get('bloom_level')} · 知识点 {len(a.get('knowledge_points') or [])} 个"
          + (" · " + "；".join(problems) if problems else ""))

sp = result.get("score_prediction") or {}
total = sum(float(q.get("total_score") or 0) for q in qs)
if expected:
    check(total == expected["total_score"], f"卷面总分 {total:g}（应 {expected['total_score']}）")
check(sp.get("predicted_average") is not None,
      f"分数预估 均分 {sp.get('predicted_average')} / {sp.get('total_score')}，区间 {sp.get('confidence_interval')}")
check((result.get("exam_statistics") or {}).get("difficulty_distribution") is not None, "整卷统计")

# 降级告警只提示不判失败：试用时专家看到的结果仍完整，但值得事后看
for w in (result.get("metadata_quality") or {}).get("warning_questions", []):
    extra = [x for x in w.get("warnings", []) if x != "competency_supplement_skipped"]
    if extra:
        print(f"WARN  第 {w['id']} 题降级: {', '.join(extra)}")

print(f"INFO  耗时 {result.get('processing_time', 0):.0f}s；本次在现网 score_prediction 表留记录 id={sp.get('prediction_id')}"
      f"（exam_name=上传文件名）。删：docker exec biology_postgres psql -U biology -d biology_edu "
      f"-c 'delete from score_prediction where id={sp.get('prediction_id')}'")
sys.exit(1 if fails else 0)
PY
      [ $? -eq 0 ] || FAILS=$((FAILS + 1))
    fi
    rm -f "$RESULT"
  fi
fi

echo "== $([ "$FAILS" = 0 ] && echo '全部 PASS' || echo "FAIL $FAILS 处")"
[ "$FAILS" = 0 ]
