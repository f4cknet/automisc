# AGENTS.md 归档变更日志

> 本文件收录 AGENTS.md 已被后续条目覆盖、不再具有"最近状态"价值的旧版本条目。
> **当前 §8 仅保留最近 4 条**（治理/实施重大节点）；超出范围的旧条目归档到此处。
> 归档规则：当 §8 超过 4 条时，最旧的一条移入本文件并按版本号升序追加。
>
> 归档时点：2026-06-13（per Owner 决策，refactor/clean-changelogs 分支）。

---

## v1.0（2026-06-13）— 初版

初版：4 条铁律 + L1/L2/L3 违规分级 + 紧急通道 + AI Agent 精简条款（3 条核心）+ macOS only 约束（§2.4）+ 治理变更流程。骨架参考 `pwn/autopwn/AGENTS.md v1.7`，按 automisc 特性调整：铁律 4 完成判定改写（不追求 flag 匹配）；文档契约改为 `AGENTS.md` + `prd.md` + `Architecture.md` 三件套（无独立 `upgraded.md`，任务看板合并入 `prd.md §3`）；明确不引入 LLM / 不桥接 skill 体系

---

## v1.1（2026-06-13）— v0.1.0b-PR1 实施完成

**v0.1.0b-PR1 实施完成**（per `prd.md §4.1 v0.1.0b-PR1`）：实现 core/ + tools/shared/ 6 个 adapter + 61 unit tests 100% PASS + 真实样本 smoke 通过 6 关验收。**文档契约首次实战**：任务状态 🔄 → ✅ + `Architecture.md §10` + `tools.md §8` + 本表同步更新；代码与文档严格同 PR 落地

---

## v1.2（2026-06-13）— GitHub 工作流治理变更（v1）

**GitHub 工作流治理变更**（per Owner 2026-06-13 决策）：新增 §2.5（GitHub 工作流强制规范）+ §9（Git 仓库 & 工作流速查）。**关键约束**：（1）远端仓库 `https://github.com/f4cknet/automisc.git`；（2）每个任务必须在 feature 分支实施，PR target = `main`；（3）PR 标题 = `[v{X}.{Y}.{Z}] {动词} {对象}`；（4）PR 描述必须含 6 关验收 checklist；（5）合并方式 = Squash and merge；（6）AI Agent 不持有 GitHub 凭据，`git push` / `gh pr create` / merge 由 Owner 在本地完成。**注**：本条目同步自 `docs/v0.1.0b-add-github-workflow` 分支（commit 9644a53），因为 main 分支此前未包含

---

## v1.3（2026-06-13）— GitHub 工作流强化（v2：硬约束模式）

**GitHub 工作流强化**：§2.5 重写为"AI Agent 硬约束"模式——**AI Agent 只做本地 commit，所有远端写操作 Owner 人工**。理由：AI Agent 不应持有 GitHub 凭据；远端写操作不可逆。§5 同步强化对应行。§9.4 状态同步表新增"commit 由 AI Agent 做 / push 由 Owner 做"明确分工。§9.5 snapshot 更新"本地分支 / 远端 PR"两列。**注**：本条目同步自 `docs/v0.1.0b-add-github-workflow` 分支（commit 9644a53）
