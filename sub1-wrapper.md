在 `vx-rez-packages` 内落地 `vx build` 包装器，并把现有 `tools/build_bundle.py` 的确定性打包阶段抽成独立可复用步骤。

## 背景

可行性 spike 已确认：`rez build`（rez-next 0.3.10 的 Rust 二进制）能原生复现 VX 已发布的 bundle 仓库布局，spike 包产物为
`<prefix>/spike/0.0.1/platform-windows/arch-x86_64/payload/bin/spike.txt`。

证据与设计见 `docs/spike-rez-build-feasibility.md` 与 `docs/build-py-contract.md`（PR #13，待合并）。本单按其中「第三节 工具仓落地」执行，**但先落在 vx-rez-packages 内**，不新建仓库 —— 现有 `tooling-ref` 引脚已经给下游消费者不可变引用，等命名定下来再抽成独立仓。

## 范围

1. **新增 `tools/vx_rez_build/`**：CLI（`--definition` / `--triple` / `--output-dir`）+ 最小 Python API。职责见契约文档「What `vx build` does」八步：
   - 校验 recipe.json（复用现有 validator）
   - 按 triple 选 target，宿主不匹配即失败
   - 经 SDK `installation-plan` 解析变体（布局仍由 SDK 决定）
   - 生成 `platform/<p>/`、`arch/<a>/` 系统包到 bootstrap 仓库并设 `REZ_PACKAGES_PATH`（`rez build` 没有 `--repository` 参数）
   - 按字节复制被 pin 的 `package.py` 到 `<name>/<version>/package.py`
   - 设置环境契约后跑 `rez build <source> --install --prefix <repo> --build-system build.py`
   - 断言 payload 非空
2. **抽出 pack 阶段**：把 `_write_reproducible_tar_zst` 与 `_write_repository_checksums` 从 `build_bundle.py` 提取为可独立调用的打包步骤，供包装器复用。确定性规则不变（PAX tar、按 posix 路径排序、uid/gid=0、mtime=release_date epoch、mode 0755/0644、zstd level 10 threads=0）。
3. **测试**：CLI/API 单测；`build_system = "custom"` 必须被测试拒绝（不是靠 code review）。
4. **README**：说明 `rez` 二进制如何取得，以及当前为提案状态。

## 约束

- 不改动已发布的 bundle 格式（schema-v1 是已发布契约）。
- `build_bundle.py` 现有行为在验证等价前不得删除，两条路径并存。
- 只用 Monica 分配的 task 分支，不推 main 或他人 PR 分支。
- 公开 PR 标题与描述用英文，不写 Monica 内部单号、内部路径与 agent 路由信息。
- 提交使用 loonghao / hal.long@outlook.com。

## 验收

- `tools/vx_rez_build/` 有 CLI + Python API + 测试，CI 绿（ruff format/check、unittest、actionlint）。
- 对同一 recipe.json，新路径与原 `build_bundle.py` 产出的仓库内容（非归档字节）可比对，差异必须可解释。
- `build_system = "custom"` 被测试拒绝。
- README 与 `docs/build-py-contract.md` 一致。
