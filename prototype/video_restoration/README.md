# SVM C 实践线 R1-001 · 受控视频修复

本实验实现 256 × 256、12 fps、24 帧、固定相机的 RGB8 PNG 修复与 MP4 导出。素材由程序绘制，包含静态纹理背景、移动椭圆、人工闪烁、单帧拖影及局部遮损。默认种子为 `20261109`，生成器为 `svm-c-r1-synthetic@1`。随机数算法、遮损帧、拖尾权重、亮度偏移和注入顺序记录于 `fixture/evaluation/fixture.json`。`--without` 可分别关闭 `flicker`、`ghost` 或 `defect`。

本轮基线为 `6b9a304f66d8a657f77e729a73e36f8bb0f3133c`。该提交包含 C-MVP v0.1 契约草案。R1 按本轮的合成样例与 CLI 交付，使用自己的原型 profile，尚未进行草案规定的正式留出集验收。

## 仓库调查与接入边界

| 现有入口 | 本轮核对的能力 |
| --- | --- |
| `svm/artifacts.py` | 按内容哈希存取外部证据快照，供 Adapter 与 Proposal 使用。 |
| `svm/adapters/opencv_analysis.py` | 对受限灰度 PNG 生成二值掩膜和连通域证据。 |
| `svm/motion.py` | 用整数 tick 采样 Document 中已记录的运动，产生逐帧求值结果。 |
| `svm/renderers/svg.py` | 将求值场景输出为 SVG。 |
| `demo/004-real-pop-animation/build_demo.py` | 示例脚本用外部浏览器光栅化并调用 FFmpeg。 |

这些入口没有现成的视频像素修复接口。本原型在 `prototype/video_restoration/` 内独立运行，复用已有 Pillow 与 OpenCV 依赖，直接使用 OpenCV 所依赖的 NumPy。它生成和消费外部 RGB 帧。后续如需 SVM 出图，可在外部工具将 FINAL 且当前的 SVG 帧光栅化成同规格 PNG，再作为此类工具的输入。合成参考生成、修复、评分与视频编码分别位于实验入口，修复像素不会进入 Document、Revision 或 Proposal。

## 复现

在本分支仓库根目录运行。实测 Python `3.12.14`、OpenCV `4.14.0`、Pillow `12.3.0`、NumPy `2.5.4`。可以在独立虚拟环境安装以下实验依赖。

```powershell
python -m pip install Pillow==12.3.0 numpy==2.5.4 opencv-python-headless==4.14.0.94
```

