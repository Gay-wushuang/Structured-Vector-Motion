# SVM 视频修复 v0：五线任务包

策划日期：2026-11-05。策划线负责范围、接口冻结、冲突裁决与最终收口；本文分派其余四线。
核对基线：`cf4815357909f4e462f26619d33e6bfcb1e16236`。本文件是新里程碑的策划建议，不表示视频修复能力已经实现。

## 共同目标与范围

交付一段 5–10 秒受控短片的局部画面修复、闪烁抑制、拖影改善、外观稳定及渲染导出，提供修复前后同步对照、可播放结果、无损帧和可复现报告。

尚无用户视频素材。本轮先用 SVM 已接受 Document 渲染受控干净序列，再离线生成有记录的退化输入；必须标为合成受控实验。真实视频泛化、自动对象关联、遮挡恢复、神经模型、光流、多相机及通用编辑 UI 不在本轮范围。真实素材测试留作后续独立验收，不能以合成成功代替。

优先采用固定相机、一个运动目标和静态背景，局部遮损/脉冲亮度闪烁/人工拖影/局部外观漂移分别有单项片段，最后再组合。第一轮不要求重新恢复相机或扩展光栅观测支持域。若复用 spec/56–58 的观测恢复，只能在其既有受控输入域内使用，不得把彩色视频或受损图像直接冒充已受支持的证据。

SVM 负责已有 Document、MotionEvaluator 与 SVGRenderer 语义；修复算法、光栅化、解编码和质量分析属于 Core 外实验工具。修复程序只能消费退化帧、显式用户掩膜/ROI、时间信息和版本化配置。干净参考、退化生成参数中的真实运动、ground-truth 和评分结果只允许用于离线样例生成及最终评测，不能成为修复推断输入。显式掩膜可以作为用户输入，但必须披露。

渲染修复成果不等于成果已成为可编辑 SVM Document。默认交付帧序列和媒体文件；若确实提出 Document 修改，必须另走现有 Artifact → Proposal → 注册 Change → 原子 Transaction → Revision 边界，不能直接调用 commit 绕过接受。

## 现状与必读

- 阅读仓库 AGENTS.md；其要求的 Core 语义源文件按变更范围落实，本文不豁免。
- 至少阅读 spec/00、01、05、08、21、22、56、57、58，pyproject.toml 和 .github/workflows/ci.yml。
- 参考 examples/036-controlled-raster-camera-recovery、examples/037-explicit-multi-object-raster-recovery、tests/test_multi_object_raster_recovery.py。
- 参考 demo/004-real-pop-animation/build_demo.py 的已有导出方式；它依赖本机浏览器路径，不可直接当跨平台方案。
- 当前 CI 是 Ubuntu/Windows × Python 3.11/3.12；AGENTS 提及本地 3.12，不应据此缩减既有矩阵。

## 模型与工作区

以下是本轮明确选用的配置，不要求必须混用供应商。Codex 是 Agent 工具，GPT 名称才是底层模型。

| 工作线 | Agent | 具体模型 | 推理强度 | 分支建议 |
| --- | --- | --- | --- | --- |
| 文档 | Codex | GPT-6.1 Sol / gpt-6.1-sol | high | codex/video-repair-docs |
| 实践 | Codex | GPT-6.1 Sol / gpt-6.1-sol | xhigh / Extra High | codex/video-repair-implementation |
| CI 测试 | Codex | GPT-6.1 Sol / gpt-6.1-sol | high | codex/video-repair-ci |
| 审查 | Codex | GPT-6 Astra / gpt-6-astra | xhigh / Extra High | codex/video-repair-review |

在工具的模型选择器中实际设置模型和强度。提示词本身不会切换模型；账号无此配置时先报告可用配置，不得声称已经切换。可改用 DeepSeek 或 TRAE CN 执行同一任务，但要重新明确其实际底层模型完整名称和可用推理档位，不能将平台名或“深度思考”自行等同于 Codex 的 xhigh。

