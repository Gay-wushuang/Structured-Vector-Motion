# C-MVP v0.1 · SVM 接入边界

| 项目 | 内容 |
| --- | --- |
| 版本 | `c-video-repair-contract@0.1`，草案修订 `R1-002` |
| 状态 | **DRAFT**，等待 C 板块策划线 G1 审核。 |
| 适用范围 | Motion 来源、外部媒体链路、修复结果与 Document/Revision 权限。 |
| 已验证事实 | 下表为文档分支 `5561d8b` 和实践分支 `b310f57` 的源码盘点。 |
| 待实现能力 | 正式 Motion 导出及审计、参考进程隔离、外部媒体工具配置与正式验收。 |
| 未决问题 | 正式 Document 及 Revision 选择、采样/光栅化和 FFmpeg 工具环境，见[策划分派](../planning/video-repair-v0-dispatch.md#g1-待决问题)。 |

## 1. 已有能力和证据

| 来源 | 已核对行为 | C 板块可采用的接口 |
| --- | --- | --- |
| [Core 模型](../../spec/00-svm-core-model.md)、[系统边界](../../spec/05-system-boundaries.md)、[不变量](../../spec/01-invariants.md) | Document 定义接受的语义，Artifact 属外部证据，Immutable Value 属确定性计算结果。Proposal 接受由 Core 独立授权。 | 只读 Motion 数据作为来源，修复产物留在外部。 |
| [Motion](../../spec/21-motion-semantics.md)、[Motion Revision](../../spec/22-motion-revisions.md)、[MotionEvaluator](../../svm/motion.py)、[SVGRenderer](../../svm/renderers/svg.py) | 整数 tick 采样获得 Motion Frame 和求值场景，SVGRenderer 输出 SVG。已有质量及缓存语义。 | 从确切快照逐 tick 取得 FINAL 且当前的结果，输出 SVG，由外部工具光栅化。 |
| [Artifact 存储](../../svm/artifacts.py)、[现有 CLI](../../svm/cli.py) | 已有内容寻址与 Core CLI，未提供 C 视频专用持久化存储或 C 命令。 | 用外部包保留可重取的不可变输入副本，以 SHA 验证。 |
| [OpenCV 分析](../../spec/16-opencv-artifact-analysis.md)、[光栅观测](../../spec/56-controlled-raster-observations.md)、[相机恢复](../../spec/57-controlled-raster-camera-recovery.md)、[多对象恢复](../../spec/58-explicit-multi-object-raster-recovery.md) | 受控灰度静态光栅证据和显式恢复，支持域受限。 | 坐标等约定可借鉴。RGB 视频修复需要本契约的独立证据。 |
| [Motion 示例 001](../../demo/001-group-motion/build_demo.py)、[Motion 示例 004](../../demo/004-real-pop-animation/build_demo.py) | 外部示例通过本机浏览器截帧与 FFmpeg 导出，存在固定工具路径和产物目录的假设。 | 复用采样和导出思路。正式 B 要记录可重现的外部工具配置、清理旧输出污染并验证每一帧。 |
| [实践原型](https://github.com/Hesperr233/Structured-Vector-Motion/tree/b310f57e6a21562798f5ccad2a1897ba4d99c47e/prototype/video_restoration) | 有程序合成 A 规格素材、显式四组掩膜、受限修复、三路 MP4 和离线评分。该源码位于实践分支，README 中的实测是原型自报证据。 | 以兼容入口复核行为。正式接口及其状态以[管线契约](pipeline-contract-v0.1.md)为准。 |
| [pyproject.toml](../../pyproject.toml)、[CI workflow](../../.github/workflows/ci.yml) | 现有开发/几何/SVG/追踪/分析依赖及 Ubuntu/Windows × Python 3.11/3.12 质量矩阵。没有 C 媒体验收 job。 | 视频工具仅为实践或 CI 的显式实验依赖。 |

## 2. 输入、输出和访问权

| 环节 | 可读取 | 产出或影响 |
| --- | --- | --- |
| A 合成器或 B Motion 渲染、光栅化与离线退化生成 | 受控场景；B 的只读 Document 和当前 FINAL 结果 | 干净序列及注入真值存放在离线评测树。退化 PNG、授权掩膜及规范元数据单独发布。 |
| Ingest | 原始视频或退化 PNG 包 | 外部规范包、原始输入摘要和可重取快照。 |
| Repair | 退化包、显式授权/供体/静态掩膜、配置 | 外部无损修复帧和运行记录，无 Document、Revision、Entity、Track 或 Immutable Value 写入。 |
| Export | 运行内校验过的前后无损帧 | 三路演示媒体、可重放的工具参数和媒体摘要。 |
| Evaluate / Verify | 已封存的修复证据、独立离线 reference 和评分区域 | 指标与验收报告。允许记录参考 SHA，禁止把评分数据反馈给 repair。 |

C 工具由外部 Artifact Processor、光栅化和 Media Encoder/Exporter 组成。禁止新增 Core Operation、Change、Schema 字段、政策或 `svm` CLI 命令。禁止在 Operation 中访问视频文件、网络、时钟或 UI。修复后的外部帧、媒体和报告属于派生产物。只有源 Document 的当前 FINAL 求值可作为 B 的 SVM 来源证明。

以后如确需改变已接受 Document，应另立任务。以外部 Artifact 作为证据，Adapter 构造针对确切 base Revision 的 Proposal，`ProposalAcceptor.accept()` 校验 Artifact、权限、约束和已注册 Change，再原子提交新 Revision。保留旧 Revision 的可求值性。外部工具不得直接调用 `RevisionStore.commit()`。依据 [Proposal 边界](../../spec/05-system-boundaries.md)及 [ProposalAcceptor](../../svm/proposals.py)。

## 3. 隔离与审查证据

- repair 的参数无 reference、clean 或 ground-truth 路径。以独立进程及最小可见输入运行。打包不得穿越根目录或通过符号链接、junction 等形式访问评测树。评分代码不得作为运行时依赖。
- 对相同输入执行隔离复核。把评测树移出工作目录或使其不可读，再在新目录运行，仅比较修复像素、修复语义摘要和逐帧报告。原输入只读运行并前后核对 SHA。使用隔离的临时数据完成破坏性反例。
- 记录 B 的确切 Document / Revision、采样范围、逐帧 FINAL 当前状态、SVG/PNG 摘要和固定外部工具。只在离线报告保存干净源证据。三路媒体各自从封存的无损帧编码，并以解码内容检查同 PTS 的左右对应。
- 审查需指定相同 implementation SHA、CI SHA、文档 SHA 与契约修订。历史测试日志和原型自报数据仅可追踪调查背景。完整验收使用[验收标准](acceptance-criteria-v0.1.md)。
