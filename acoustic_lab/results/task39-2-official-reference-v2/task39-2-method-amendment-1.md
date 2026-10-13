# Task 39-2 方法修订 1：独立预测实现与验证判据冻结

- 登记：2026-10-13（**在修正方法重评执行之前登记**，见 §4 时序）。
- 触发：2026-10-13 只读审计（`devpiano-evidence` 收口纠偏）发现两处"验证所用方案与预登记记录不一致"：
  1. 分析工具的单点 leave-one-partial-out 不满足预登记 `physical_admission.fitting_minimum`；
  2. 跨生产者验证的归一化分音比口径未在打开封闭验证集前明确冻结。
- 性质：**方法修订**。不改写 `task39-2-preregistration-v2.json` 原文本（历史原件保留），本文件补充实现细则与评估口径，对其后的全部分析与判决生效。
- 判据数值不放宽、不收紧：`RMS <= 1 cent`、`max <= 3 cents`、`B` 散布 `<= 10%`、`minimum_identified_partials >= 5` 等保持原样；验证数据不得用于调参（原 `holdout_policy` 保持）。

---
## 1. 偏差事实（修正前实现）

预登记 `physical_admission.fitting_minimum` 原文（历史原件保持只读）：

> use >=3 identified training partials and >=2 untouched partials for prediction;
> re-identify heldout peaks without full-data nearest-peak assignments

修正前工具（`pilot/tools/pilot-partial-analysis.py`，工作区版本 SHA-256 `9436c4f0…`，与 `anchors2-20261013-090249` 归档副本逐位一致）的实现：

1. 先以全数据（`staged_match_multi` + `match_partials(mode="nearest")`）锁定全套分音号与观测峰；
2. 再对每个分音做单点留出（每次仅 1 个），留出值**直接取全数据配对锁定的峰**；
3. 训练拟合以**全数据拟合解**为初值。

即：留出数量不足（1 < 2）、留出峰未独立重新识别、初值含留出信息。该实现能证明给定配对下的自洽性，不能替代预登记要求的独立预测检验。

历史版本链（供索引）：`2a2fba30`（register 分析）-> `7335c23d`（corpus 前置，含默认 SNR=25 与防呆）-> `9436c4f0`（新增 anchors2 preset，当前工作区基版）。

## 2. 修订后的实现（冻结）

### 2.1 独立留出集

- 单元已识别分音数为 `N`；留出大小 `h = max(2, N // 5)`；
- 留出索引确定性均匀选取（工具以 `np.linspace` 的中间点取整给出，指示位非随机数，可在任意机器复现）；
- 训练集 = 其余 `N - h` 个分音；`N - h < 3` 时该单元的独立预测记为 `insufficient_training_partials`（失败登记，不产出指标）。

### 2.2 训练拟合（无全数据解泄漏）

- 训练拟合初值取 `(theory, seed)`：`theory` 为该单元的名义基频（A4 与十二平均律，非数据拟合值），`seed` 遍历该单元适用的种子表（低中音区 `DEFAULT_SEEDS`；高音区 `EXTENDED_SEEDS`，沿用既有规则）；
- 多起点中取训练集残差最大绝对值最小者；**不使用全数据拟合解作为初值**。

### 2.3 留出峰的独立重新识别

对每个留出分音 `n`：

- 用训练拟合模型预测 `f_pred(n) = n * f1_train * sqrt((1 + B_train * n^2) / (1 + B_train))`；
- 在**原始谱峰表**（`spectral_peaks` 输出，未经全数据配峰）中，按预测位置搜索 `|1200 * log2(f_peak / f_pred)| <= 50 cents` 窗口；
- 合格峰规则与主导匹配一致：`rel >= 1e-7`，或（高音区 SNR 通道开启时）`snr >= min_snr 且 rel >= 1e-9`；
- 窗口内取 `rel` 最强合格峰为重新识别的观测 `f_pick`，误差 `= 1200 * log2(f_pick / f_pred)`；
- 窗口内无合格峰记 `unresolved`（该点失败；**不允许**回退到全数据配对值）。

### 2.4 单元指标（替代原字段）

- `independent_max_cents` / `independent_rms_cents`：全部留出点误差的最大值与 RMS（跨点不跨单元）；
- `independent_status`：`ok` / `insufficient_training_partials` / `training_fit_failed` / `no_holdout_peak_reidentified`；
- 工具内**干净切换**：删除原 `max_holdout_cents` / `rms_holdout_cents` / `leave_one_out_residual_cents` 字段，不保留旧名别名；逐点明细写入 `independent_prediction.details`。
- 训练残差（`max_residual_cents` / `rms_residual_cents`，全数据自洽指标）保留并列示，供诊断区分"配对质量"与"预测质量"。

### 2.5 跨生产者验证评估口径（冻结）

- **判据口径 = 归一化分音比**：对每个共同识别分音 `n`，
  `err(n) = 1200 * log2( (f_dev(n) / f_dev(m)) / (f_ref(n) / f_ref(m)) )`，
  基准分音 `m` 默认 `1`；当任一侧不可识别 `n=1`（如极低音基频低于工具 40 Hz 下限）时，`m` 取**两侧共同可识别的最小分音号**并在单元记录中标注 `reference_partial`；
  单元指标 `norm_rms` / `norm_max`；判据 `norm_rms <= 1.0` 且 `norm_max <= 3.0`（cents）。
- 语义：归一化消去参考（Flat、无拉伸）与 devpiano（等律 + 逐键拉伸）的调律基础差异，只检验非谐性/分音相对位置——即"独立分音上的预测误差"在本验证语境下的可操作形式。
- **绝对频率口径**（`rms_cents` / `max_cents`）仅作诊断记录，不作为判据；其偏置来源（调律基准差）如实并列。
- 双侧分析均使用同一工具、同一参数（含 SNR 通道规则）；峰识别互不引用对方结果。
- 冻结时点：**本修订登记于修正方法重评之前**；重评结果不得反向调整本口径、判据或上述实现细则。

## 3. 生效范围

对以下集合全部以修订后方法重新分析（只读既有归档 WAV；不重新渲染、不重新采集、不调参）：

1. 全键 176 渲染（devpiano，A4=440）：锚点 B/f1 回收、双率一致性、邻键顺序、非拍频子集口径（明确落盘）；
2. 封闭验证集 48 单元（参考侧 48 + devpiano 侧 48）：归一化判据重评；
3. 已归档族质量重验：pilot-v2 / register / corpus / anchors2 / bridge 单元独立预测指标重算，核对"族通过"结论是否维持。

结果作为 `closure-revalidation` 批次归档；首次评估（原 LOO 方法）与其结论**并列保留**、不替换、不删除，两者差异在批次报告中并列。

## 4. 时序声明

- 本文件先于任何修正后重评落盘；
- 重评期间不修改本文件的 §2 内容；如需再次修订，登记 amendment 2；
- 原 `task39-2-preregistration-v2.json`、`calibration-plan-v1.md`、`anchors-v3.md` 与既有批次报告均不回写。

## 5. 工具版本记录

- 修正前：`pilot-partial-analysis.py` SHA-256 `9436c4f0193fa1a652808265eb2fd828d796547ad6e438e445bdd479adf6d0f8`（当前工作区及 anchors2 归档副本）。
- 修正后：`pilot-partial-analysis.py` SHA-256 `6b0239c1be12804536aef763fccfe608fa91028a4c0d4c25542d7867c5ed3b36`（独立留出预测实现；重评批次与归档中记录此版本）。
