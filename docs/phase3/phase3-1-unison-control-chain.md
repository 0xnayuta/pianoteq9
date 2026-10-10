# Phase 3-1 验收报告：同音失谐参数控制链定位与交叉引用取证

> **任务编号**：Phase 3-1  
> **研究目标**：在 `binaries/Pianoteq 9.vst3plugin` (58.0 MiB) 中定位同音多弦调律与拍频控制参数（`unison_width`、`Unison Width`、`Unison Balance`）的内存虚拟地址（VA/RVA），提取代码段交叉引用（XRefs），并在核心声学设计求解器中追踪控制三根同音弦（Trichord）独立失谐量 $\Delta f_1, \Delta f_2, \Delta f_3$ 的控制链路。  
> **报告归档路径**：`docs/phase3/phase3-1-unison-control-chain.md`  
> **当前状态**：历史地址/切片保留；旧 Accepted 不等于三弦分配方程、频率中心或拍频已被认证。
> **复核入口**：[统一证据等级与旧主张处理](../acoustic_benchmark_report.md#证据等级与旧主张处理)。作者在表内/汇编中的用途注释为原解释，本轮未重新取证。

---

## 一、同音参数物理内存锚点全景表 (Unison Parameter Anchors)

以下是原稿声称由特征扫描得到的同音字符串地址记录，本轮原样保留而不新认证其全部真实性或功能角色：

| 参数键名 / 标签 | 语义角色 | 物理文件偏移 (Raw Offset) | 相对虚拟地址 (RVA) | 绝对虚拟地址 (VA) | 结尾终止符 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `unison_width` | 同音失谐宽度主键名 | `0x0005f3c0` | `0x0005ffc0` | `0x000000018005ffc0` | `\0` (有效独立串) |
| `Unison Width` | 同音失谐宽度 UI 标签 | `0x0001f700` | `0x00020300` | `0x0000000180020300` | `\0` (有效独立串) |
| `Unison Balance` | 同音平衡 UI 标签 | `0x0008c988` | `0x0008d588` | `0x000000018008d588` | `\0` (有效独立串) |
| `Unison Fine` | 同音微调精细别名 | `0x00085f58` | `0x00086b58` | `0x0000000180086b58` | `\0` (有效独立串) |
| `Unison` | UI 紧凑缩写短名 | `0x0007d684` | `0x0007e284` | `0x000000018007e284` | `\0` (有效独立串) |
| `Unis` | 超短紧凑别名 | `0x000578fc` | `0x000584fc` | `0x00000001800584fc` | `\0` (有效独立串) |
| `UnisF` | 微调超短紧凑别名 | `0x00086440` | `0x00087040` | `0x0000000180087040` | `\0` (有效独立串) |

---

## 二、代码段交叉引用 (XRefs) 深度取证记录

在 `.text` 节中执行滑窗匹配，共发现 **22 处** 高置信度指令级交叉引用：

### 1. 关键排布发现：整音主配置函数最前序锚点 (`unison_width`)
- **引用指令地址**：`0x00000001806c4d96` (RVA `0x006c4d96`)
- **机器码**：`48 8d 15 23 b2 99 ff`
- **反汇编**：`lea rdx, [rip - 0x664ddd]` $\longrightarrow$ 目标 VA `0x18005ffc0` (`unison_width`)
- **原稿对装配次序的用途推断**：
  原稿将 `VoicingSetup_Master` (`0x1806c49f0`) 中以下加载次序解释为物理因果链；次序记录保留，该用途解释不能仅由字符串加载顺序证明：
  1. `0x1806c4d96`: `unison_width`（首先设定琴弦微失谐几何状态）
  2. `0x1806c4e22`: `impedance_cutoff`（设定音板高频耗散边界）
  3. `0x1806c4e8a`: `hammer_hardness_*`（设定击弦动力学硬度激振源）

### 2. 43 KB 核心声学设计求解器中的控制链 (`0x1803846d1` ~ `0x1803848bb`)
在求解器内部，连续高频读取了同音调律参数，并分配专有内部槽位：
- `0x1803846d1`: `lea rdx, [rip - 0x3643d8]` $\longrightarrow$ `Unison Width` (`0x180020300`)
- `0x180384780`: `lea rdx, [rip - 0x364487]` $\longrightarrow$ `Unison Width` (`0x180020300`)
- `0x18038482f`: `lea rdx, [rip - 0x2f72ae]` $\longrightarrow$ `Unison Balance` (`0x18008d588`)
- `0x180384899`: `lea rdx, [rip - 0x2f7318]` $\longrightarrow$ `Unison Balance` (`0x18008d588`)

---

## 三、43 KB 求解器内部槽位 (Internal Slot IDs) 确认

原稿根据立即数提出下列槽位绑定解释。切片及数值不改写，本轮没有进一步证明其后续渲染读取和三弦状态更新：

```assembly
; === 1. 槽位 0x21 (十进制 33): Unison Width (同音失谐宽度) ===
1803846c1:  mov    $0x21, %edx             ; edx = Slot 33 (Unison Width)
1803846c6:  mov    %rsi, %rcx              ; rcx = DesignContext*
1803846c9:  call   0x1803de5b0             ; 获取/初始化槽位对象
1803846ce:  mov    %rax, %rdi
1803846d1:  lea    -0x3643d8(%rip), %rdx   ; rdx = "Unison Width" (VA 0x180020300)
1803846e2:  lea    -0x32c1ed(%rip), %rdx   ; rdx = "Unis" (VA 0x1800584fc)
1803846f3:  lea    -0x306476(%rip), %rdx   ; rdx = "Unison" (VA 0x18007e284)
...
180384741:  call   0x180360ad0             ; 装配入参数描述符容器

; === 2. 槽位 0x22 (十进制 34): Unison Balance (同音平衡与微调) ===
180384770:  mov    $0x22, %edx             ; edx = Slot 34 (Unison Balance)
180384775:  mov    %rsi, %rcx
180384778:  call   0x1803de5b0
18038477d:  mov    %rax, %rdi
180384780:  lea    -0x364487(%rip), %rdx   ; rdx = "Unison Width" / "Unison Balance"
1803847a2:  lea    -0x2fdc51(%rip), %rdx   ; rdx = "Unison Fine" (VA 0x180086b58)
1803847b4:  lea    -0x2fd77b(%rip), %rdx   ; rdx = "UnisF" (VA 0x180087040)
...
1803847f0:  call   0x180360ad0             ; 装配入参数描述符容器
```

---

## 四、公开同音语义与撤回的分配外推

公开 Advanced Tuning 定义：Unison width 为同一音三弦最高与最低频差；Unison balance 调整中弦频率从最低(-1)到最高(+1)，0为公开出厂描述。显示单位、范围和实际控制映射需要独立核对，不能混用Hz、cents与归一化量。

原稿的偏置表达只是在槽位/字符串记录之外提出的候选重构，没有完整状态数据流证据；其端点行为也不能仅凭 Balance 名称认证为公开语义的实现。本页不再提供可直接集成的频率分配公式。

两个频率分量的数学频差可形成拍频，但整体混合包络未唯一识别为3.56Hz，全琴固定宽度及旧能量比例不采用。最强混合峰、候选族拟合量和中心弦必须区分，当前结果只看 [声学基准报告](../acoustic_benchmark_report.md)。

## 五、后续补证边界

上方地址、机器码和切片并未因限制解释而被抹去或新认证；若继续研究，需补具体对象/状态读取与频率端点、身份和辐射行为，而非从常量推整套矩阵。当前模型限制见 [同音候选规格](phase3-3-unison-beating-spec.md)，本轮不修改 devpiano DSP。