每线使用独立 worktree/克隆，保留现有未提交改动。四线在同一基线开始；集成前显式导入冻结契约和依赖提交，记录实际 SHA。不要在共享工作目录同时切分支。各线只改自己负责的文件；需要跨线改动先给策划线说明，由所有者落地。

## 并行顺序与收口

1. G0，立即并行：文档线起草契约；实践线盘点工具并做最小可行性实验；CI 线记录基线和测试设计；审查线输出架构风险。没有冻结契约前，实践实验不能被宣称为正式完成。
2. G1，契约冻结：文档、实践、CI、审查对齐 CLI、manifest、掩膜、帧范围、指标和阈值，交策划线确认版本。阈值先冻结再运行正式验收；可行性校准用开发样例，不用正式留出样例调参。
3. G2，集成：实践实现正式端到端链路，CI 在相同 implementation SHA 和 contract version 上独立验证。测试失败交回实现者修复，CI 不改门槛遮盖问题。
4. G3，验收：审查线检查同一候选 SHA 的代码、实际媒体、指标和 CI；策划线按阻塞项收口。候选代码变化后，受影响检查及审查必须更新。

正式交付：before.mp4、after.mp4、comparison.mp4、无损输出帧、输入及掩膜清单、运行 manifest、metrics.json、复现说明。MP4 默认 H.264/yuv420p、静音；帧率、分辨率、起止 tick、帧数明确记录。不支持音频或可变帧率时明确拒绝或按文档转换，不能悄悄丢弃。

manifest 至少包含 contract_version、输入帧/掩膜摘要、帧索引与整数 tick 映射、有理数 fps、参数、随机种子、算法与工具版本、质量、输出摘要、退出状态及代码 SHA。身份不依赖绝对路径或时钟；时间戳等执行日志不能进入语义哈希。对 PNG 同时区分文件摘要与规范化解码像素摘要。

## 验收建议，由文档线具体冻结

- 局部修复：在预先固定的受损 ROI 内比较输出与参考的 MAE。
- 闪烁：以逐帧参考误差的时间差分衡量，避免把真实目标运动计成闪烁；需要对齐时只在评分阶段使用参考对齐，并披露边界处理。
- 拖影：预先固定参考轮廓之外的拖尾区域，报告残影能量；区域和采样规则不能看完结果再挑。
- 外观稳定：按参考定义的目标内部区域报告颜色/亮度残差的时间波动，同时报告空间误差，防止模糊刷低指标。
- 初始策划目标：每项独立退化样例的对应主指标相对未修复输入降低至少 30%；组合样例四项都改善。若开发样例证明目标不合理，正式验收前提交依据并重新冻结，不能在留出验收失败后降阈值。
- 未授权区域：无损修复帧在声明的作用域（含显式边界羽化范围）外像素不变；有损 MP4 不适用逐像素相等。
- 防止静止、模糊取巧：在留出样例检查目标运动/轮廓保真，报告空间误差和时间指标；不能仅凭更低帧差宣称修复成功。
- 同一固定工具环境下重复运行，规范化像素/结构性结果满足约定确定性；跨平台光栅化和 MP4 编码使用冻结容差及解码内容检查，不要求未经证明的二进制相等。
- 不允许 stale/PREVIEW 代替 FINAL；无效输入、缺帧、摘要不符、非法掩膜、失败的编码应清晰失败，不能留下看似成功的结果。
- 所有既有 Golden 和全量质量检查通过。未运行、跳过、通过、失败分别报告。

## 提示词 1：文档线（可整段复制）

