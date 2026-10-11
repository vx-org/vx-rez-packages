向 `vx-org/rez-next` 上游提交可行性 spike 发现的缺口，并记录结论。

## 背景

`vx-rez-packages` 的 `docs/spike-rez-build-feasibility.md`（PR #13）记录了 10 条缺口（G1–G10）。其中一部分属于 rez-next 上游职责，应先提 issue；只有在上游明确不接或排期过远时，才在本仓做补偿层。

## 需要提的上游 issue

| 编号 | 缺口 | 期望 |
| --- | --- | --- |
| G1 | PyPI wheel 的构建 API 是空壳：`rez_next.build_.build_package()` 返回 success 但安装目录为空；`get_buildsys_types()` 返回 `[]`；`python -m rez_next` 只有 banner，CLI dispatch 抛 `NotImplementedError` | 要么补足，要么在文档里明确「构建只能走 Rust 二进制」 |
| G2 | `binary_archive` / `extract_archive()` 只支持 zip / whl / tar.gz / tgz | 增加 zstd（`.tar.zst`） |
| G4 | `REZ_BUILD_TARGET_PLATFORM` / `_ARCH` / `_OS` 被 `build_plugins.py` 读取，但没有任何 Rust 代码设置它们，静默回退到宿主 | 由构建路径设置，或文档说明必须由调用方注入 |
| G5 | 普通 `BuildManager` 路径不复制 `package.py`，只有 release 路径会 | 明确约定，或让 build 路径也复制 |
| G8 | `create_build_system("custom")` 退化为 `Custom("default")`（copy-only），脚本静默不执行 | 至少给出警告 |
| G10 | 宿主 arch 报 `amd64`，与 `arch-x86_64` 包族不一致 | 明确 arch 词表映射 |

## 范围

- 在 `vx-org/rez-next` 提 issue（每条一个，或按主题合并），链接回本组织的 spike 文档。
- 公开英文撰写，不写 Monica 内部单号、内部路径与 agent 路由信息。
- 本仓记录：issue 链接、上游答复、以及「上游修 / 本仓补」的判定。

## 验收

- 每条缺口都有上游 issue 链接，或一条明确的「不在上游做」结论与理由。
- 结论回写到父单评论，并据此更新 `docs/spike-rez-build-feasibility.md` 的 gap 表。

## 约束

- 不在 PR/commit/issue 正文里加任何自动化署名或推广文本。
- 不用上游仓库的 main 分支；提 issue 即可，不自行提交代码改动。
