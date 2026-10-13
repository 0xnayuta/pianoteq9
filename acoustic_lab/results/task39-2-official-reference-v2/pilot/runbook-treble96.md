# Task 39-2 P3 采集 runbook：96 kHz 高音区 + 中低音加密（treble96 v1）

- 生成：2026-10-13（**准备就绪，待用户授权后执行**；GUI 操作留主会话逐次审批，本文件不构成执行授权）。
- 目的：为 P1 修正后的 B 表取得**新登记的验证数据**（旧 holdout 已消耗、不得复用）：
  1. **96 kHz 高音区**：Nyquist 提升到 48 kHz 使 C7 附近可用分音翻倍，直接实测 85–108 段（对 P1 文献外推的独立确认）；
  2. **48 kHz 中低音加密**：确认 24→28 与 48→60 插值曲率的诊断结论（26/50 附近的未看音高）。
- 网格全部使用**未看过参考**的 MIDI 音高（避开旧 holdout 26/39/50/63/77/86/98/104、全部锚点与已登记诊断音 91/95/96）：
  - 96 kHz：{87, 93, 99, 105, 108}（*注意：93 在 P1 的测试重标定中被用作 devpiano 侧测试音符，但参考侧从未采集该音高；108 为表端上界键、无任何参考实测*）
  - 48 kHz：{25, 27, 49, 51, 64, 74}
- 验收口径：`task39-2-method-amendment-3.md`（可比较分音集）+ amendment-1/2（独立留出预测、冻结归一化基准）。

## 1. 矩阵与会话（11 会话 / 33 单元）

| 批次段 | preset | 音 | 力度 | 采样率 | 单元 | 会话 |
|---|---|---|---|---|---|---|
| treble96 | `treble96` | 87, 93, 99, 105, 108 | 41/70/98 | 96 kHz | 15 | 5（每会话 1 音 × 3 力度） |
| midfill | `midfill` | 25, 27, 49, 51, 64, 74 | 41/70/98 | 48 kHz | 18 | 6 |

- 会话结构沿用 runbook-corpus v1（3 导出/会话、≤900 s 硬窗口、模板播种冷启动、prepare 215 项基线 + 反例恢复、D1 路径修正、unit-before/after 断言、close quit exit 0）。
- stimulus 已生成（生成器复用 `make-stimulus-corpus.py`，A4-v70 逐位自检继承）：
  - `pilot/stimulus-treble96/`（15 MIDI + receipt.json）
  - `pilot/stimulus-midfill/`（18 MIDI + receipt.json）

## 2. 前置：96 kHz 能力核验（首个会话，单独审批）

1. 私有隔离冷启动（沿用受控套件），Options → Audio device 检查采样率列表是否含 **96 kHz**；
2. 若含：设为 96 kHz（可用设备类型内选择），确认状态 running；
3. **导出核验**：以 n87-v70 试导一次，检查 WAV 头 = 96 kHz / 24-bit / 双声道；结束后正常退出；
4. 若设备不支持 96 kHz：**停止 treble96 段**并登记（不得用重采样替代；48 kHz 已证高音区分音不足）；
   回退仅执行 midfill 段；
5. 核验结果与试导回执落盘为 s01 会话的 diag 记录（不产出正式单元）。

## 3. 采集后的分析

```bash
# 高音 96 kHz（--max-freq 40000；SNR 通道默认自 n>=72 生效）
python3 tools/pilot-partial-analysis.py --preset treble96 --batch <批次根> \
    --out <分析输出> --max-freq 40000

# 中低 48 kHz（默认口径）
python3 tools/pilot-partial-analysis.py --preset midfill --batch <批次根> --out <分析输出>
```

- 工具版本：`pilot-partial-analysis.py` SHA-256 `0d8e13d9f292bb88488bba9288d89fdd7df0ecc777ec33395d50233796e66ed2`
  （含 amendment-1/2 独立预测、amendment-3 待用于评估、`--max-freq`、`treble96`/`midfill` preset、动态采样率聚合）；
- 评估口径：可比较分音集（amendment-3）；设计区与全口径并列记录；
- 目标（诊断预期）：87/93/99/105/108 段 B 回收与参考斜率一致（3.04 倍/八度）；midfill 的 25/27/49/51 应显示比 24→28 / 48→60 线性插值更接近参考的曲率证据。

## 4. 门禁与纪律

- GUI 操作仅主会话逐次审批（windows-mcp）；执行前用户明确放行；
- 采集期间不修改 B 表、不修改分析判据；失败与偏差照实登记（含 96 kHz 不可用这一可能）；
- 数据归档沿用批次惯例（逐文件 SHA-256、manifest、四索引）；
- 本批次为**新登记验证数据**；旧 holdout 不复用、不作对照判决。
