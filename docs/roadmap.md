# Pianoteq 9 研究路线与证据状态

> 用途：维护研究产物入口、当前证据类别与进一步验证的进入条件；不是 devpiano 产品路线。
> 原始研究目标和旧Accepted记录可在输入Git修订/本机封存追溯。产物完成、数学可解释、内部算法已证实和生产工程通过不是同一状态。

## 当前工作与边界

Task 39-1 下游复核结果回流：封存原始音频、重建输入和双方旧文档；参考结果、方法、claims及manifest落库；以 [声学基准报告](acoustic_benchmark_report.md) 统一口径与旧主张处理。复算入口只读取现有文件，不能补证过去商业渲染条件。

REA/Ghidra用于有明确目标和真实工具记录的静态研究。本轮不重做完整商业DSP反编译、不修改二进制或 devpiano 音源。原路线的工具版本与槽位数字属于历史记录，不用当前安装版本或新假说覆盖；具体证据真实性仍须对应原始输出单独核对。

## 原研究产物入口

| 方向 | 原子阶段文件 | 当前状态边界 |
|---|---|---|
| Phase 1：琴槌与整音 | [1-1](phase1/phase1-1-rva-xrefs-evidence.md) / [1-2](phase1/phase1-2-hammer-mapping-decompilation.md) / [1-3](phase1/phase1-3-hammer-dynamics-spec.md) | 原记录/候选产物保留，解释受统一证据等级限制；内部实现等价和生产工程认证未建立 |
| Phase 2：音板与耗散 | [2-1](phase2/phase2-1-soundboard-anchors-evidence.md) / [2-2](phase2/phase2-2-filter-coefficient-decompilation.md) / [2-3](phase2/phase2-3-soundboard-acoustic-spec.md) | 原记录/候选产物保留，解释受统一证据等级限制；内部实现等价和生产工程认证未建立 |
| Phase 3：同音与衰减 | [3-1](phase3/phase3-1-unison-control-chain.md) / [3-2](phase3/phase3-2-beating-matrix-decompilation.md) / [3-3](phase3/phase3-3-unison-beating-spec.md) | 原记录/候选产物保留，解释受统一证据等级限制；内部实现等价和生产工程认证未建立 |
| Phase 4：开放弦与非发音段 | [4-1](phase4/phase4-1-sympathetic-anchors-evidence.md) / [4-2](phase4/phase4-2-resonance-pool-decompilation.md) / [4-3](phase4/phase4-3-sympathetic-system-spec.md) | 原记录/候选产物保留，解释受统一证据等级限制；内部实现等价和生产工程认证未建立 |
| Phase 5：张力与泛音时间轨迹 | [5-1](phase5/phase5-1-quadratic-blooming-anchors-evidence.md) / [5-2](phase5/phase5-2-nonlinear-mechanics-decompilation.md) / [5-3](phase5/phase5-3-quadratic-blooming-spec.md) | 原记录/候选产物保留，解释受统一证据等级限制；内部实现等价和生产工程认证未建立 |

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
