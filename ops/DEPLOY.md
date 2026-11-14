# 从仓部署（河源 ECS）

main = 现网在跑的代码。以后改动走 PR 合 main，再从 main 部署；部署后跑两条对账命令。

## 现网

- 目录：`/home/ops/projects/biology-exam-analyzer`（`ssh ecs`，用户 ops）
- compose 项目名 **`biology`**（不是目录名）：所有 `docker compose` 命令都要带 `-p biology`，否则会另起一个项目，和固定的 `container_name` 撞名。
- 容器：`biology_frontend`（`0.0.0.0:3001`，专家入口）、`biology_backend`（`127.0.0.1:8001`）、`biology_postgres`（`127.0.0.1:15433`，ECS 的 5432 已被占用）
- 后端代码是 `./backend:/app` 挂载：只改 `.py` / prompt 时重启即可，不用重建镜像。前端是 build 进镜像的：改了就要重建。
- 不进仓、只在现网的：`.env`（全部密钥）、`.credentials/`、`uploads/`、`logs/`、`reports/`、`backend/data/runtime.sqlite`（登录 token / 会话 / 任务）。

## 对账命令（本机跑，只读现网）

```bash
bash ops/diff-live.sh     # 仓 HEAD = 宿主目录 = 后端容器 /app = 前端容器静态文件，0 差异才算对齐
bash ops/check-live.sh    # 容器 / 健康 / 专家登录 / 样卷全流程，全 PASS 才算可用
```

## 一次性切换：现网目录改成 git 工作树（2026-11-01 已做，#13；留作新机器 / 重做时参考）

不动文件、不停容器，只是给现有目录补上 `.git`：

```bash
ssh ecs
cd /home/ops/projects/biology-exam-analyzer
cp -a . ../biology-exam-analyzer.bak-$(date +%Y%m%d)   # 先留一份备份
git init -q -b main
git remote add origin https://github.com/juanwan99/biology-exam-analyzer.git
git fetch -q origin main          # GitHub 不通时：本机 git bundle create bea.bundle main，scp 过去后 git fetch bea.bundle main:refs/remotes/origin/main
git reset -q origin/main          # 只设索引，不改工作区文件
git status --short                # 只应出现 D（仓里比现网新的文件，如 ops/ 下新增的）；出现 M 或 ?? 就停下，先查原因
git checkout -- .                 # 确认只有 D 后再补齐
```

（2026-10-18 用现网目录副本模拟过：`git reset` 后只有 `ops/check-live.sh`、`ops/fixtures/*` 4 个 D，没有 M 或 ??。）

切完在本机跑 `bash ops/diff-live.sh`，确认仍是 0 差异。2026-11-01 实做：`git reset` 后只有 ops/ 下 6 个 D，没有 M 或 ??；切前备份 `/home/ops/backup-bea-pre-gitwt-20261101.tgz`（容器里 root 写的 `__pycache__` 读不到，未进备份，不影响）。撤回：删掉现网目录下的 `.git`。

`diff-live.sh` 里的「宿主 git」一项核对现网 HEAD = 仓 HEAD、工作区干净。

## 日常发版（切换之后）

```bash
ssh ecs
cd /home/ops/projects/biology-exam-analyzer
git pull --ff-only origin main
docker compose -p biology restart backend                # 只改了后端 .py / prompt
docker compose -p biology up -d --build backend          # 改了 requirements.txt 或 backend/Dockerfile
docker compose -p biology up -d --build frontend         # 改了 frontend/
```

- `up -d backend`（含 `--build`、改了 compose env）后后端容器 IP 会变，前端 nginx 还连着旧 IP，登录、上传全 502：必须接着 `docker compose -p biology restart frontend`。
- 重启后等半分钟（后端 `start_period` 30 s），健康过了 starting 再验收，不然「容器 biology_backend」报 FAIL；补跑 `bash ops/check-live.sh --no-analyze` 即可。
- ECS 上 `git pull` 偶尔报 HTTP2 framing 后挂住：别等，kill 掉改用 bundle——本机 `git fetch origin && git bundle create bea.bundle origin/main` → `scp bea.bundle ecs:/home/ops/` → 现网 `git fetch /home/ops/bea.bundle refs/remotes/origin/main:refs/remotes/origin/main && git merge --ff-only origin/main`，用完删 bundle（不上传别处）。
- 换 deepseek key：现网 `.env` 只改 key → `up -d backend` → `restart frontend` → `bash ops/daily.sh`，看「deepseek /models」是 200。

