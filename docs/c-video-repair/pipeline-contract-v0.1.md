# C-MVP v0.1 · 管线与接口契约

| 项目 | 内容 |
| --- | --- |
| 版本 | `c-video-repair-contract@0.1`，草案修订 `R1-002` |
| 状态 | **DRAFT**，G1 审核后由 C 板块策划线冻结。 |
| 适用范围 | 外部 CLI、文件、状态、媒体与追溯接口。A/B 规格见[需求](requirements-v0.1.md)。 |
| 已验证事实 | 实践代码 `b310f57e6a21562798f5ccad2a1897ba4d99c47e` 有 `synthetic`、`demo`、`evaluate` 三个模块入口。 |
| 待实现能力 | 下表含全部正式入口，均无完整契约实现或验收证据。 |
| 未决问题 | 兼容窗口、固定工具版本与传递函数往返验证、掩膜 fixture、B profile，见[策划分派](../planning/video-repair-v0-dispatch.md#g1-待决问题)。 |

## 1. 统一接口

正式命令计划采用 `python -m prototype.video_restoration <command>`，在仓库根目录执行，与现有基于模块的实验路径一致。命令之间仅用约定文件交接。

| 正式命令 | 参数 | 读取与产出 | 实现状态 |
| --- | --- | --- | --- |
| `ingest` | `--source PATH --output DIR [--decoder-profile ID] [--drop-audio]` | 源 RGB8 帧包或受控 MP4 → 规范 PNG 包及原始输入记录。 | 待实现。原型直接读取固定格式 PNG，无 MP4 输入。 |
| `repair` | `--input DIR --masks DIR --config FILE --output DIR` | 退化 PNG、显式掩膜、配置 → 前后无损帧、修复记录及清单。 | 待实现。原型 `demo` 同时做修复和导出。 |
| `export` | `--run DIR --encoder EXEC --ffprobe EXEC` | 已封存的前后 PNG → `before.mp4`、`after.mp4`、`comparison.mp4`、媒体摘要及阶段状态。 | 正式命令待实现。已有部分编码、ffprobe 和完整解码能力在 `demo` 中。 |
| `evaluate` | `--run DIR --reference DIR --output FILE` | 前后 PNG、离线 reference/评分区域 → `<run>/metrics.json`，绑定 run identity 和已封存帧。 | 正式参数、公式及报告待实现。同名原型模块已实现离线诊断。 |
| `verify` | `--run DIR --reference DIR --contract VERSION --expected-code-sha SHA --output FILE` | 已导出和评分的运行 → 独立核验、`<run>/acceptance-report.json` 和最终状态。 | 待实现。由 CI 线拥有独立验证逻辑。 |

原型入口属于 R1-001 兼容路径，状态仅描述实践分支的实际接口。

| 已实现的原型入口 | 用法 | 实际语义 |
| --- | --- | --- |
| `python -m prototype.video_restoration.synthetic` | `--output DIR [--seed N] [--without STAGE]...` | 生成 24 帧开发素材，导出 `input/`、四组掩膜 `mask/` 和离线 `evaluation/`。 |
| `python -m prototype.video_restoration.demo` | `--input DIR --mask DIR --output DIR [--ffmpeg EXEC] [--ffprobe EXEC]` | 修复并编码。退出 0 仍可能是 `partial`；媒体 `verified` 只说明原型已验证媒体。 |
| `python -m prototype.video_restoration.evaluate` | `--run DIR --mask DIR --evaluation DIR` | 更新原型 `metrics.json`，计算原型现用的诊断公式，未执行正式验收。 |

兼容期保留原型入口和原型出件语义。正式 CLI 在新运行目录发布规范命名和格式。读入旧结果时，`original.mp4 → before.mp4`、`repaired.mp4 → after.mp4` 是媒体角色映射。旧 `comparison.mp4` 仍需逐 PTS 复验。旧 `manifest.json` 可作为 `svm-c-r1-restoration@1` 的历史记录阅读，禁止仅改名为 `run-manifest.json`。旧六位帧名 `000000.png` 等，经显式 ingest 或迁移写到新目录，生成四位规范文件名并重新校验文件和像素摘要。旧 `metrics.json` 的公式与证据按原型解释，正式验收须从原始证据重跑。新结果不同时生成新旧别名，兼容窗口由策划线审核。

## 2. 输入输出示例

以下是正式接口目标的 PowerShell 示例。这里的 `fixtures/s1-source` 是含规范元数据的退化源，`fixtures/s1-eval` 位于独立离线目录树。样例中的 SHA 用实际候选提交的完整 SHA 替换。

```powershell
$codeSha = '<implementation git SHA>'
$run = 'build/cvr/s1-run'
python -m prototype.video_restoration ingest --source fixtures/s1-source --output build/cvr/s1-input
python -m prototype.video_restoration repair --input build/cvr/s1-input --masks fixtures/s1-masks --config fixtures/s1-config.json --output $run
python -m prototype.video_restoration export --run $run --encoder ffmpeg --ffprobe ffprobe
python -m prototype.video_restoration evaluate --run $run --reference fixtures/s1-eval --output "$run/metrics.json"
python -m prototype.video_restoration verify --run $run --reference fixtures/s1-eval --contract c-video-repair-contract@0.1 --expected-code-sha $codeSha --output "$run/acceptance-report.json"
```

```text
s1-run/
  input/video-manifest.json
  input/frames/frame-0000.png ... frame-0023.png  # before 的无损快照
  masks/mask-manifest.json
  masks/repair/...                              # 其他掩膜见 §4
  config.json
  frames-repaired/frame-0000.png ... frame-0023.png
  before.mp4
  after.mp4
  comparison.mp4
  run-manifest.json
  metrics.json
  acceptance-report.json
  run.log
```

run 中的输入为只读快照，有明确的包内路径及摘要。参考目录含 `reference-manifest.json`、干净帧和评分掩膜，只提供给独立的 evaluate/verify 进程。可追回的原 MP4 保留在 ingest 输出包的 `source/`，run 记录输入包和源摘要，发布证据须能按摘要找到此包及原视频。整套结果写在新的互不重叠的路径，禁止覆盖源或已有运行目录。

## 3. PNG、时间与 MP4 摄取

- PNG 为非隔行 PNG truecolor type 2、RGB8、无 alpha 和 palette。直接使用 sRGB 编码码值，拒绝会触发样本转换的色彩声明，禁止隐式色彩或 gamma 转换。第 `i` 个文件为 `frames/frame-NNNN.png`，与 manifest 索引一致。拒绝缺帧、多帧、重复/乱序索引和损坏文件；合法相同像素帧可占不同展示位置。
- A 和 B 共享格式。A 的 `timebase_ticks_per_second = 12` 且 `frame_ticks[i] = i`。B 的 Timebase、采样起点及每帧 Motion tick 按批准的 profile 记录。`presentation_pts(i)` 以秒为单位，等于 `i * fps.denominator / fps.numerator`。tick、PTS 使用整数或有理数，所有媒体展示时长为 `frame_count / fps`，不编码右端点。
- `video-manifest.json` 记录 `contract_version`、`draft_revision`、`scenario_kind`、`clip_id`、`profile_id`、宽高、`pixel_format: "RGB8"`、`color_space: "sRGB"`、`frame_count`、有理数 `fps`、`timebase_ticks_per_second`、`frame_ticks`、精确有理数 `duration_seconds`（如 `"2/1"`）、`endpoint_rule: "left-closed-right-open"` 和 `frames`。每帧记录 `index`、`file`、`file_sha256`、`pixel_sha256`。另记录 `bundle_digest`、`clean_reference_in_input: false` 及允许公开的来源摘要。干净 SVG/PNG、Document 定位、注入种子和真值仅放离线来源记录。
- 受限 MP4 摄取仅面向 A，输入为 H.264/8-bit `yuv420p`、符合 A 的尺寸、帧数和 CFR，色彩遵循 §7 的显式可逆记录策略（编码本身有损）。拒绝 VFR、旋转元数据及未知色彩配置。默认拒绝音轨，只有 `--drop-audio` 可显式丢弃并记录。以选中视频 stream 的 time base 和每帧源 PTS 建立 `source_pts → index → presentation_pts/Tick` 映射。保存原媒体的 SHA 和字节快照、stream、编码/色彩信息、解码版本及可重放参数。冻结原始快照的可重取方式，复核时仅用快照重做 ingest。规范 PNG 包是 repair 的内容身份。

## 4. ROI、掩膜与配置

| 输入 | 约束与用途 |
| --- | --- |
| `repair_roi` | 图像坐标原点为左上，半开矩形 `[x0,y0,x1,y1]`，必须在画布内。 |
| `repair` | 静态背景局部替换的写入授权。可按 `roles` 提供互斥的 `defect`、`ghost` 子掩膜，支持必须在授权内。主掩膜总支持非空、每帧不得覆盖整幅画面。常量掩膜必须有支持；逐帧掩膜允许无待修像素的某帧为空，整组不能全空。 |
| `donor_valid` | 同坐标背景供体的可靠性许可。逐帧明确排除损坏、拖影、遮挡和经过该像素的前景。写入掩膜不提供供体有效性；读入合格供体后仍需验证邻域证据的一致性。 |
| `static_sample` | 估计光度的只读静态样本，离移动目标和拖影至少 2 px，可在写入 ROI 外。 |
| `photometric_roi` | 显式光度写入矩形，位于 `protection_domain` 内。仅声明的这种修正可改变 `repair` 掩膜外合法像素。 |
| `feather_px` | 整数 `[0,8]`。`protection_domain` 为 `repair_roi` 扩展该距离后裁剪到画布；扩展本身不授权写入。 |
| `evaluation_roi` 及评分掩膜 | 在评测树预先固定，禁止提供给 repair。其像素区域与修复授权不同。 |

`mask-manifest.json` 记录版本、修订、宽高、`repair_roi`、`feather_px`、
`mask_semantics: "255=role-active,0=role-inactive"` 和 `roles`。
每个角色记录用途、来源（用户提供或受控测试刺激）、`kind: "constant" | "per-frame"` 和按索引排序的文件记录。文件记录含相对路径、文件/像素 SHA、支持像素数。掩膜均为与画布同尺寸的灰度 8-bit PNG，取值只可 0/255。常量角色文件用索引 0，逐帧角色逐索引声明。显式掩膜可由受控实验提供疑似受损或不可用观测的范围。不得编码或嵌入 clean 像素、真实运动轨迹或注入参数。报告披露其来源，禁止声称自动识别。

配置例（以下键和取值为草案）：

```json
{
  "contract_version": "c-video-repair-contract@0.1",
  "draft_revision": "R1-002",
  "clip_id": "S1",
  "repair": {
    "mode": "temporal-median",
    "window_radius": 2,
    "minimum_observations": 2,
    "max_changed_fraction": "1/4",
    "spatial_fallback": null
  },
  "photometric": {
    "enabled": true,
    "roi": [64, 64, 192, 192],
    "max_abs_luma_offset": 32,
    "max_abs_channel_offset": 16
  },
  "ghost": {
    "enabled": true,
    "min_clean_observations": 2,
    "max_displacement_px": 4
  },
  "determinism": {"rounding": "round-half-to-even", "random_seed": null}
}
```

未知字段、模式或非空 fallback 失败。光度校正从退化帧的静态样本估计。进行局部替换时，选声明窗口内的同坐标可靠邻帧，排除当前帧，边界只用实际存在的邻帧，至少两次可信观测。证据不足或不一致时保持原像素，记录 `UNRESOLVED`。拖影需满足短暂且与物体分离，限制声明允许的拖影位移及 ROI 内变化比例，违反时失败。修复阶段的像素差和残留诊断只基于可见输入；参考残影能量由 evaluate 计算。

## 5. 状态、发布及退出

| 成功交接点 | 清单状态 | 约束 |
| --- | --- | --- |
| repair | `REPAIRED` | 用同层临时目录完成校验、写入和摘要，原子改名后发布；前后无损帧和输入快照封存。 |
| export | `EXPORTED` | 全部三路媒体通过属性和完整解码检查后才发布阶段记录。 |
| evaluate | `SCORED` | 独立输出 `metrics.json`。退出 0 表示完成计算，分数和门槛结果另行报告，未授予运行成功。 |
| verify | `SUCCESS` | 独立复验通过并写妥 `acceptance-report.json` 后，原子更新 `run-manifest.json`；这是唯一可发布成功的时点。 |

阶段串行、独占写入。每步先核对上一步状态和摘要，把新产物写到临时位置，验证后以替换清单作为状态提交点。正式 evaluate/verify 的输出路径必须是表内 run 工件路径，禁止指向原文件或预先存在的其他输出。中断遗留的产物只能按清单引用和摘要读取。执行失败写 `FAILED` 或只留无成功标志的临时诊断；证据不足写 `PARTIAL` 并退出 5。部分输出不得沿正式流水线验收。若同目录已有终态运行，新请求失败并保护原运行；重试使用新目录。缺失产物、核验失败、阈值未过或报告发布失败时，本次运行不得出现 `SUCCESS`。逐帧状态用 `UNCHANGED`、`REPAIRED`、`UNRESOLVED`。未解析区域与变化区域分别计数。

| 退出码 | 稳定诊断 | 对应情形 |
| ---: | --- | --- |
| 0 | `EXIT_OK` | 当前阶段完成。只有 verify 的 0 表示验收通过。 |
| 2 | `CVR-E001`–`CVR-E012` | 版本、帧数、尺寸、帧率/tick、帧索引、PNG、ROI、掩膜格式、支持、范围、羽化、目录冲突，依序对应。 |
| 3 | `CVR-E013`、`CVR-E014` | SHA 不符或运行输入过期；参考隔离违规。 |
| 4 | `CVR-E015`–`CVR-E020` | 不支持的色彩、音轨、VFR/旋转、配置、空间 fallback、移动物体内部背景替换，依序对应。 |
| 5 | `CVR-E021`–`CVR-E024` | 证据不足、光度上限、拖影超域、变化比例超限，依序对应。 |
| 6 | `CVR-E025`、`CVR-E026` | 所需工具缺失；编码/解码工具调用失败。 |
| 7 | `CVR-E027`–`CVR-E029`、`CVR-E031` | 输出摘要、媒体验证、越权像素、验收指标/护栏不通过。 |
| 8 | `CVR-E030` | 非预期内部错误。 |

## 6. 清单与可复核身份

| 工件 | 必需字段及身份 |
| --- | --- |
| `run-manifest.json` | 版本、修订、`run_id`、`semantic_digest`、当前阶段状态和最近一次阶段退出码；场景及输入/掩膜/配置 SHA；实际完整 Git `code_sha`、算法 ID、参数、种子（确定性时 `null`）、工具版本；每帧时间、结果状态、文件与像素 SHA、变更/未解决计数；披露 ROI、授权域、掩膜角色与支持；媒体时序、相对路径、文件 SHA 及工具记录；错误码和不含本机路径的诊断。 |
| `metrics.json` | 版本、修订、clip/profile ID、run ID、修复语义摘要、输入与代码 SHA、评分代码 SHA、参考和评分区域 SHA；每条公式 ID、单位、区域、输入值、输出值、改善率、阈值、状态及原因。护栏逐条输出，保留时间序列等所需诊断。 |
| `acceptance-report.json` | 版本、修订、run ID、修复语义摘要、输入与实施/评分/验收代码 SHA、指标文件 SHA 和三路媒体 SHA；逐检查 ID、通过/失败/未运行、实测值、期望、诊断；总体 `PASS`、`CHANGES_REQUIRED` 或 `BLOCKED`。B 的离线源证据按摘要绑定到报告。 |

- `file_sha256` 哈希精确文件字节，`pixel_sha256` 哈希从左上按行扫描的解码字节，无行填充（PNG 为 RGB 通道交错，掩膜为灰度单通道）。文件和像素 SHA 都用 `sha256:<64 lower-case hex>`。
- `bundle_digest` 哈希输入 manifest 的显式投影，键为 `contract_version`、`draft_revision`、`profile_id`、`width`、`height`、`pixel_format`、`color_space`、`frame_count`、`fps`、`timebase_ticks_per_second`、`frame_ticks`、`duration_seconds`、`endpoint_rule`、`frames`。帧只投影 `index`、`file_sha256`、`pixel_sha256`。mask/config 摘要为其 JSON 文件 SHA。
- `run_id` 为 `run:<hex>`，哈希规范对象 `{contract_version, draft_revision, bundle_digest, mask_manifest_sha256, config_sha256, algorithm_id, code_sha}`。验收独立核对实际候选实现 SHA，仅有 repair.py 文件摘要不足以标识实现。
- `semantic_digest` 为修复封存时对 `{run_id, frames}` 的哈希。帧按索引记录 `index`、`pixel_sha256`、`status`、`changed_pixels`、`unresolved_pixels`。清单阶段和 MP4 摘要更新不改变封存的修复身份。媒体、评分和验收报告以各自的文件 SHA 和 run ID 相互校验，无双向哈希依赖。
- 哈希规范 JSON 用 UTF-8、键按 Unicode 码点排序、非 ASCII 字符直接编码、标准 JSON 字符转义、紧凑标点、保留数组顺序、无 BOM 或尾换行。参与语义哈希的数值用整数或规范字符串/有理数。指标按未舍入值判定，JSON 数值保留足够复核的精度，展示可用六位小数。
- 路径只写包内相对 POSIX 路径，拒绝绝对路径、上级跳转及通过连接点越界。工具参数中以角色占位符记录本机位置，去除 hostname、个人路径和临时目录。真实起止时间、耗时与日志不进入语义身份；上传日志同样不得泄露这些路径或评测参考位置。

可复核的 A 输入时间示例为 `frame_count=24`、`fps={"numerator":12,"denominator":1}`、`frame_ticks=[0,1,...,23]`，最后一帧的展示 PTS 为 `23/12`。当 H3 的 M3 输入为 `5.0` DN、输出为 `3.0` DN 时，指标行记录公式 `cvr-metric-ghost-residual@0.1-r1.002`、区域 G 的摘要、`relative_improvement=0.4`、`threshold=0.30` 和通过状态。此算例仅说明字段，单条指标通过不能发布运行成功。

## 7. 外部媒体 profile

无损输出 PNG 与输入尺寸、帧数、顺序相同。编码器固定并记录，PNG 文件哈希用于工件完整性，解码像素哈希用于规范像素比较。

| 媒体 | 规范 |
| --- | --- |
| `before.mp4` / `after.mp4` | 单路 H.264、`yuv420p`、静音、faststart，尺寸为 profile 的宽高。 |
| `comparison.mp4` | 同样编码，宽度 2 倍，画布内同一 PTS 左 before 右 after。禁止裁切、标签、边框或重定时。 |
| 色彩和 PTS | RGB8 sRGB 码值转换为 BT.709 矩阵、有限范围 YCbCr；其 primaries 与输入 sRGB 一致，保留 sRGB transfer 并显式标记 `iec61966-2-1`。禁止给未转换的 sRGB 码值标 BT.709 transfer。每路从 0 按有理间隔展示，完全匹配 profile PTS、总帧数、时长。 |
| 外部工具候选 | FFmpeg/libx264，`preset medium`、`crf 16`，固定 A 规格为 GOP 12，使用固定工具环境和显式 ffprobe/完整解码。用色条与暗阶验证标记、范围和解码 RGB。 |

编码使用暂存目录并核查输出映射。ffprobe 检查元数据及逐帧展示时间，完整解码检查每个 PTS：before 与输入、after 与修复帧、对照左右半幅分别与各自源帧比较。解码需明确执行相反的 BT.709 矩阵与范围换算并保留 sRGB transfer。误差阈值和聚合由[验收标准](acceptance-criteria-v0.1.md)定义。跨平台 MP4 字节哈希只用于验证各自工件。缺 FFmpeg/ffprobe 或解码链路未完成时验收失败。
