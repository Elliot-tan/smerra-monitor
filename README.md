# Smerra 空房云端监测（GitHub Actions）

在 GitHub 的服务器上每 30 分钟检查四个公寓的 Disponible 状态，
一有空房就推送到你的 iPhone（ntfy）。**完全不需要你的电脑开机。**

## 需要准备

- 一个 GitHub 账号
- iPhone 上已订阅 ntfy 话题 `smerra-alert-w4dp9fm4`（已配置好）

## 部署步骤（网页操作，无需安装 git）

### 1. 创建仓库

打开 https://github.com/new

- Repository name：`smerra-monitor`
- 选择 **Private**（私有，推荐）
- 不要勾选任何初始化选项（README / .gitignore 都不要）
- 点 Create repository

### 2. 上传文件

在新建的空仓库页面：

1. 点 **Add file → Create new file**，文件名输入
   `.github/workflows/smerra-monitor.yml`（输入带斜杠的路径会自动创建文件夹），
   把 `smerra-monitor-cloud/.github/workflows/smerra-monitor.yml` 的内容粘贴进去，点 Commit。
2. 再点 **Add file → Create new file**，文件名 `check.py`，
   把 `check.py` 的内容粘贴进去，点 Commit。
3. 同样方式创建 `state.json`，内容粘贴：`{}`

### 3. 添加密钥

仓库页面：**Settings → Secrets and variables → Actions → New repository secret**

- Name：`NTFY_TOPIC`
- Secret：`smerra-alert-w4dp9fm4`
- 点 Add secret

### 4. 手动测试一次

仓库 **Actions** 标签页 → 左侧选中 **Smerra 空房监测** → 点 **Run workflow**。

跑完后展开运行日志，能看到每个公寓的房型和状态；同时手机会收到
"Smerra 云端监测 测试" 或状态日志。

之后每 30 分钟（整点 :00 / :30 左右）自动运行，电脑关不关机都无所谓。

## 注意事项

- GitHub Actions 的定时任务有"尽力而为"的延迟，通常延迟几分钟，
  偶尔可能更久；对半小时一次的监测来说影响不大。
- `state.json` 会被工作流自动提交回仓库，用来记住上次状态、避免重复通知。
- 如果之后想停用本机 launchd 监测，避免两边重复提醒，运行：
  `launchctl bootout gui/$(id -u)/com.tansuchen.smerra-monitor`
- 想换话题名：改仓库密钥 `NTFY_TOPIC` 并在 ntfy App 里重新订阅即可。
