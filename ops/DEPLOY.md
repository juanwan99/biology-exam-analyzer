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

发完在本机跑 `bash ops/diff-live.sh && bash ops/check-live.sh`。这就是发版门（冒烟 + 对账，≤5 分钟；check-live 样卷实测 39–155 s）。

## 卡验收与每日整跑（不进发版门）

正本 §1（agent-policy#237）：卡的验收脚本照旧进仓，关单时本窗跑一次、每天整跑一次，不放进上面的发版门。

```bash
bash ops/daily.sh   # check-live 全流程 + 现网 HEAD 全量单测（一次性容器）+ 24 h ERROR / 现网文字链 / deepseek key 状态
```

单测在河源 `biology-backend` 镜像的一次性容器里跑（`git archive` 进容器、`--network none`），本机不需要 venv。

## 全新机器部署

```bash
git clone https://github.com/juanwan99/biology-exam-analyzer.git && cd biology-exam-analyzer
cp .env.example .env    # 按现网 .env 填密钥（不要提交）
docker compose -p biology up -d --build
```

`database/init/` 只在 postgres 数据卷为空时执行。迁移现网数据要另行导出导入 `biology_postgres` 的库。
