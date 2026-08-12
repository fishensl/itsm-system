# 身份与认证安全指南

## 上线顺序

1. 先部署数据库迁移和代码，保持 `ITSM_MFA_ENFORCE=0`、后台“高风险操作码”关闭。
2. 用户进入 `/app/mfa`，使用腾讯身份验证器分别绑定登录验证和操作验证，并离线保存 8 个恢复码。
3. 管理员在 `/app/system/security` 检查绑定覆盖率，先小范围开启操作码，再开启强制登录 MFA。
4. 生产启用 `ITSM_FORCE_HTTPS=1`；确认页面无 CSP 违规后可启用 `ITSM_CSP_ENABLED=1`。

所有强制能力默认关闭；关闭时原登录和业务接口语义保持不变。

## 离职 SOP

在“用户与部门”中执行“离职清理”。系统将停用账号、递增 `auth_version` 使现有会话失效，清除登录 MFA、操作 MFA、恢复码及锁定状态，并按配置调用外部 URL/命令钩子。

离职清理不会删除用户行，也不会删除、转移或匿名化工单、巡检、报告、草稿、审计等历史业务记录。外部钩子失败只产生告警，访问权限撤销仍然生效。

## 密钥轮换 SOP

1. 同时备份数据库和 `.secret.key`，停止应用写入。
2. 执行 `python scripts/rotate_secret_key.py`，确认所有密文可由旧密钥解密。
3. 执行 `python scripts/rotate_secret_key.py --apply`。
4. 启动应用，验证设备 reveal、通知渠道、AI、导出审核及 MFA。
5. 新旧密钥备份必须与对应数据库版本配套保管。

轮换覆盖设备凭据、密码历史、AI Key、一次性导出密码、用户 MFA/操作种子，以及通知渠道 JSON 内嵌密文。

## 可选主密钥锁定

默认继续使用 `.secret.key`，既有部署行为不变。需要降低磁盘明文主密钥暴露面时：

1. 停止应用写入并完成数据库与 `.secret.key` 的离线备份。
2. 执行 `python scripts/unlock.py --lock`，输入不少于 12 位的管理员主密码。工具使用
   PBKDF2-HMAC-SHA256（480,000 次）派生 KEK，并用 AES-256-GCM 包装主密钥，生成
   `.secret.key.locked` 后删除明文 `.secret.key`。
3. 人工启动前执行 `python scripts/unlock.py --unlock`；无头服务可在受保护的服务环境配置
   `ITSM_AUTO_UNLOCK_KEY`，此时主密钥只解包到进程内存。包装文件存在但无法解锁时，WSGI 拒绝启动。
4. 轮换密钥、生成完整备份包或迁移前先人工解锁，完成后再重新锁定。数据库、包装文件和主密码
   必须分开备份；任一丢失都会导致历史密文不可恢复。

执行 `python scripts/unlock.py --check` 可查看 `locked`、`unlocked` 或 `uninitialized` 状态。

## 传输与会话

- `ITSM_FORCE_HTTPS=1` 后，携带密码/种子/高风险令牌的 HTTP 请求会被拒绝。
- API、导出和上传响应统一使用完整 `no-store/no-cache` 响应头。
- 会话可配置闲置超时与 IP 绑定；改密、重置 MFA、停用和离职都会递增 `auth_version`。
- 操作令牌仅驻留前端内存，默认 120 秒，不写 localStorage/sessionStorage。

## 依赖审计

执行 `bash scripts/audit_deps.sh`。Python 使用 pip-audit，前端使用 npm audit；发现高危漏洞时先验证兼容性，再升级锁文件并跑全量回归。
