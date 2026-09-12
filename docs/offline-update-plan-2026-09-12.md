# 本次通知与 UI 改进离线更新方案

日期：2026-09-12。目标为更新现有生产系统，沿用此前提供的 `root@172.16.123.124`、`/home/itsm-system_20260614`。本轮未连接服务器，路径和环境需现场核对。

## 交付状态与发布前提

当前工作区存在已修改及未跟踪的新功能文件，尚未形成发布提交。本方案不代表离线包已生成，也不代表已推送或部署。此前 `4b8ceb0` 离线包不包含本轮修改，不能用于本次更新。

先整理本轮通知、UI、迁移、测试和文档为可审阅提交，确保新模块全部纳入 Git；不要把临时开发启动脚本、运行数据、密钥或无关文件一并提交。通过发布检查后，从该 master 提交的干净工作树打包。Git bundle 可以包含尚未推送的本地提交，但必须记录准确的提交号；推送和生产更新是独立步骤。

本次需要同时发布后端、Vue 前端、两项通知迁移，以及 `itsm-notifications` 消费者。仅上传前端不能完成更新。

## 1. 工作机生成同版本包

以下命令在完成发布提交后，于 Windows Git Bash 执行；打包机需要 Node/npm、Python 和构建依赖网络。发布目录须为尚不存在的新目录。

```bash
cd /d/CODE/itsm-system_20260525
release_dir="/d/CODE/itsm-release-$(git rev-parse --short master)"
git worktree add --detach "$release_dir" master
cd "$release_dir"
bash scripts/make-release.sh
git bundle verify backups/itsm-update.bundle
cp scripts/update.sh backups/update-release.sh
sha256sum backups/update-release.sh | awk '{print $1}' > backups/update-release.sh.sha256
cat backups/itsm-release-manifest.txt
```

发布文件：`itsm-update.bundle`、`itsm-update.bundle.sha256`、`vue-dist-manual.zip`、`vue-dist-manual.zip.sha256`、`itsm-release-manifest.txt`、`update-release.sh`、`update-release.sh.sha256`。

单独携带同版本更新脚本，是为了避免服务器仍运行旧更新脚本时漏掉离线依赖策略或通知消费者安装步骤；不要直接覆盖生产仓库里的已跟踪脚本。

## 2. 上传

在本地 PowerShell 中，把路径中的“实际提交号”替换为上一步输出：

```powershell
$pkg = 'D:\CODE\itsm-release-实际提交号\backups'
$key = 'C:\Users\Fishen\.ssh\id_rsa_test'
scp -i $key `
  "$pkg\itsm-update.bundle" `
  "$pkg\itsm-update.bundle.sha256" `
  "$pkg\vue-dist-manual.zip" `
  "$pkg\vue-dist-manual.zip.sha256" `
  "$pkg\itsm-release-manifest.txt" `
  "$pkg\update-release.sh" `
  "$pkg\update-release.sh.sha256" `
  root@172.16.123.124:/home/itsm-system_20260614/backups/
```

## 3. 生产只读预检

在服务器 Bash 中执行，任一步失败先排查，不继续更新：

```bash
set -euo pipefail
app_dir=/home/itsm-system_20260614
cd "$app_dir"
git status --short
test -z "$(git status --porcelain --untracked-files=no)"
test -x venv/bin/python
test -f .env
dpkg -s libcairo2 unzip >/dev/null
test -f static/vendor/drawio/index.html
df -h .
cd backups
for name in itsm-update.bundle vue-dist-manual.zip update-release.sh; do
  expected=$(tr -d '[:space:]' < "$name.sha256")
  actual=$(sha256sum "$name" | awk '{print $1}')
  test "$actual" = "$expected"
done
git -C "$app_dir" bundle verify "$app_dir/backups/itsm-update.bundle"
cat itsm-release-manifest.txt
```

核对生产 master 能快进到发布提交、没有本地分叉及未跟踪文件冲突；不要使用 reset --hard 或自动 stash 掩盖生产修改。磁盘须容纳数据库备份、前端备份及发布包。