```text
你是 Structured-Vector-Motion 视频修复 v0 的文档线 Agent。
Agent 工具：Codex。指定模型：GPT-6.1 Sol（gpt-6.1-sol）。推理强度：high。
请在工具中实际设置上述模型/强度；不能设置时报告实际配置，不要伪称提示词已完成切换。

仓库：https://github.com/Gay-wushuang/Structured-Vector-Motion
本地参考：D:\codex\Structured-Vector-Motion；你的独立工作区以实际路径为准。
以 cf4815357909f4e462f26619d33e6bfcb1e16236 为已核对参考，先核对实际 HEAD 和工作树差异。
读取 AGENTS.md、docs/planning/video-repair-v0-dispatch.md，并落实其中共同目标、必读文件、G0–G3 与验收建议。任务包不存在时要求策划线提供全文，不得自行编造已冻结契约。

目标：形成实践和 CI 能共同执行的受控视频修复契约，覆盖局部画面修复、闪烁、拖影、外观稳定、渲染导出。现在缺少用户真实视频，默认使用合成受控片段并明确披露。你负责文档及接口定义，不实现修复算法。

你拥有 docs/video-repair/contract-v0.md、docs/video-repair/reproduce.md、docs/video-repair/acceptance.md。新语义确需进入 spec 时先提出具体变更，避免擅自占用 spec 编号或改写既有规范。

立即执行：
1. 将仓库现有能力、外部实验能力、尚未支持能力分别写明，尤其禁止把 spec/56–58 的受控光栅恢复等同于自然视频修复。
2. 定义 5–10 秒固定相机受控样例的输入域、显式 ROI/掩膜、单项退化和组合退化、开发/留出划分。干净参考只用于生成和评分，不得成为修复推断输入。
3. 与实践、CI 对齐后冻结实验 CLI 子命令、退出码、输出目录、manifest/metrics 字段、帧索引到整数 tick 的映射、有理数 fps 和端点规则。CLI 属于 demo 外部入口，不默认扩展 svm 公共 CLI。
4. 写出四项主指标的公式、单位、ROI、聚合方法、零分母处理和硬阈值；同时写明未授权区域保护、轮廓/运动保真、无退化输入保护。以策划包的 30% 目标为初始提案，正式留出验收之前冻结。
5. 定义 H.264/yuv420p 静音 MP4、同步对照和无损 PNG 交付规范，区分媒体文件摘要、像素摘要和 SVM Immutable Value；写明外部光栅化/编码版本和跨平台容差。
6. 写入完整复现步骤、实际依赖、失败诊断及局限，禁止先写“已通过”。导出链路若涉及 SVM 结果，必须 FINAL 且非 stale。

边界：不改 svm/、schema/、测试、workflow 或算法代码；不引入新 Core 字段，不修改现有支持域和阈值。对 accepted Document 的任何修改必须遵守现有 Proposal/ChangeAuthority 原子接受语义。

交付：契约草案文件、输入输出示例、依赖/未决问题、交给实践与 CI 的接口表。G1 前标记 DRAFT；接口取得策划线确认后记录冻结版本。G2 后用真实运行命令和产物更新复现文档。
汇报必须列出分支、基线/当前 SHA、改动路径、已完成/待完成、实际验证和阻塞。不要越权合并其他线或声称整个里程碑完成。
```

## 提示词 2：实践线（可整段复制）

