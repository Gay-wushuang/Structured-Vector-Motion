# SVM C 板块 · 视频修复五线分派

| 项目 | 内容 |
| --- | --- |
| 版本 | `c-video-repair-contract@0.1`，草案修订 `R1-002` |
| 状态 | **DRAFT**，交策划线 G1 审核。 |
| 适用范围 | C 板块 Core 外实验及 G0–G3 的分派。SVM 长期首要目标仍为 Motion 动画编辑。 |
| 已验证事实 | 初始文档分支 `agent/c-docs-r1` 为 `5561d8b59fb1d3ebd5544bacde88f387d3902100`。实践原型位于 `agent/c-impl-r1` 的 `b310f57e6a21562798f5ccad2a1897ba4d99c47e`。 |
| 待实现能力 | 按下列门禁完成正式 CLI、独立验收与 SVM Motion 演示。 |
| 未决问题 | 见本页 [G1 待决问题](#g1-待决问题)。 |

仓库为 [Hesperr233/Structured-Vector-Motion](https://github.com/Hesperr233/Structured-Vector-Motion)。各线在独立 worktree/克隆核对实际分支、SHA、工作区状态。旧基线 `cf4815357909f4e462f26619d33e6bfcb1e16236` 仅供追踪。提交前核对真实上游，保留现有成果。集成时记录契约文档、实施和 CI 的各自 SHA。

## 范围与契约来源

[需求](../c-video-repair/requirements-v0.1.md)定义 A 固定 CI 合成素材（2 秒、24 帧、12/1 fps、256 × 256 RGB8 PNG）与 B 正式 SVM Motion 演示（真实 Document、5–10 秒、`MotionEvaluator`、FINAL 且当前、`SVGRenderer`、外部光栅化的连续 RGB8 帧）。两个里程碑分别提供证据。B 优先 12 fps、256 × 256，源场景需要其他规格时评审等比画布和整数采样方案。目标包括局部修复、闪烁抑制、拖影改善、外观稳定，以及视频导出和同步前后比较。

[管线契约](../c-video-repair/pipeline-contract-v0.1.md)统一 CLI、输入、掩膜、输出与状态。[验收标准](../c-video-repair/acceptance-criteria-v0.1.md)是公式、阈值与测试口径的单一来源。[接入边界](../c-video-repair/integration-boundary.md)定义外部处理与 SVM 的权限边界。契约只维护在 `docs/c-video-repair/`。实践原型源见 [b310f57 的 prototype/video_restoration](https://github.com/Hesperr233/Structured-Vector-Motion/tree/b310f57e6a21562798f5ccad2a1897ba4d99c47e/prototype/video_restoration)。

## 工作线与执行顺序

以下为分派配置。执行者在实际客户端核对模型及档位，无法核实时披露可见信息，未经协调不得静默替换。

| 线路 | 平台 | 模型 | 推理强度 | 分支与文件责任 |
| --- | --- | --- | --- | --- |
| 策划 | Codex Windows 桌面版 | GPT-6 | High | C 板块范围、G1 冻结、争议及 G3 签收。 |
| 文档 | Codex Windows 桌面版 | GPT-6 | High | `agent/c-docs-r1`，本页及 `docs/c-video-repair/` 四份契约。 |
| 实践 | Codex Windows 桌面版 | GPT-6.1 Sol | Extra High | `agent/c-impl-r1`，外部原型、正式 CLI、样例和导出工具。 |
| CI 测试 | Codex Windows 桌面版 | GPT-6.1 Sol | High | 策划线登记独立分支，以实际 SHA 为准。独立 fixture 验证、评分、测试和 workflow。 |
| 审查 | Codex Windows 桌面版 | GPT-6 Astra | Extra High | `agent/c-review-r1`，独立核阅边界、实际媒体和签收证据。 |

| 门禁 | 可并行工作 | 进入下一阶段的条件 |
| --- | --- | --- |
| G0 · 调研和草案 | 文档消除冲突，实践验证开发样例，CI 设计独立测试，审查排查权限、媒体和质量风险。 | 同版草案和各线意见交策划线。 |
| G1 · 冻结 | 实践验证开发环境和样例，CI 核查公式与媒体容差，审查核对观察证据与来源。 | 策划线明示批准并记录契约版本/文档 SHA、阈值、正式采样配置及封存的留出数据。G1 前均为 DRAFT。 |
| G2 · 集成 | 实践接通正式链路，CI 在同一契约上独立实现测试和评分，两线按实施 SHA 对接。 | 有同 SHA 的媒体、验收报告、CI 和重复性证据，缺陷交对应所有者修复。 |
| G3 · 签收 | 审查同一候选，策划线核收两套证据与阻塞。 | 成套文件、指标、护栏、Core 非回归与独立审查均齐备。候选变化后重跑受影响的检查。 |

## 实践线接口交接单

1. 在 Core 外实现 `ingest → repair → export`，接通 `evaluate`、`verify` 的外部入口和版本校验。独立 oracle、正式评分与 verify 验收逻辑由 CI 线维护。现有 `synthetic`、`demo` 和原型 `evaluate` 保留兼容行为，正式接口使用新的文件格式和输出目录。
2. 保留可追回的原始源及退化快照。repair 仅接收退化 PNG、帧时间、显式掩膜和配置。公开掩膜的来源、写入授权、供体可靠性及保护域。可靠邻帧不足须原样保留并标 `UNRESOLVED`。
3. 交付 A 开发样例及 B Motion 演示来源配置。B 记录 Document/Revision、逐帧 tick、FINAL 当前状态、SVG/PNG 哈希及固定光栅化工具。干净参考和退化真值交离线评测侧。
4. 分阶段提交状态和摘要。交付 `before.mp4`、`after.mp4`、`comparison.mp4`、前后无损 PNG、`run-manifest.json` 和复现命令。将实际依赖、实施 SHA、工具版本和未完成项交 CI；不能将原型 `partial` 或媒体 `verified` 写成验收通过。

## CI 线测试交接单

1. 保留 Ubuntu/Windows × Python 3.11/3.12 的现有质量矩阵。独立视频 job 至少使用一个固定工具环境，执行真实编码、完整解码和证据上传。缺工具阻塞正式验收。
2. 实施侧用 A 开发数据校准，正式修复进程只获得 H1–H5 的退化输入、许可掩膜和配置。封存 H1–H5 的 seed、SHA、参考/评分掩膜与门槛后再开始正式验收。CI 独立计算 M1–M4、空间与运动护栏，输出 `metrics.json`、`acceptance-report.json`，保留首轮失败证据。
3. 覆盖反相闪烁、目标穿越供体、持续遮损、无退化、首尾帧、重复画面、无效帧包、掩膜/摘要错误、引用越界、源只读、移走参考、滞留文件和工具中途失败。缺失或失败结果不得发布 `SUCCESS`。
4. 核验三路 PTS 及对应的左右解码内容。加入交换对照右半两帧但保持原 PTS、色条/暗阶与音频处理的反例。B 独立校验源 Document、FINAL 非 stale、光栅化记录及完整运行。
5. 对同一候选 SHA 运行 unittest、Ruff format/lint、Pyright、compileall 和实际媒体 job。报告所测实施 SHA、CI SHA、契约版本/修订、工作流链接及通过、失败、跳过、未运行的明细。

审查线查阅 AGENTS.md、README.md、[系统边界](../../spec/05-system-boundaries.md)、[Motion 语义](../../spec/21-motion-semantics.md)、[Motion 修订](../../spec/22-motion-revisions.md)、[受控光栅恢复](../../spec/58-explicit-multi-object-raster-recovery.md)，比对边界 diff、原片/真值隔离、源质量和候选 SHA，实看三路媒体与报告。使用 PASS / CHANGES_REQUIRED / BLOCKED 报告证据和阻断，不自行合并 main。

## G1 待决问题

| 议题 | 草案决定或待验证 |
| --- | --- |
| 演示来源 | 选择确切的 Document/Revision、连续 tick、画布与外部光栅化工具。对 256 方形缩放做边缘/掩膜可见性检查，必要时提交等比方案。 |
| S4/H4 和合成掩膜 | 先在开发集验证漂移可由许可静态样本观测、固定 G 不与目标轨迹重合、供体语义可独立构造。冻结留出 manifest 与保真检查规则。 |
| 工具与媒体 | 确定跨平台 PNG 测试环境、至少一个固定 FFmpeg/libx264/ffprobe 组合、sRGB 色彩往返与逐帧 MAE/PSNR 试验结果、原片快照位置与保存周期。 |
| 兼容期 | 确定保留原型调用方的期限以及显式迁移工具的归属。 |
| 冻结记录 | 策划线确认公式修订、现有 30% 单项和 20% 组合及空间、运动、媒体门槛。开始留出后禁止下调阈值或重选区域。 |

## 仓库卫生与旧日志

`.c-impl-r1` 与 `.review-r1` 在文档分支原基线为 mode 160000 Gitlink，分别对应实践和审查的本地独立工作目录。该树与本地仓库未发现有效的 `.gitmodules` 配置。二者为工作目录引用，清理只涉及文档分支 Git 树/索引条目，须保留实际目录、各自提交和工作区内容。

**`.review-r1-baseline.log` 是历史测试日志，非有效验收基线。** 没有与本次契约和实施候选绑定，禁止据此报告 C 板块或远端 CI 通过。R1-002 检出工作区和运行时的绝对路径。交付树排除此历史日志，保留本地原件和历史提交。未生成替代日志；正式基线由 CI 线另行运行并以实施和 CI SHA 标识。
