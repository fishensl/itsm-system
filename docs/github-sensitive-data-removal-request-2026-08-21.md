# GitHub Sensitive Data Removal 请求材料（2026-08-21）

> 此文件不包含密钥内容，仅用于项目负责人向 GitHub Support 提交平台侧垃圾回收申请。

## Repository

- Repository: `fishensl/itsm-system`
- Sensitive path: `.secret.key.bak.20260719_165843`
- Old blob SHA: `b6d605f5f2d66ee4c65c022f8c5239cbf6c11e20`
- First affected commit: `2f2a0e358f88445d447cefba2a91604d78be99f0`
- Rewritten first commit: `dcdced6436ee180ab63147a46436f1aaf97cb160`
- Old `master`: `41e273010ca6ae0e1ce6278569a1af3cce7e83fd`
- Rewritten `master`: `48db11980f7d2421cdefabd94a85b29c831abb5a`
- Pull request refs found before rewrite: none

## Completed remediation

1. Used `git-filter-repo` to remove the path from all local branches and tags.
2. Force-pushed `master` and four release tags.
3. Verified final tree hash remained unchanged.
4. Verified rewritten bundle and production repository have zero path hits and cannot resolve the old blob locally.
5. Rotated the production Fernet master key and re-encrypted all current ciphertext values.
6. Expired reflogs and pruned old objects in local and production repositories.

## Remaining platform issue

After the force push, a clean probe repository could still fetch the old blob directly by SHA:

```bash
git fetch --no-tags --depth=1 origin b6d605f5f2d66ee4c65c022f8c5239cbf6c11e20
```

Please purge cached views and dangling objects associated with the removed sensitive path/blob, and run repository garbage collection as appropriate. Please also confirm whether any hidden refs or forks retain the object and advise on their cleanup.
