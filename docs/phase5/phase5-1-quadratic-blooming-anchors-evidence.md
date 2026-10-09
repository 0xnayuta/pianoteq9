# Phase 5-1 验收报告：二次方效应与泛音膨胀参数锚点取证

> **任务编号**：Phase 5-1  
> **研究目标**：在 `binaries/Pianoteq 9.vst3plugin` (58.0 MiB) 中定位大动态琴弦几何二次方张力非线性效应（`Quadratic Effect`）与泛音时间滞后膨胀动力学（`Blooming Energy`、`Blooming Inertia`）参数的内存虚拟地址（VA/RVA），提取代码段交叉引用（XRefs），并在 43 KB 核心声学求解器中逆向其内部槽位 ID 映射与函数边界。  
> **报告归档路径**：`docs/phase5/phase5-1-quadratic-blooming-anchors-evidence.md`  
> **执行状态**：**已通过验收 (Accepted)**  

---

## 一、二次方非线性与泛音膨胀物理内存锚点全景表 (Anchors)

通过全二进制特征扫描，在 `.text` 节中定位到如下核心参数的权威物理锚点：

| 参数键名 / 标签 | 语义角色 | 物理文件偏移 (Raw Offset) | 相对虚拟地址 (RVA) | 绝对虚拟地址 (VA) | 结尾终止符 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `Quadratic Effect` | 二次方非线性效应全名 | `0x00046c88` | `0x00047888` | `0x0000000180047888` | `\0` (有效独立串) |
| `Blooming Energy` | 泛音绽放能量深度全名 | `0x00058828` | `0x00059428` | `0x0000000180059428` | `\0` (有效独立串) |
| `Blooming Inertia` | 泛音绽放时间惯性全名 | `0x0002a068` | `0x0002ac68` | `0x000000018002ac68` | `\0` (有效独立串) |
| `Blooming` | 绽放 UI 缩写短别名 | `0x00018490` | `0x00019090` | `0x0000000180019090` | `\0` (有效独立串) |

---

## 二、代码段交叉引用 (XRefs) 深度取证记录

在 `.text` 节中执行滑窗匹配，共发现 **30 处** 高置信度指令级交叉引用，全部采用 x86-64 `lea rdx, [rip + disp32]` 相对寻址：

### 1. 43 KB 核心声学设计求解器中的控制链 (`0x180385d56` ~ `0x180387035`)
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
- 在整音主配置函数中，`Quadratic Effect` 与 `Blooming Energy` 被作为独立物理动力学特征成对注入各个乐器预设模板。

---

## 三、43 KB 求解器内部槽位 (Internal Slot IDs) 映射链

通过反汇编分析核心求解器代码块，锁定了二次方效应与泛音膨胀在声学设计网络中的底层槽位编号：

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

### 核心声学求解器完整物理槽位全景映射
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

---

## 四、Phase 5-2 衔接指引

在 Phase 5-1 成功定位了二次方效应（Slot 94）与泛音膨胀（Slot 63/65）的权威 RVA 锚点与内部槽位后，**Phase 5-2** 将聚焦于：
1. 定向反编译单音琴弦振动回路中利用振幅平方项 $\Delta y^2$ 调制张力的离散差分方程；
2. 提取双参数（能量与惯性）驱动高阶泛音时变增益的二阶低通包络滤波器方程；
3. 输出 `docs/phase5/phase5-2-nonlinear-mechanics-decompilation.md`。