发完在本机跑 `bash ops/diff-live.sh && bash ops/check-live.sh`。这就是发版门（冒烟 + 对账，≤5 分钟；check-live 样卷实测 39–155 s）。

## 卡验收与每日整跑（不进发版门）

正本 §1（agent-policy#237）：卡的验收脚本照旧进仓，关单时本窗跑一次、每天整跑一次，不放进上面的发版门。

```bash
bash ops/daily.sh   # check-live 全流程 + 现网 HEAD 全量单测（一次性容器）+ 24 h ERROR / 现网文字链 / deepseek key 状态
```

单测在河源 `biology-backend` 镜像的一次性容器里跑（`git archive` 进容器、`--network none`），本机不需要 venv。

真卷回归：卷子放 ECS 非仓目录 `/home/ops/bea-work7/`（真卷不进仓）：PDF `mock2026.pdf`（#7）、Word `word06.docx`（#35，原件 `/home/ops/var/dst/06_生物_试题.docx`）。每天 `ops/daily.sh` 自动跑（#27）；手动在一次性容器里跑：

```bash
docker run --rm --entrypoint "" -e BEA_PDF_MOCK2026=/w/mock2026.pdf -e BEA_WORD_BIO06=/w/word06.docx \
  -v <代码目录>/backend:/app -v /home/ops/bea-work7:/w -w /app biology-backend \
  python -m pytest -q tests/test_pdf_splitter.py tests/test_word_splitter.py
```

本机 venv `/home/liang/.cache/bea-venv` 11-01 被平台清盘挪到 ECS `/data/office-archive/bea-20261101/`，找回：`ssh ecs 'cat /data/office-archive/bea-20261101/bea-venv.tar' | tar -xf - -C /home/liang`，或按 `backend/requirements.txt` 重建。

## stage（发河源前先在临时容器跑通）

1. `git archive HEAD backend prompts` 解到 `/home/ops/stage-bea/app`，复制现网 `backend/data`；env 只取 compose 传给后端的那几项，写 `stage.env`。
2. 建网络 `biology_stage_net`，起 `biology_postgres_stage`（`pg_dump` 现网库导入）和 `biology_backend_stage`（`127.0.0.1:8011`，挂 stage 目录）。
3. 本机 `ssh -N -L 18011:127.0.0.1:8011 ecs`，跑 `BEA_BASE=http://127.0.0.1:18011 bash ops/check-live.sh --keep-record`。**必须带 `--keep-record`**，不然它按 stage 的记录号去删现网库。stage 只起后端，「前端」一项必 FAIL；「容器」和「后端 /health」两项写死查的是现网，stage 健不健康要另看 `ssh ecs 'curl -s 127.0.0.1:8011/health'` 和 `docker inspect -f '{{.State.Health.Status}}' biology_backend_stage`。
4. 拆：`docker rm -f -v biology_backend_stage biology_postgres_stage`（pg 带 `-v` 删卷）、`docker network rm biology_stage_net`；目录里有 root 写的文件，用 `docker run --rm --entrypoint "" -v /home/ops:/h biology-backend rm -rf /h/stage-bea`（不清 entrypoint 会先联网 pip install，失败就删不成）。本机隧道用 `pgrep` 找 ssh 的 pid 再 kill，别用 `pkill -f <端口串>`（会连本条命令的 shell 一起杀）。

容器日志时间戳比本机快 15 h。

## 现网备份（ECS `/home/ops/`）

- `backup-bea-score-prediction-pre17-20261111.sql`：#17 清空前的 score_prediction 全表（16 行验收测试记录）；恢复 `docker exec -i biology_postgres psql -U biology -d biology_edu < 该文件`。
- `backup-bea-env-pre19-20261111-1514`：#19 删千问开关前的 `.env`。
- `backup-bea-pre-gitwt-20261101.tgz`：改 git 工作树前的现网目录。
- `backup-bea-db-pre-delete-20261018-2026.dump`、`backup-bea-pre6-20261018-2012.tgz`、`backup-bea-pre9-20261018-2313.tgz`：试用前的库和目录。

## 全新机器部署

```bash
git clone https://github.com/juanwan99/biology-exam-analyzer.git && cd biology-exam-analyzer
cp .env.example .env    # 按现网 .env 填密钥（不要提交）
docker compose -p biology up -d --build
```

`database/init/` 只在 postgres 数据卷为空时执行。迁移现网数据要另行导出导入 `biology_postgres` 的库。
