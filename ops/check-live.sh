#!/usr/bin/env bash
# 现网对账：容器 → 健康 → 前端 → 专家账号登录 → 上传样卷跑全流程 → 逐题核分值与结果字段。
# 只读现网（不重启、不改配置）；跑一次分析会调 LLM，并在 score_prediction 表留一条记录，跑完删掉并核实（--keep-record 留着）。
#
# 用法：
#   bash ops/check-live.sh                    # 默认样卷 ops/fixtures/sample-paper.docx + 去分值版核推断偏差
#   bash ops/check-live.sh --no-analyze       # 只查容器/健康/登录，不跑分析
#   bash ops/check-live.sh --paper 真卷.docx  # 跑别的卷：只核拆题与字段，不核分值（除非给 --expected）
#   bash ops/check-live.sh --keep-record      # 不删本次 score_prediction 记录（调试用）
#
# 账号与入口不进仓：优先读环境变量 BEA_BASE / BEA_USER / BEA_PASS，
# 否则从 BEA_CRED_FILE（默认 /home/liang/work/SHENTI.md）里的「地址：」「账号：user / pass」两行读。
# BEA_SSH 为现网 ssh 别名（默认 ecs）。
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PAPER="$HERE/fixtures/sample-paper.docx"
EXPECTED="$HERE/fixtures/sample-paper.expected.json"
ANALYZE=1
KEEP_RECORD=0
TIMEOUT_MIN="${BEA_TIMEOUT_MIN:-15}"

while [ $# -gt 0 ]; do
  case "$1" in
    --no-analyze) ANALYZE=0 ;;
    --keep-record) KEEP_RECORD=1 ;;
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
#    默认两份同时跑：标了分值的样卷逐题核分值；同一卷去掉题号后与小问后分值（只留分节说明）核推断偏差（#29）
check_result() {  # $1 结果文件  $2 expected（可空）  $3 strict|infer
  python3 - "$1" "$2" "$3" <<'PY'
import json, sys

INFER_TOL_Q = 2

result = json.load(open(sys.argv[1]))["result"]
expected = json.load(open(sys.argv[2])) if sys.argv[2] else None
infer = sys.argv[3] == "infer"   # 卷面分值藏掉的样卷：分值不逐题判，按偏差门槛判
fails = 0
deviations = []

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
    if q.get("score_status") not in (("valid", "inferred") if infer else ("valid",)):
        problems.append(f"score_status={q.get('score_status')}")
    if expected and infer:
        deviations.append((qid, float(score or 0), float(expected["scores"].get(qid, 0))))
    elif expected and float(score or 0) != float(expected["scores"].get(qid, -1)):
        problems.append(f"分值 {score}≠卷面 {expected['scores'].get(qid)}")
    check(not problems, f"第 {qid} 题 {q.get('question_type')} {score}分 · {d.get('difficulty_label')} · "
          f"bloom {a.get('bloom_level')} · 知识点 {len(a.get('knowledge_points') or [])} 个"
          + (" · " + "；".join(problems) if problems else ""))

sp = result.get("score_prediction") or {}
total = sum(float(q.get("total_score") or 0) for q in qs)
if expected and infer:
    # 门槛：分节写了小计，总分必须对上；每题偏差 ≤ INFER_TOL_Q 分
    worst = max(deviations, key=lambda d: abs(d[1] - d[2]), default=("-", 0, 0))
    diff_total = total - expected["total_score"]
    check(abs(diff_total) < 1e-6 and abs(worst[1] - worst[2]) <= INFER_TOL_Q,
          f"分值推断偏差 总分 {total:g}（卷面 {expected['total_score']}，差 {diff_total:+g}）· "
          f"每题最大差 {worst[1] - worst[2]:+g}（第 {worst[0]} 题 {worst[1]:g}/{worst[2]:g}，门槛 ±{INFER_TOL_Q}）· "
          + " ".join(f"{i}:{s:g}/{e:g}" for i, s, e in deviations))
elif expected:
    check(total == expected["total_score"], f"卷面总分 {total:g}（应 {expected['total_score']}）")
check(sp.get("predicted_average") is not None,
      f"分数预估 均分 {sp.get('predicted_average')} / {sp.get('total_score')}，区间 {sp.get('confidence_interval')}")
check((result.get("exam_statistics") or {}).get("difficulty_distribution") is not None, "整卷统计")

# 降级告警只提示不判失败：试用时专家看到的结果仍完整，但值得事后看
for w in (result.get("metadata_quality") or {}).get("warning_questions", []):
    extra = [x for x in w.get("warnings", []) if x != "competency_supplement_skipped"]
    if extra:
        print(f"WARN  第 {w['id']} 题降级: {', '.join(extra)}")

print(f"INFO  耗时 {result.get('processing_time', 0):.0f}s")
sys.exit(1 if fails else 0)
PY
}

if [ "$ANALYZE" = 1 ] && [ -n "$TOKEN" ]; then
  RUNS=("$PAPER|$EXPECTED|strict")
  [ "$PAPER" = "$HERE/fixtures/sample-paper.docx" ] && RUNS+=("$HERE/fixtures/sample-paper-unscored.docx|$EXPECTED|infer")
  TASKS=()
  for run in "${RUNS[@]}"; do
    paper="${run%%|*}"
    submit="$("${CURL[@]}" -m 180 -H "Authorization: Bearer $TOKEN" \
      -F "file=@$paper" -F mode=deep -F generate_report=false -F subject=biology \
      "$BASE/api/analyze_auto")"
    task="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1]).get("task_id", ""))' "$submit" 2>/dev/null)"
    if [ -z "$task" ]; then fail "上传 $(basename "$paper"): ${submit:0:300}"; else pass "上传 $(basename "$paper") → task $task"; fi
    TASKS+=("$task")
  done
  deadline=$(( $(date +%s) + TIMEOUT_MIN * 60 ))
  for i in "${!RUNS[@]}"; do
    TASK="${TASKS[$i]}"
    [ -n "$TASK" ] || continue
    IFS='|' read -r paper expected mode <<<"${RUNS[$i]}"
    echo "-- $(basename "$paper")（$mode）"
    RESULT="$(mktemp)"
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
      check_result "$RESULT" "$expected" "$mode" || FAILS=$((FAILS + 1))
      # 本次分析在现网 score_prediction 留的那条记录：删掉并核实（分析流程只写这一张表）
      PRED_ID="$(python3 -c 'import json,sys; print((json.load(open(sys.argv[1]))["result"].get("score_prediction") or {}).get("prediction_id") or "")' "$RESULT" 2>/dev/null)"
      PSQL="docker exec biology_postgres psql -U biology -d biology_edu -Atc"
      if ! [[ "$PRED_ID" =~ ^[0-9]+$ ]]; then
        fail "测试记录 id 取不到（${PRED_ID:-空}），没删"
      elif [ "$KEEP_RECORD" = 1 ]; then
        echo "INFO  测试记录 id=$PRED_ID 按 --keep-record 留着"
      else
        left="$(timeout 30 ssh "$SSH_HOST" "$PSQL 'delete from score_prediction where id=$PRED_ID' >/dev/null && $PSQL 'select count(*) from score_prediction where id=$PRED_ID'" 2>&1)"
        if [ "$left" = 0 ]; then pass "测试记录 id=$PRED_ID 已删"; else fail "测试记录 id=$PRED_ID 没删掉: $left"; fi
      fi
    fi
    rm -f "$RESULT"
  done
fi

echo "== $([ "$FAILS" = 0 ] && echo '全部 PASS' || echo "FAIL $FAILS 处")"
[ "$FAILS" = 0 ]
