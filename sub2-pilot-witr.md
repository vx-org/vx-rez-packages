把 `vx-org/witr` 试点迁移到自带 `build.py` + `rez build` 构建，并验证产物与现有 CI 输出等价。

## 背景

可行性 spike（见 `vx-rez-packages` 的 `docs/spike-rez-build-feasibility.md`、`docs/build-py-contract.md`）确认 `rez build` 0.3.10 能复现 VX 已发布布局。选 witr 而非 python 做试点：6 个 target，payload 是 Windows 上的 `zip` 与其他平台的裸 `binary`，不触发「`binary_archive` 不支持 `tar.zst`」这条缺口；python 3.7.9 的 `tar.zst` payload 会正面撞上它，留作第二个。

## 范围

1. `vx-org/witr` 的 `package.py` 增加 `build_system = "build.py"`，同步更新 `recipe.json` 里的 `package.definition.sha256`（pin 覆盖新字节）。
2. 在包根目录写 `build.py`：按 `VX_BUILD_TRIPLE` 选 target，下载并校验 sha256，解包，按 `payload.mappings` 落到 `$REZ_BUILD_INSTALL_PATH/payload`。
   注意三条已实测的行为：脚本在 `%TEMP%/rez-core-build-cache/...` 的临时副本里执行（相对路径取不到 `recipe.json`，用 `VX_BUILD_RECIPE` 绝对路径）；子进程环境被清空且 **没有 `PATH`**（要 shell out 必须补）；`REZ_BUILD_TARGET_PLATFORM/_ARCH/_OS` 不会被设置，默认是宿主。
3. `.github/workflows/packages.yml` 的构建步骤从 `tools.build_bundle` 切到新包装器，更新 `tooling-ref`。

## 约束

- 不改动已发布的 bundle 格式；`runtime-release.yml` 的 matrix、native smoke、index、publish、public-consumer 保持不动，只换一个构建步骤。
- 只用 Monica 分配的 task 分支。
- 公开 PR 标题与描述用英文。
- 提交使用 loonghao / hal.long@outlook.com。

## 验收

- 6 个 target 全部构建成功，产物布局为 `witr/0.3.4/platform-<p>/arch-<a>/payload/bin/witr[.exe]`。
- `tools/verify_consumer.py` 与 `tools/cache_bundle.py` 对试点产物**不改一行**即通过（零 symlink、`payload` 命名、`package_root`、checksum 覆盖这些不变量不可妥协）。
- 与上一个已发布 release 的同 recipe 产物做内容与校验和比对，差异必须逐条可解释。
- 记录第二个包照文档迁移实际花了多久，验证「30 分钟内」这个目标。
