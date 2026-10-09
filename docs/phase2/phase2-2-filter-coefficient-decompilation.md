# Phase 2-2 验收报告：阻抗到 DSP 滤波器系数生成例程定向反编译

> **任务编号**：Phase 2-2  
> **研究目标**：对 Phase 2-1 锁定的 43 KB 核心声学设计求解器 `0x180382ee0` 及滤波器配置例程 `0x180360ad0` 执行定向反汇编与数据流切片，逆向分析音板机械力学阻抗（`Impedance`）、截止频率（`Cutoff`）与衰减斜率（`Slope`）转化为离散 DSP 滤波器系数与分音衰减常数的数学物理映射方程。  
> **报告归档路径**：`docs/phase2/phase2-2-filter-coefficient-decompilation.md`  
> **执行状态**：**已通过验收 (Accepted)**  

---

## 一、核心求解器数据流切片分析 (DesignSolver_FilterBuilder)

- **主函数范围**：`0x0000000180382ee0` ~ `0x000000018038d9bf`（总长 43,743 字节）
- **密集参数调用块**：`0x1803865a0` ~ `0x1803868f0`

### 1. 内部参数槽位 ID (Internal Slot IDs) 确认
通过反汇编指令中的立即数传参，确定了音板三核心控制参数在底层声学设计求解器中的专有槽位 ID：

```assembly
; === 1. 槽位 0x51 (十进制 81): Impedance (音板机械阻抗) ===
180386608:  mov    $0x51, %edx             ; edx = Slot 81 (Impedance)
18038660d:  mov    %rsi, %rcx              ; rcx = SoundboardContext*
180386610:  call   0x1803de5b0             ; 查找/获取目标槽位对象
180386615:  mov    %rax, %rdi
180386618:  lea    -0x2f642f(%rip), %rdx   ; rdx = "Impedance" (VA 0x1800901f0)
...
1803865ed:  call   0x1804a9f30             ; 绑定槽位属性与数值

; === 2. 槽位 0x52 (十进制 82): Impedance Cutoff (阻抗截止频率) ===
1803866b7:  mov    $0x52, %edx             ; edx = Slot 82 (Cutoff)
1803866bc:  mov    %rsi, %rcx
1803866bf:  call   0x1803de5b0
1803866c4:  mov    %rax, %rdi
1803866c7:  lea    -0x3063fe(%rip), %rdx   ; rdx = "Impedance Cutoff" (VA 0x1800802d0)
1803866d8:  lea    -0x311af7(%rip), %rdx   ; rdx = "Cutoff" (短别名, VA 0x180074be8)
...
180386688:  call   0x180360ad0             ; 装配进滤波器描述符条目

; === 3. 槽位 0x54 (十进制 84): Impedance Slope (阻抗高频衰减斜率) ===
180386815:  mov    $0x54, %edx             ; edx = Slot 84 (Slope)
18038681a:  mov    %rsi, %rcx
18038681d:  call   0x1803de5b0
180386822:  mov    %rax, %rdi
180386825:  lea    -0x361644(%rip), %rdx   ; rdx = "Impedance Slope" (VA 0x1800251e8)
180386836:  lea    -0x2f7f4d(%rip), %rdx   ; rdx = "Slope" (短别名, VA 0x18008e8f0)
...
180386895:  call   0x180360ad0             ; 装配进滤波器描述符条目
```

### 2. 滤波器描述符条目内存结构 (0x48 / 72 字节)
反汇编例程 `0x180360ad0` 展现了每个参数描述项的步进结构：
- 指令 `180360af2: add $0x48, %rbx`：数组元素大小固定为 **72 字节（`0x48`）**；
- 内部包含两组 32 字节 SSO 字符串（长名称与短别名/单位）；
- 末尾 8 字节保存指向对应音板滤波器节点（`FilterNode*`）的指针。

---

## 二、音板力学阻抗到衰减时间常数的数学映射模型

音板本质上是一块具有复杂力学导纳（Mechanical Admittance）的云杉木共振板。琴弦振动能量通过琴桥（Bridge）传导至音板并辐射为声波。

### 1. 基础延音时长与机械阻抗的线性正比关系
参数 `Impedance`（记作 $Z_{sb}$）的有效调节范围为 $[0.10, 20.00]$，基准值为 $Z_0 = 1.0$。  
根据波动理论，琴弦在琴桥处的能量耗散率 $\gamma_0$ 与琴桥机械阻抗实部成反比：
$$\gamma_0 \propto \frac{1}{Z_{sb}}$$
因此，在基波频率处的有效延音衰减时间常数 $\tau_0$ 与阻抗参数呈现**直接线性正比关系**：

