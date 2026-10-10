# Phase 5-1 历史报告：二次方效应与泛音膨胀参数锚点检索

> **任务编号**：Phase 5-1  
> **原研究目标**：在 `binaries/Pianoteq 9.vst3plugin` (58.0 MiB) 中定位泛音膨胀（`Blooming Energy`、`Blooming Inertia`）与张力非线性（`Quadratic Effect`）相关参数的内存虚拟地址（VA/RVA），提取代码段交叉引用（XRefs），并在 43 KB 核心声学求解器中记录其内部槽位 ID 与函数边界。  
> **报告归档路径**：`docs/phase5/phase5-1-quadratic-blooming-anchors-evidence.md`  
> **复核状态**：**历史产物**（原记录“已通过验收 (Accepted)”仅为当时流程状态）。本轮 Task 39-1 未重做 Ghidra/反汇编复核：下文地址、机器码、XRefs 与槽位记录按原样保留为历史静态记录，既不因文档纠错升级为新认证，也不据此反向断言为假。相关等价主张对应[统一复核](../acoustic_benchmark_report.md#证据等级与旧主张处理)中的 `commercial-algorithm-equivalence`（not-established）。  
> **证据标注**：【官方语义】随附 9.1.2 英文手册；【静态记录】历史反汇编/地址记录（本轮未复核）；【经典理论】公开声学/钢琴构造常识；【候选模型】未经认证的解释、方程或数值；【工程】工程外推或建议，除注明外均未生产验证。统一口径：[统一复核与证据等级](../acoustic_benchmark_report.md#证据等级与旧主张处理)、[复算与原始数据保留](../acoustic_benchmark_report.md#复算与原始数据保留)。  

---

## 一、参数锚点历史记录 (Anchors)

【静态记录】通过全二进制特征扫描，在 `.text` 节中定位到如下锚点。地址、偏移与终止符按原样保留，本轮未复核；“语义角色”列为当时分析者的解释性标注，字符串存在只证明相应名称被携带：

| 参数键名 / 标签 | 语义角色 | 物理文件偏移 (Raw Offset) | 相对虚拟地址 (RVA) | 绝对虚拟地址 (VA) | 结尾终止符 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `Quadratic Effect` | 二次方非线性效应全名 | `0x00046c88` | `0x00047888` | `0x0000000180047888` | `\0` (有效独立串) |
| `Blooming Energy` | 泛音绽放能量深度全名 | `0x00058828` | `0x00059428` | `0x0000000180059428` | `\0` (有效独立串) |
| `Blooming Inertia` | 泛音绽放时间惯性全名 | `0x0002a068` | `0x0002ac68` | `0x000000018002ac68` | `\0` (有效独立串) |
| `Blooming` | 绽放 UI 缩写短别名 | `0x00018490` | `0x00019090` | `0x0000000180019090` | `\0` (有效独立串) |

【官方语义】随附 9.1.2 英文手册对 Blooming 给出定性说明：该参数最初为钢鼓而设计，也可用于其他乐器；“Blooming energy”控制从低阶泛音向高阶泛音转移的能量多少，“Blooming inertia”控制该转移的速度（惯性越大转移越慢）。手册**未**出现 `Quadratic Effect` 参数词条（字符串扫描命中，但公开条目缺位），其公开语义只能按“参数名存在”处理。

---

## 二、代码段交叉引用 (XRefs) 历史记录

【静态记录】历史记录称在 `.text` 节中发现 **30 处** 指令级交叉引用，形式为 x86-64 `lea rdx, [rip + disp32]`。计数、地址与机器码按原样保留，本轮未复核。

### 1. 43 KB 区间中的控制链记录 (`0x180385d56` ~ `0x180387035`)（“核心求解器”为分析者标签）
- **引用 `Blooming Energy` (VA `0x180059428`)**：
  - 指令地址：`0x0000000180385d56` (RVA `0x00385d56`)
  - 汇编：`lea rdx, [rip - 0x32c935]`
- **引用 `Blooming Inertia` (VA `0x18002ac68`)**：
  - 指令地址：`0x0000000180385e2a` (RVA `0x00385e2a`)
  - 汇编：`lea rdx, [rip - 0x35b1c9]`
- **引用 `Quadratic Effect` (VA `0x180047888`)**：
  - 指令地址：`0x0000000180386fa9` (RVA `0x00386fa9`)
  - 汇编：`lea rdx, [rip - 0x33f728]`
  - 指令地址：`0x0000000180387013` (RVA `0x00387013`)
  - 汇编：`lea rdx, [rip - 0x33f792]`

### 2. 整音面板多预设模板同步绑定链 (`0x1806c9b7a` ~ `0x1806d4cb4`)
【候选模型】原文称“在整音主配置函数中，`Quadratic Effect` 与 `Blooming Energy` 被作为独立物理动力学特征成对注入各个乐器预设模板”。引用地址落在预设/模板装配区域，只能说明这些名称在该区域被携带；**不证明**“独立物理动力学特征”或“成对注入”的语义。

---

## 三、43 KB 区间内部槽位 (Internal Slot IDs) 历史记录

【静态记录】以下汇编与槽位立即数按原样保留，本轮未复核；行内注释为当时分析者标注，不构成认证结论。它们记录“哪些立即数与字符串在同一代码块中被连续处理”，不证明槽位号即官方参数编号、官方取值范围或任何专有实现：

```assembly
; === 1. 槽位 0x3F (十进制 63): Blooming Energy (泛音膨胀能量深度) ===
180385d46:  mov    $0x3f, %edx             ; edx = Slot 63 (Blooming Energy)
180385d4b:  mov    %rsi, %rcx              ; rcx = DesignContext*
180385d4e:  call   0x1803de5b0             ; 获取/初始化槽位节点
180385d53:  mov    %rax, %rdi
180385d56:  lea    -0x32c935(%rip), %rdx   ; rdx = "Blooming Energy" (VA 0x180059428)
...
180385d95:  call   0x1804a9f30             ; 绑定槽位属性与数值

; === 2. 槽位 0x41 (十进制 65): Blooming Inertia (泛音膨胀时间惯性) ===
180385e1a:  mov    $0x41, %edx             ; edx = Slot 65 (Blooming Inertia)
180385e1f:  mov    %rsi, %rcx
180385e22:  call   0x1803de5b0
180385e27:  mov    %rax, %rdi
180385e2a:  lea    -0x35b1c9(%rip), %rdx   ; rdx = "Blooming Inertia" (VA 0x18002ac68)
...
180385e69:  call   0x1804a9f30             ; 绑定槽位属性与数值

; === 3. 槽位 0x5E (十进制 94): Quadratic Effect (二次方张力非线性效应) ===
180386f99:  mov    $0x5e, %edx             ; edx = Slot 94 (Quadratic Effect)
180386f9e:  mov    %rsi, %rcx
180386fa1:  call   0x1803de5b0
180386fa6:  mov    %rax, %rdi
180386fa9:  lea    -0x33f728(%rip), %rdx   ; rdx = "Quadratic Effect" (VA 0x180047888)
...
180386fe8:  call   0x1804a9f30             ; 绑定槽位属性与数值
```

### 核心槽位全景对应（历史观察）
- `Slot 33 (0x21)`: `Unison Width`
- `Slot 34 (0x22)`: `Unison Balance`
- `Slot 63 (0x3F)`: **`Blooming Energy`**
- `Slot 65 (0x41)`: **`Blooming Inertia`**
- `Slot 81 (0x51)`: `Impedance`
- `Slot 82 (0x52)`: `Impedance Cutoff`
- `Slot 84 (0x54)`: `Impedance Slope`
- `Slot 88 (0x58)`: `Sympathetic Resonance`
- `Slot 90 (0x5A)`: `Duplex Scale Resonance`
- `Slot 94 (0x5E)`: **`Quadratic Effect`**

【撤回】原文由此宣称“成功定位了……权威 RVA 锚点与内部槽位”。立即数/字符串的相邻处理不能确立“权威”，也不能把槽位号升级为官方映射；该归属与[统一复核](../acoustic_benchmark_report.md#证据等级与旧主张处理)的 `commercial-algorithm-equivalence`（not-established）一致。参数的真实取值范围与默认值本轮未复核（历史草案与参数字典的记录互相冲突，也不自动统一）。

---

## 四、Phase 5-2 衔接（历史计划）

当时的衔接计划为：继续定向分析音频渲染数据流，设想琴弦几何张力调制与瞬时音高漂移形式、双参数滞后膨胀包络，产出 `docs/phase5/phase5-2-nonlinear-mechanics-decompilation.md`。该产物已归档，其当前状态为历史记录加未认证候选模型；本页的槽位与 XRefs 记录本身仍属未复核的历史观察。