```text
你是 Structured-Vector-Motion 视频修复 v0 的实践线 Agent。
Agent 工具：Codex。指定模型：GPT-6.1 Sol（gpt-6.1-sol）。推理强度：xhigh（Extra High）。
请在工具中实际设置上述模型/强度；不能设置时报告实际配置，不要伪称提示词已完成切换。

仓库：https://github.com/Gay-wushuang/Structured-Vector-Motion
本地参考：D:\codex\Structured-Vector-Motion；使用独立 worktree，先核对实际 HEAD 和现有改动。
已核对参考 SHA：cf4815357909f4e462f26619d33e6bfcb1e16236。
读取 AGENTS.md、docs/planning/video-repair-v0-dispatch.md 及其中必读资料。任务包缺失时索取全文。

目标：实际做出一段 5–10 秒受控短片的局部修复、闪烁抑制、拖影改善和外观稳定，输出 before.mp4、after.mp4、comparison.mp4、无损修复帧及可复现报告。无真实输入时先交合成受控实验，不宣称自然视频通用修复。

你拥有 demo/005-controlled-video-repair/ 下的实验实现、样例生成脚本和最小素材/预览，不拥有其中由文档线维护的仓库级文档，也不拥有 tests/ 和 .github/。大型帧序列作为构建产物，不直接提交。需要修改 pyproject.toml 或 .gitignore 时提交具体依赖/路径需求给 CI 文件所有者。

G0 立即盘点现有渲染和导出工具，复用 MotionEvaluator → FINAL Evaluated Scene → SVGRenderer；验证已有 demo/004 的本机浏览器方案在你环境中的限制。先做最小实验，向文档线给出可实际执行的 CLI 与依赖建议，不要只写方案。

G1 后按冻结契约实现：
1. 构建固定相机、一个移动目标、静态背景的干净序列；在独立的离线 fixture 步骤注入局部遮损、亮度闪烁、人工拖影和外观漂移，记录种子。把干净参考和退化参数真值隔离在评测输入目录。
2. 修复入口仅接收退化帧、用户显式掩膜/ROI、时间信息和版本化配置。选可解释的最小确定性传统基线；逐项输出消融结果，再组合。避免简单时间平均造成新的拖影。可靠邻帧不足或输入超域时明确拒绝/降为有标记的未修复结果。
3. 输入帧、掩膜和配置做内容摘要校验，记录 fps/整数 tick、边界规则、版本、算法参数和输出摘要。修复路径不能读取 reference、ground-truth 或评分输出；禁止用干净渲染覆盖受损区域冒充修复。
4. 作用域外无损像素保持不变，羽化范围须明确。输出尺寸、帧数、时间戳顺序和色彩规则遵守契约，保持目标轮廓与真实运动。
5. 将光栅化与 FFmpeg/ffprobe 编解码留在 Core 外；采用可配置可检测的工具路径，不硬编码个人 Windows 安装目录。捕获失败、非零退出码和未完成产物；不得把失败残片标记成功。
6. 生成同步并排对照、修复后视频、代表性帧与 metrics/manifest。规范化像素和结构性结果用于确定性检查，不擅自要求不同平台 MP4 字节一致。

边界：默认不改 svm/、schema/ 或既有 spec。不要添加模型权重、光流系统、自动关联、GUI 或扩大既有光栅恢复支持域。不要把帧级修复自动宣称为可编辑 SVM Document；若确需写 accepted Document，先把必要性和最小 Proposal/注册 Change 方案交策划线。无 Core 语义变更就不造新的 Adapter 或 Revision 子系统。

与 CI 共享正式 CLI 和小型确定性 fixture，不调用 CI 的评分结果来决定输出。修复实现问题由你负责更正，禁止修改 CI 的验收阈值。运行全量 unittest、Ruff 格式检查/lint、Pyright，必要时 compileall；测试由 CI 线拥有，提出行为测试需求而不竞争编辑。

交付必须有实际命令、实际输出路径、环境/工具版本、四项指标前后值、运行日志、已知失败及样例局限。无工具导致不能编码时可先交无损帧并清楚标记阻塞；仍不得宣布本任务完成，需跟进到可播放导出验证。
汇报分支、基线/当前 SHA、改动路径、契约版本和所需依赖提交，交 CI 与审查按同一 SHA 复核。
```

## 提示词 3：CI 测试线（可整段复制）