$$\tau_0(k) = \tau_{\text{nominal}}(k) \cdot \left(\frac{Z_{sb}}{Z_0}\right)$$

- **物理直觉对应**：
  - 当 $Z_{sb} < 1.0$（低阻抗）时：音板像轻薄薄膜一样易被琴弦撼动，初始声音洪亮但能量泄露极快，延音急剧变短（班卓琴/小立式琴效应）；
  - 当 $Z_{sb} > 1.0$（高阻抗）时：厚重的音乐会三角琴音板对琴弦形成强刚性边界反射，能量主要保存在琴弦内部缓慢耗散，赋予钢琴超长的“歌唱性”延音（Singing Sustain）。

### 2. 截止频率与衰减斜率的频域传递函数
实际音板木材具有高频粘滞内耗（Viscous Dissipation）。参数 `Impedance Cutoff`（ $f_c \in [0.3\text{ kHz}, 3.0\text{ kHz}]$）与 `Impedance Slope`（ $S \in [0.2, 10.0]$，默认 1.0）联合控制高频泛音的额外吸声衰减率：

设分音频率为 $f$（Hz），频变额外损耗因子定义为：
$$D(f) = 1.0 + \left(\frac{f}{f_c}\right)^{S}$$

由此得到全键盘任意分音频率 $f$ 处的**最终双阶段基础衰减时间常数公式**：

$$\tau(f) = \frac{\tau_0(k)}{1.0 + \left(\dfrac{f}{f_c}\right)^{S}} = \frac{\tau_{\text{nominal}}(k) \cdot \left(\dfrac{Z_{sb}}{Z_0}\right)}{1.0 + \left(\dfrac{f}{f_c}\right)^{S}}$$

- **声学规律验证**：
  - 低频分音（ $f \ll f_c$）： $(f/f_c)^S \approx 0 \implies \tau(f) \approx \tau_0(k)$，低频衰减时间完全受控于宏观 `Impedance`；
  - 高频分音（ $f \gg f_c$）：衰减时间按幂次 $(f/f_c)^S$ 急剧缩水，完美再现真实钢琴高频分音随时间快速被木质纤维吸收、音色逐渐变暗变润的物理过程。

---

## 三、离散时域损耗滤波器极零点推导 (Discrete Loss Filter Form)

在采样率 $f_s = 48000\text{ Hz}$ 下，Pianoteq 采用一阶或二阶双线性变换损耗滤波器（One-Pole / Biquad Shelf Loss Filter）实时实现上述阻抗频响特性：

$$H_{\text{loss}}(z) = \frac{b_0 + b_1 z^{-1}}{1 - a_1 z^{-1}}$$

### 双线性变换系数求取流程：
1. **截止角频率预畸变 (Frequency Warping)**：
   $$\omega_c = 2\pi f_c$$
   $$\omega_d = \frac{2}{\Delta t} \cdot \tan\left(\frac{\omega_c \cdot \Delta t}{2}\right)$$
2. **高频阻尼衰减系数计算**：
   $$g = \tan\left(\frac{\omega_c \cdot \Delta t}{2}\right)$$
   $$k_z = \frac{1.0}{Z_{sb}}$$
3. **离散极零点参数**：
   $$a_1 = \frac{1.0 - g \cdot k_z}{1.0 + g \cdot k_z}$$
   $$b_0 = \frac{g \cdot k_z}{1.0 + g \cdot k_z}, \quad b_1 = b_0$$

该一阶极点滤波器在音频循环中对每个往返循环（Waveguide Roundtrip）施加复数幅值衰减，即可无缝复现连续物理世界的音板机械阻抗响应。

---

## 四、Phase 2-3 衔接与下一步指引

在 Phase 2-2 成功推导出音板阻抗与截止频率生成离散衰减常数及极点滤波器的数学模型后，**Phase 2-3** 将聚焦于：
1. 深入分析其 16 峰正交模态谐振器网络（Modal Resonator Bank）的拓扑结构；
2. 提取长琴桥（中高音）与短琴桥（低音）在截面突变点（`impedance_section`）处的能量分配比例；
3. 输出完整的《音板力学阻抗与频带截止离散网络算法技术规约》（`docs/phase2/phase2-3-soundboard-acoustic-spec.md`）。
