# Pianoteq 9 研究路线与证据状态

> 用途：维护研究产物入口、当前证据类别与进一步验证的进入条件；不是 devpiano 产品路线。
> 原始研究目标和旧Accepted记录可在输入Git修订/本机封存追溯。产物完成、数学可解释、内部算法已证实和生产工程通过不是同一状态。

## 当前工作与边界

**当前有效范围（2026-10-14，用户批准收口；有界验收已执行并消耗）**：midfill、interp-training 及 26/52/57 生产准入已完成，现行表含 17 实测锚点 + 2 文献外推节点。冻结该表，停止追加训练；[validation-interp2 预登记](../acoustic_lab/results/task39-2-official-reference-v2/pilot/validation-interp2-preregistration.json) 所述一次有界独立验收已完整执行并消耗：48/48 单元采集，唯一一次 guarded 判决为**证据不足**（32 个可评估单元全部达标；12 个 n88 单元参考侧分音匹配失败、4 个 n67-v47 单元可比分音不足；legacy 敏感性计数相同），未记通过。判决后保留常量与记录，不自动调参、扩采或补开替代验证；通过或证据不足均不认证全域或真实琴型。下列阶段记录只作历史依据，不构成续采授权；产品完成状态以 devpiano roadmap 为准。

当前方法工作另见 [runbook §8](../acoustic_lab/results/task39-2-official-reference-v2/pilot/runbook-validation-interp2.md#8-有界量测资格与诊断入口2026-10-14)：用户批准的有界资格修订已完成数值门禁与完整分类修复；合成负例仍揭示未分辨混合族假阳性，候选未获总体资格，保持原分析器默认、冻结表和原判决，不启动新采集。该修订只支持诊断与观察器能力边界，不把低残差拟合升级为物理弦身份。

Task 39-1 下游复核结果回流：封存原始音频、重建输入和双方旧文档；参考结果、方法、claims及manifest落库；以 [声学基准报告](acoustic_benchmark_report.md) 统一口径与旧主张处理。复算入口只读取现有文件，不能补证过去商业渲染条件。
2026-10-11 旧参考来源资格撤销：9.1.2 为第三方破解/补丁样本，停止执行及官方算法/声音归因，保留历史文件身份与数值。当前 [来源登记](../acoustic_lab/results/task39-2-official-reference-v2/provenance.json) 独立于旧 manifest；仅在已核验官方 9.2.5 的独立配置、完整状态和试用限制下建立新协议，不将版本切换当作 B 锚点准入。

历史阶段记录（2026-10-13）：官方 9.2.5 私有隔离采集完成 pilot v2 / register / corpus / anchors2 / bridge，最初 14 个准入锚点进入 devpiano 生产表；封闭验证一次性执行并消耗，amendment-1/2 重评 12/34 未达预登记指标。该结果保留为原参数与原口径的历史判决，不作为现行 17 锚点表的新验收；分析工具、runbook、预登记与重评产物保持原样。

参考资源裁决（2026-10-13，保持有效）：用户仅提供当前官方 Standard Trial；[官方手册](https://www.modartt.com/user_manual?product=pianoteq&lang=en)规定内部采样率上限 48 kHz，[官方 FAQ](https://www.modartt.com/faq?product=pianoteq)明确无 PRO 试用版。treble96 关闭为缺少合格高采样率参考环境，不列待办、不升采样冒充参考；当时选定的 [midfill](../acoustic_lab/results/task39-2-official-reference-v2/pilot/runbook-midfill.md) 已完成。85–108 的全域独立实测缺口作为本资源范围的限制保留，不因后续抽样通过而豁免。

P3 midfill 执行结果（2026-10-14）：6 个独立冷启动会话 / 18 单元全部形式验收（pre/post 参数断言漂移 0、215 项认证基线、独立核验 accepted、受保护 412 文件零差异、每会话 ≤900 s）；参考侧分音分析 **17/18 族通过**，n27-v98 登记不可准入（留出误差 +3.9→−8.7 cents 漂移、f1 38.800）；导出仅能经 GUI（RPC 7 个候选方法探测全部 function-not-found），菜单项需屏幕坐标点击。批次与分析输出归档于 devpiano 证据库 `phase39/task39-2/midfill-20261014-001725`（940 文件逐文件 SHA-256）。跨生产者（devpiano vs 参考）对照评估已于 2026-10-14 执行（批次 `cross-eval-20261014-010217`）：可比较口径（amendment-3/4）**12/18 通过**；失败全部为 n25/n27（24→28 插值段，B 相对参考 +7.5~8.0%，与 n26 诊断互证）；48→60 段 B_rel +8.6%（n49）/+19.4%（n51）一并登记；不回调参数、不放宽判据。

插值预研与后续实施（2026-10-14）：[预研报告](../acoustic_lab/results/task39-2-official-reference-v2/calibration/interpolation-research-20261014.md)基于当时 14 锚点比较插值方案，保留 log 线性并建议少量新训练锚点；[原 84 单元提案](../acoustic_lab/results/task39-2-official-reference-v2/calibration/interpolation-capture-proposal-20261014.json)后续已完成训练 36 单元及 validation-interp 48 单元，26/52/57 经准入、更正政策与生产回归进入当前表。validation-interp 原判决 46/48 保留；amendment-5 的 48/48 仅为已消耗集诊断。旧全分音 B_rel 的拍频回收偏置、低区条件级留出资格及预研证据保持，不再把历史提案写成未实施待办。


REA/Ghidra用于有明确目标和真实工具记录的静态研究。本轮不重做完整商业DSP反编译、不修改二进制或 devpiano 音源。原路线的工具版本与槽位数字属于历史记录，不用当前安装版本或新假说覆盖；具体证据真实性仍须对应原始输出单独核对。

## 原研究产物入口

| 方向 | 原子阶段文件 | 当前状态边界 |
|---|---|---|
| Phase 1：琴槌与整音 | [1-1](phase1/phase1-1-rva-xrefs-evidence.md) / [1-2](phase1/phase1-2-hammer-mapping-decompilation.md) / [1-3](phase1/phase1-3-hammer-dynamics-spec.md) | 原记录/候选产物保留，解释受统一证据等级限制；内部实现等价和生产工程认证未建立 |
| Phase 2：音板与耗散 | [2-1](phase2/phase2-1-soundboard-anchors-evidence.md) / [2-2](phase2/phase2-2-filter-coefficient-decompilation.md) / [2-3](phase2/phase2-3-soundboard-acoustic-spec.md) | 原记录/候选产物保留，解释受统一证据等级限制；内部实现等价和生产工程认证未建立 |
| Phase 3：同音与衰减 | [3-1](phase3/phase3-1-unison-control-chain.md) / [3-2](phase3/phase3-2-beating-matrix-decompilation.md) / [3-3](phase3/phase3-3-unison-beating-spec.md) | 原记录/候选产物保留，解释受统一证据等级限制；内部实现等价和生产工程认证未建立 |
| Phase 4：开放弦与非发音段 | [4-1](phase4/phase4-1-sympathetic-anchors-evidence.md) / [4-2](phase4/phase4-2-resonance-pool-decompilation.md) / [4-3](phase4/phase4-3-sympathetic-system-spec.md) | 原记录/候选产物保留，解释受统一证据等级限制；内部实现等价和生产工程认证未建立 |
| Phase 5：张力与泛音时间轨迹 | [5-1](phase5/phase5-1-quadratic-blooming-anchors-evidence.md) / [5-2](phase5/phase5-2-nonlinear-mechanics-decompilation.md) / [5-3](phase5/phase5-3-quadratic-blooming-spec.md) | 原记录/候选产物保留，解释受统一证据等级限制；内部实现等价和生产工程认证未建立 |
上述 Phase 1–5 的地址、字符串与切片均属于旧具体样本的历史记录，不因保留而恢复官方实现证明资格；公开理论和经独立官方文档核对的参数语义分别保留。

## 进一步研究的进入条件

1. **数据身份先固定**：版本、原始文件SHA、输入MIDI与实际生效参数分别记录；未知预设/拾音/增益不从模板或当前GUI prefs反推。
2. **量测先定义**：分音号、柔弦/第一分音/同音峰、时窗、功率/幅度、分辨能力和真正独立的验证条件在比较前固定。
3. **候选模型可证伪**：从固定输出建立分音族或包络假说，报告Hz/cents残差及窗口/边界敏感性；新 `B_eff` 不自动升级为内部参数。
4. **静态证据须完整链条**：字符串、分配大小和常量不能唯一证明状态更新算法；涉及实现等价需有相应数据流/调用/状态和独立行为证据，本轮未建立。
5. **工程落地独立验收**：数值稳定、Nyquist、生命周期和完整实时闭包必须由消费者验证；理论示例或未留receipt的编译声明不能代替工程通过。

本仓库只在真实研究需求出现时小步补证，不为封板结论重开所有阶段或建立通用平台。旧指数B、固定接触时间、机械能量权重和算法等价断言的当前处理以基准报告为准，不能继续作为新研究的强制验收目标。

## 资料与产品责任

轻量参考结果随Git保存，本机忽略封存与原始音频由散列追溯。原始汇编、地址、XRefs和作者注释保留原样，解释部分可纠错；不把历史记录的存在误称为当前验证。

实现、状态与后续任务只由 [devpiano roadmap](https://github.com/0xnayuta/devpiano/blob/main/docs/roadmap/roadmap.md) 管理。研究可以接收下游纠错，但不复制专有代码、不自动修改其DSP或自有文件格式，也不在本仓库维护另一套产品进度。