- Pillow 用于 PNG 编解码，许可证 MIT-CMU。NumPy 用于数组和数值统计，项目采用 BSD-3-Clause，实测轮子另含 0BSD、MIT、Zlib 和 CC0-1.0 组件。
- `opencv-python-headless` 的打包脚本采用 MIT，OpenCV 本身采用 Apache-2.0。原型使用 OpenCV 连通域和邻域形态操作。随轮子分发的第三方组件许可证见其 `LICENSE-3RD-PARTY.txt`。
- 外部 `ffmpeg` 和 `ffprobe` 负责 H.264 编码、元数据核验和完整解码。实测为 Gyan `9.0.2-essentials_build-www.gyan.dev`，此构建启用 libx264，随附 GPLv3 许可证。使用 [Gyan 版本固定的 Windows 构建](https://github.com/GyanD/codexffmpeg/releases/tag/9.0.2)。实测 `ffmpeg-9.0.2-essentials_build.7z` 的 SHA-256 为 `4705843ccaaf54257c16ad90f3e952ece33c17df964ecf7bfdbb0f49c7171077`。可将工具加入 `PATH`，或使用下文的显式路径参数。

```powershell
$run = 'build/video-restoration'
python -m prototype.video_restoration.synthetic --output "$run/fixture" --seed 20261109
python -m prototype.video_restoration.demo --input "$run/fixture/input" --mask "$run/fixture/mask" --output "$run/result" --ffmpeg ffmpeg --ffprobe ffprobe
python -m prototype.video_restoration.evaluate --run "$run/result" --mask "$run/fixture/mask" --evaluation "$run/fixture/evaluation"
```

生成和修复要求新的输出目录。`input/` 只接受名为 `000000.png` 到 `000023.png` 的连续 8 位 RGB PNG。`mask/` 内有同索引的 `roi/`、`stable/`、`ghost/`、`defect/` 四组 0/255 灰度 PNG。稳定样本固定且在 ROI 外，只用于估计。拖影和缺陷掩膜互斥，且必须在 ROI 内，某帧可以没有拖影或缺陷。显式掩膜由合成器提供，用于限定授权区和疑似受损区域。`evaluation/` 的 clean reference、注入真值和运动评分掩膜只由独立的评分命令读取。

### 修复与失败状态

1. 从固定稳定样本估计相对于全片中位背景的共同 RGB 加性偏移。残差过大、偏移超限、支持不足和持续同向变化会触发拒绝。在 ROI 内应用可靠偏移，避免对饱和端点强行逆推。
2. 拖影区只接纳有多数帧支持的同坐标背景候选，并从实际观测中选取供体。局部强边缘、过强残差和供体不一致均会保留原始拖影数据。合成拖尾掩膜另外与当帧目标保持两像素距离。
3. 局部缺陷限于小型、内部、单连通掩膜。掩膜周围的邻域必须有足够静态证据，才使用时域同坐标背景样本填补。
4. 保存两组无损 PNG、按帧报告、参数和源/输出 SHA-256。MP4 输出为静音 H.264 `yuv420p` BT.709，同步对照左原始右修复。三支视频经 ffprobe 检查格式、尺寸、12/1 帧率和连续 PTS，再完整解码并与各自无损源帧比较后发布。

`demo` 退出 `0` 表示输出视频通过验证。若存在修复拒绝，manifest 顶层为 `partial`，媒体仍单独记为 `verified`。输入错误退出 `2`，缺工具或编码失败退出 `6`，媒体核验失败退出 `7`，其他输出错误退出 `8`。媒体失败时保留已写入的 PNG 和指标，manifest 明确标记失败。`evaluate` 可对已完整写出的 PNG 单独评分，输出合入 `metrics.json`。

## 默认样例实测

生成、修复/导出与评分三条命令均退出 `0`。同一环境重复执行后，193 个合成文件以及结果中的 48 个 PNG、`metrics.json`、`manifest.json` 均逐字节一致。MP4 核验以实际解码内容为准。

| 8 位码值指标 | 退化输入 | 修复后 |
| --- | ---: | ---: |
| ROI RGB MAE | 6.611509 | 0.007679 |
| 局部缺陷 RGB MAE | 73.772006 | 0 |
| 静态评分区亮度均值的时间标准差 | 7.810250 | 0 |
| 静态评分区 RGB MAE 的帧间变化均值 | 5.217391 | 0 |
| 拖影掩膜超过 1 DN 的平均残差 | 26.609687 | 8.169516 |
| 目标内部 RGB 均值的时间标准差 | 7.810250 | < 0.000001 |
| 运动边缘 RGB MAE | 6.500000 | 0 |
| 全帧 RGB MAE | 6.536589 | 4.369707 |

运动边缘梯度均值为 40.990333 DN/px，与 clean reference 一致。无损 PNG 的 ROI 外变化像素数为 `0`。468 个拖影掩膜像素中，328 个恢复、140 个保留，涉及 16 帧。三支 MP4 均为 24 帧、12 fps、2 秒，原始及修复为 256 × 256，对照为 512 × 256。完整解码与各自无损源的最大单帧 RGB MAE 分别为 1.902217、1.842412、1.922170 DN。

本地结果目录 `build/video-restoration/result/` 包含 `original.mp4`、`repaired.mp4`、`comparison.mp4`、`frames-original/`、`frames-repaired/`、`metrics.json` 和 `manifest.json`。大批生成文件及下载工具放在 Git 忽略的 `build/` 内。

## 已知局限

- 入口限定为固定帧数、尺寸和帧率的 RGB8 PNG 序列。自然视频、MP4 输入、音轨、可变帧率和移动相机未纳入支持域。
- 短暂的真实全局闪光可能与加性闪烁不可区分。估计基准依赖静态样本和全片中位数，遇到长期漂移或大面积饱和可能弃权。ROI 外的全局注入闪烁按授权边界保留。
- 拖影和缺陷依赖可信的显式掩膜、静态背景和足够供体。误标低对比度运动内容时，强边缘保护不能保证保真。当前证据来自一个组合样例和受控反例，尚无跨平台或真实视频泛化证据。
- MP4 有色度子采样和有损量化。ROI 外逐像素相等只对无损 PNG 检查。