```text
你是 Structured-Vector-Motion 视频修复 v0 的 CI 测试线 Agent。
Agent 工具：Codex。指定模型：GPT-6.1 Sol（gpt-6.1-sol）。推理强度：high。
请在工具中实际设置上述模型/强度；不能设置时报告实际配置，不要伪称提示词已完成切换。

仓库：https://github.com/Gay-wushuang/Structured-Vector-Motion
本地参考：D:\codex\Structured-Vector-Motion；在独立 worktree 先检查 HEAD、工作树与 CI 基线。
已核对参考 SHA：cf4815357909f4e462f26619d33e6bfcb1e16236。
读取 AGENTS.md、docs/planning/video-repair-v0-dispatch.md、其中必读资料和文档线契约。任务包缺失时索取全文；G1 前先做基线与测试设计，不自行发明正式门槛。

目标：独立证明四项修复改善、非目标保护、可复现导出及既有 SVM 不回归。不要只证明进程返回 0 或输出文件存在。

你拥有 tests/test_video_repair_*.py、测试专用 fixture/评分辅助代码，以及 .github/workflows/ 下视频测试配置。pyproject.toml/.gitignore 的必要改动由你统一落地，保持最小且与实践线对齐。不要编辑实践算法或文档线契约。

G0：记录现有 Ubuntu/Windows × Python 3.11/3.12 测试矩阵及执行结果。先交指标公式/测试案例反馈给文档线，冻结后再编写正式验收断言。

G1 后执行：
1. 为局部修复、闪烁、拖影、外观稳定分别做端到端行为测试及组合测试，采用冻结的开发/留出划分。修复程序看不到干净参考和真值；评分进程才可以读取。用更换/移走评测真值等方式验证推断路径隔离，不能只相信代码注释。
2. 独立计算 ROI MAE、参考误差时间差分、固定拖尾区残影能量、外观残差波动及保真保护指标，核对实践输出的报告。不要导入实践算法里的同名评分函数充当独立 oracle。
3. 覆盖作用域外无损像素不变、无退化输入、首尾帧、短序列、重复帧、空/全掩膜、缺帧、错误分辨率、非法 fps/tick、摘要不符、损坏文件和工具失败。全掩膜/证据不足的预期行为遵循契约，不能默许生成假成功。
4. 重复执行验证规范化像素、manifest 语义字段和参数摘要；路径/日志时间不能污染身份。区分固定环境确定性、跨平台容差和 MP4 编码差异。
5. 视频 job 实际执行编码并用 ffprobe 及解码验证帧数、帧率、尺寸、时长和可播放内容；comparison 与 before/after 时间范围一致。缺编码工具时正式视频验收 job 必须失败，不得用 skip 制造绿色。
6. 保留既有完整质量矩阵。将耗时媒体验收放在独立必跑 job（至少一个固定 Linux 工具环境），上传 MP4、代表帧、metrics、manifest 和失败日志，设置大小与保留期限；不上传秘密或个人绝对路径。
7. 外部工具只作为实验/CI 依赖，不进入默认 Core 运行依赖。按明确版本或固定环境安装，不照抄本机浏览器硬编码。共享小型 fixture 并防止在测试内自造真值又自证成功。

必须运行并报告：
python -m unittest discover -s tests -v
python -m ruff format --check .
python -m ruff check .
python -m pyright
python -m compileall -q svm tests
以及冻结契约要求的实际端到端媒体验证命令。

禁止降阈值、弱化 Ruff/Pyright、隐藏失败、修改已有受控恢复政策或以平均指标掩盖某一必选场景失败。基线本来失败与新增回归分开记录，但都不能写成通过。

交付测试代码、workflow、精确环境/命令/结果、待验证项及 CI 证据。汇报所测 implementation SHA、contract version、CI SHA/运行链接；只有工作流实际运行并成功才能称远端 CI 通过。所有通过/失败/跳过/未运行必须分别列明。
```

## 提示词 4：审查线（可整段复制）

