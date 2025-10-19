# 版本控制指南

## 当前版本
- **标签**: v0.1-baseline
- **分支**: master (稳定版本), dev (开发分支)
- **进度**: 45%

## 版本管理策略

### 分支说明
- `master`: 稳定可用的版本，每次重大功能完成后合并
- `dev`: 日常开发分支，测试新功能
- `feature/*`: 功能开发分支（需要时创建）
- `hotfix/*`: 紧急修复分支

### 常用命令

#### 1. 查看当前状态
```bash
cd C:\Users\liang\agent_shenti
git status
git log --oneline --graph --all
```

#### 2. 创建功能分支开发新功能
```bash
# 从dev分支创建新功能分支
git checkout dev
git checkout -b feature/新功能名称

# 开发完成后提交
git add .
git commit -m "feat: 新功能描述"

# 合并回dev分支
git checkout dev
git merge feature/新功能名称
```

#### 3. 回退到之前的版本
```bash
# 查看所有版本
git tag

# 回退到基线版本
git checkout v0.1-baseline

# 恢复到最新版本
git checkout master
```

#### 4. 对比两个版本的差异
```bash
git diff v0.1-baseline master
```

#### 5. 保存当前工作（临时保存）
```bash
# 保存当前未提交的修改
git stash save "临时保存的描述"

# 恢复保存的修改
git stash pop
```

## 提交规范

建议使用以下前缀：
- `feat:` 新功能
- `fix:` 修复bug
- `refactor:` 重构代码
- `docs:` 文档更新
- `style:` 代码格式调整
- `test:` 测试相关
- `chore:` 构建/工具链相关

示例：
```bash
git commit -m "feat: 添加加载进度提示功能"
git commit -m "fix: 修复题目选项丢失问题"
```

## 版本里程碑

### v0.1-baseline (当前)
- ✅ PDF/Word文档解析
- ✅ Gemini API集成
- ✅ 高精度内容提取
- ✅ 前后端分离架构
- ⚠️ 图表渲染待优化

### v0.2 (计划中)
- [ ] 修复题目选项丢失
- [ ] 优化详细分析展示
- [ ] 添加加载进度提示
- [ ] 页面样式美化

### v0.3 (未来)
- [ ] 图表渲染优化
- [ ] 课标映射功能
- [ ] 逻辑检测功能

## 注意事项
1. 每次重大修改前先创建分支或标签
2. 确保master分支始终可运行
3. 定期提交，避免丢失工作成果
4. 使用有意义的提交信息