还须将发布提交的 `requirements.txt` 与生产已安装依赖核对。在暂存目录放入该 requirements 文件，使用生产虚拟环境执行 `pip install --dry-run --no-index -r <暂存目录>/requirements.txt`（需 pip 支持 dry-run）。不支持时在同环境副本验证。当前打包器不生成 wheelhouse；若缺依赖，必须先在与生产系统、架构及 Python 版本匹配的环境准备 wheelhouse，并验证离线安装。不能使用 Windows wheel 代替 Linux wheel。

更新脚本离线模式使用 `pip --no-index`，但缺少 libcairo2/unzip 时仍会尝试 apt，缺 drawio 时仍会尝试下载。因此预检不满足时，先补齐匹配的离线依赖，再进入窗口；现有五件发布包不是全新系统安装包。

## 4. 维护窗口执行更新

操作人确认维护窗口后，暂停业务访问和写入，停止 Web 与已有通知消费者，避免迁移期间继续产生数据。通知消费者启动后会按已启用配置处理待发队列，更新前应核对客户绑定、全局渠道和待发数量。

```bash
set -euo pipefail
app_dir=/home/itsm-system_20260614
cd "$app_dir"
stamp=$(date +%Y%m%d_%H%M%S)
git rev-parse HEAD > "backups/pre-update-$stamp.commit"
sudo systemctl stop itsm
if systemctl cat itsm-notifications.service >/dev/null 2>&1; then
  sudo systemctl stop itsm-notifications
fi
sudo tar -czf "backups/pre-update-$stamp-frontend.tar.gz" static/app
sudo bash "$app_dir/backups/update-release.sh" "$app_dir"
```

该脚本会先备份数据库及密钥配置，然后应用 bundle、核验提交、部署前端、迁移及同步权限、重启 Web 并检查 readyz，最后安装/重启通知消费者。记录此次输出的 PostgreSQL `.dump` 和同时间戳 `itsm_meta_*.tar.gz`，确认两者可读。失败时保持维护状态，检查日志，不循环重跑或绕过失败步骤。

## 5. 验收后恢复访问

```bash
cd /home/itsm-system_20260614
git rev-parse HEAD
cat backups/itsm-release-manifest.txt
sudo systemctl --no-pager --full status itsm itsm-notifications
sudo journalctl -u itsm -u itsm-notifications -n 100 --no-pager
```

- HEAD 与 manifest 的 commit 相同，更新脚本 readyz 通过；`/app/` 正常加载，静态资源无 CSP/sandbox 错误。
- 通知中心消费者心跳更新，无迁移或权限错误。不要通过真实客户群试发来验证部署；经授权的测试群单独验收。
- 新巡检开始通知没有结束/累计字段；完成通知按计划时间、地点、工程师、状态、开始、结束、耗时、人天排序。
- 故障主题完整，显示处置字段；计划时间使用已记录的计划到场时间。
- 客户消息没有内部审核意见；内部全局通知保留审核通过；历史事件不重写、不补发。
- 外网模板下载不需要操作 MFA；敏感报告/配置下载及密码查看保持原有 MFA、权限与审计边界。
- 1080p 桌面与手机端关键列表、筛选、弹窗正常。恢复访问前清理浏览器旧缓存或强制刷新。

## 6. 回滚条件与顺序

出现启动/迁移失败、关键流程不可用或通知误投时，停止 Web 和消费者并保留日志。数据库恢复会丢失备份后的写入，因此全程保持维护状态。已发送到外部平台的消息无法由数据库回滚撤回，不自动重放未知结果或恢复后的队列。

`rollback.sh` 只恢复数据库与密钥配置，不能单独完成版本回滚。先在仓库外保留新版本 rollback 脚本，再将代码切回记录的 pre-update 提交，恢复同窗口的前端归档，然后使用该 rollback 脚本恢复明确选定的 `.dump` 与配对 meta 包。脚本会重启服务，因此必须在恢复数据库前准备好匹配的旧代码与前端。不得只回退代码而保留不兼容的新 schema，也不要按“最新备份”猜测恢复目标。

回滚后验证 Web 健康、旧功能和数据；通知消费者保持停用，核对旧版本是否支持以及队列是否会重复投递后再决定启用。具体恢复提交、备份文件和覆盖操作应由现场操作人核对确认。