```text
你是 Structured-Vector-Motion 视频修复 v0 的独立审查线 Agent。
Agent 工具：Codex。指定模型：GPT-6 Astra（gpt-6-astra）。推理强度：xhigh（Extra High）。
请在工具中实际设置上述模型/强度；不能设置时报告实际配置，不要伪称提示词已完成切换。

仓库：https://github.com/Gay-wushuang/Structured-Vector-Motion
本地参考：D:\codex\Structured-Vector-Motion；用独立 worktree 审查明确候选 SHA。
已核对参考 SHA：cf4815357909f4e462f26619d33e6bfcb1e16236。
读取 AGENTS.md、docs/planning/video-repair-v0-dispatch.md、其中必读资料和冻结契约。任务包缺失时索取全文。

目标：判断“受控视频修复改善且可导出”的交付是否有可信证据、是否守住 SVM 边界。你只拥有 docs/video-repair/review.md；可以本地执行只读审查/复现及临时攻击实验，不直接修改实现、测试、阈值或其他线文档。缺陷交回文件所有者修复，保持审查独立。

G0 并行审查范围和契约草案，尽早指出架构冲突、指标漏洞和不可执行依赖。G1 检查门槛是否在正式留出验收前冻结。G2/G3 对明确的候选 SHA 和 contract version 完成代码及媒体审查：
1. Core 没有新增文件系统/网络/时钟/编解码读取；实验工具、Renderer 和 Exporter 职责清楚。凡涉及 accepted Document 变更，都走现有 Artifact/Proposal/注册 Change/原子 Revision 接受，不绕过权限、作用域或 base revision 检查。
2. 输入和掩膜内容可追溯，外部结果快照有版本；不把路径当身份。干净参考、真实运动/退化参数和报告没有泄漏到修复推断；不能将原始干净渲染作为修复结果。显式掩膜和其他人工帮助必须披露。
3. 没有把 spec/56–58 的灰度、分离、可见轮廓能力扩展宣称为任意彩色/遮挡视频恢复，也没有把帧级后处理宣称成可编辑 SVM 内容。插值时刻的准确性不能由少数观测时刻通过推出。
4. 逐项核查四项指标原始值、区域、单位、阈值及留出规则；检查冻结帧、全局模糊、错配时间、裁掉困难区、事后选帧等取巧是否被保真指标拦住。合成结果只支持合成受控结论。
5. 实际观看完整 before/after/comparison，检查首尾、运动边缘、拖尾、闪烁区及未授权区域。至少复现一条完整导出命令并解码检查媒体；只看截图或文件名不足以签署验收。无法观看或复现时明确写未验证。
6. 导出使用 FINAL 且没有 stale 依赖；失败工具不留下成功标志；帧数/帧率/时长/尺寸/对照对齐一致。跨平台确定性声明有适当证据，不拿 MP4 二进制哈希代替视觉/像素验证。
7. 审阅全量 CI 和 Golden A/B 及 motion/revision/identity 回归；核对测试实际覆盖的代码 SHA，而不是旧绿灯。独立评分不复用被测实现的判断逻辑，必需工具缺失不能以 skip 当通过。

报告按严重度列缺陷，包含文件与行号、触发条件、影响、可运行复现、建议修复及复核状态。不要只写泛泛风险或为凑数量编问题。
最终结论用 PASS / CHANGES_REQUIRED / BLOCKED：PASS 需要必选产物、门槛、质量检查及关键媒体复核都完成；有代码缺陷用 CHANGES_REQUIRED；缺素材/工具/证据导致不能判断用 BLOCKED。无发现时写明范围和剩余局限，不等于宣称普适正确。
交付 docs/video-repair/review.md，记录 reviewed SHA、contract version、CI 运行及实际媒体路径。你给出审查建议，策划线负责最终收口；不要自行合并或改别线工作。
```

## 四线统一回报格式

```text
工作线 / 实际 Agent、模型、强度：
分支 / 基线 SHA / 当前 SHA / 依赖提交：
契约版本 / 已到 G0–G3 哪一关：
改动路径：
交付物路径：
实际执行命令与结果（通过、失败、跳过、未运行）：
四项指标（适用时）：
缺陷/阻塞及证据：
需要哪一线提供什么：
建议策划线下一步：
```

## 参考依据

- 仓库基线：https://github.com/Gay-wushuang/Structured-Vector-Motion/commit/cf4815357909f4e462f26619d33e6bfcb1e16236
- 受控恢复边界：https://github.com/Gay-wushuang/Structured-Vector-Motion/blob/cf4815357909f4e462f26619d33e6bfcb1e16236/spec/58-explicit-multi-object-raster-recovery.md
- 模型与强度设置：https://learn.chatgpt.com/docs/models?surface=web

状态：仅生成策划任务包；尚未派发 Agent、创建四线工作区、实现修复或运行新验收。
