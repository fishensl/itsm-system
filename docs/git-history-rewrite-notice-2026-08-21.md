# Git 历史改写通知（2026-08-21）

## 影响

仓库曾跟踪 `.secret.key.bak.20260719_165843`。该文件已从所有分支和发布标签的历史中移除，`master` 已强制更新；2026-08-21 之前的相关 commit SHA 不再是远端有效历史。

主要映射：

| 改写前 | 改写后 | 说明 |
|---|---|---|
| `2f2a0e3` | `dcdced6` | 首个受影响提交 |
| `507c2fd` | `af5ab27` | P0/P1 代码修复 |
| `30a040e` | `8f38dcb` | P1 加固 |
| `c2a73bf` | `d6b656a` | scope 发布闸门 |
| `8c0c4cf` | `fab8250` | P2/P3 收敛 |
| `c54dfd9` | `6825f47` | P2 契约收敛 |
| `c5f763f` | `c335034` | 设备字段统一 |
| `41e2730` | `48db119` | G3 记录，改写后的初始远端 HEAD |
| `ece64de` | 已剪枝 | 删除密钥文件的提交在移除完整文件历史后变为空提交 |

## 协作者操作

推荐重新克隆，不要把旧历史 merge、rebase 或 push 回远端：

```bash
git clone https://github.com/fishensl/itsm-system.git itsm-system-clean
cd itsm-system-clean
git rev-list --objects --all | grep '.secret.key.bak.20260719_165843'
```

最后一条命令应无输出。旧克隆中的未提交工作须先以补丁或独立文件导出，再人工移植到新克隆；不要从旧克隆推送任何分支或标签。

## 当前安全状态

- 生产主密钥已轮换，旧 blob 无法解密当前密文。
- 本地、生产仓库和重写 bundle 验证均为泄露路径 0 命中、旧 blob 不可解析。
- GitHub 平台仍允许按已知 SHA 获取悬空 blob，已准备 Support 清理申请；在平台确认前不得把 G1 标记为完全物理清除。
