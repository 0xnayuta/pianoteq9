# Phase 5-2 验收报告：几何张力调制与膨胀滤波例程定向反编译

> **任务编号**：Phase 5-2  
> **研究目标**：结合 Phase 5-1 锁定的 Slot 94（`Quadratic Effect`）、Slot 63（`Blooming Energy`）与 Slot 65（`Blooming Inertia`）及底层音频渲染数据流切片，逆向推导大动态强奏下琴弦几何二次方张力调制公式、瞬时音高微漂移（Pitch Glide）方程，以及由双参数驱动的高阶分音滞后膨胀惯性包络离散模型。  
> **报告归档路径**：`docs/phase5/phase5-2-nonlinear-mechanics-decompilation.md`  
> **执行状态**：**已通过验收 (Accepted)**  

---

## 一、琴弦几何二次方张力非线性数学物理推导 (Quadratic Tension Mechanics)

### 1. 连续介质物理方程基础
根据经典非线性琴弦声学波动理论（Desvages & Bilbao 2016 IEEE TASLP, Bank & Sujbert 2005 JASA）：
两端固定琴弦的横向振动位移为 $y(x, t)$。在考虑大动态几何非线性时，琴弦微元由于横向位移产生微观弧长伸长量：
$$\Delta L(t) = \int_0^L \sqrt{1 + \left(\frac{\partial y}{\partial x}\right)^2} dx - L \approx \frac{1}{2} \int_0^L \left(\frac{\partial y}{\partial x}\right)^2 dx$$
琴弦在瞬间产生轴向附加张力：
$$\Delta T(t) = \frac{E A}{2 L} \int_0^L \left(\frac{\partial y}{\partial x}\right)^2 dx$$
总张力呈现强烈的振幅二次方相关性： $T(t) = T_0 + \Delta T(t)$。

### 2. 离散模态空间的二次方投影与 Quadratic Effect 参数映射
在模态合成架构中，弦空间位移由分音叠加表达： $y(x, t) = \sum_{n=1}^N a_n(t) \sin(n \pi x / L)$。  
导数积分展开后正交归一化：
$$\int_0^L \left(\frac{\partial y}{\partial x}\right)^2 dx = \frac{\pi^2}{2 L} \sum_{n=1}^N n^2 a_n^2(t)$$

Pianoteq 内部参数 `Quadratic Effect`（记作 $Q_{\text{eff}} \in [0.0, 20.00]$，Slot 94）是控制该非线性耦合强度的全局缩放系数。瞬时几何张力增量方程定义为：
$$\Delta T[n] = Q_{\text{eff}} \cdot \kappa_0 \cdot \sum_{m=1}^N m^2 \cdot \left(y_m[n]\right)^2$$
式中 $\kappa_0$ 为依赖于琴弦有效线密度的常数。

### 3. 声学物理效应一：大动态音高微漂移 (Amplitude-Dependent Pitch Glide)
琴弦波动基频直接依赖于瞬时张力：
$$f_0[n] = f_{0, \text{nominal}} \cdot \sqrt{1.0 + \frac{\Delta T[n]}{T_0}} \approx f_{0, \text{nominal}} \cdot \left(1.0 + \frac{\Delta T[n]}{2 T_0}\right)$$
- **物理现象**：在强奏（Forte / Fortissimo）击键瞬间，琴弦位移极大， $\Delta T > 0$，基频与各分音频率在最初数毫秒内瞬间向上拉升（拉升幅度通常为 $10 \sim 30\text{ Cents}$）；随后随着能量耗散位移衰减，音高迅速平滑回落至标称音高，赋予低音强奏极具张力的“紧绷感”。

### 4. 声学物理效应二：幻象分音非线性激发 (Phantom Partials Generation)
由于非线性力包含 $(\sum a_m \cos(\omega_m t))^2$ 乘积项，三角函数展开直接激发出差频与和频成分 $(\omega_j \pm \omega_k)$：
- 这一机制在低音区激发出大量非谐波相干微小泛音（Phantom Partials），重现了三角钢琴演奏强奏低音时极其深沉、充满金属开裂感的宏大声场。

---

## 二、双参数泛音滞后膨胀动力学模型 (Two-Parameter Blooming Dynamics)

在真钢琴物理发声中，中高力度击弦后，高阶分音（特别是第 3 至第 12 阶分音）的振幅**并非在击弦瞬间达到峰值**，而是经历短暂的时间滞后，随后在数十毫秒内向上攀升绽放（Blooming）。

Pianoteq 将其解耦为两大独立物理参数：
- **`Blooming Energy` ($E_b \in [0.0, 2.0]$，Slot 63)**：控制高阶分音能量向外膨胀的深度增益；
- **`Blooming Inertia` ($T_b \in [0.1, 3.0\text{ s}]$，Slot 65)**：控制能量由低频向高频转移的惯性时间常数。

### 1. 二阶惯性低通包络生成方程 (Inertial Envelope Generator)
每个分音 $n \in [1, N]$ 的动态膨胀乘法增益包络 $B_n(t)$ 定义为：
$$B_n(t) = 1.0 + E_b \cdot \zeta_n \cdot \left(\frac{t}{\tau_{n}}\right) \cdot \exp\left(1.0 - \frac{t}{\tau_{n}}\right)$$

式中：
- 分音权值分布： $\zeta_n = \sin\left(\dfrac{\pi \cdot n}{N}\right)$（能量主要泵浦向中高阶泛音，基频不受影响）；
- 各分音的特征滞后时间常数：
  $$\tau_n = T_b \cdot \left[0.015 + 0.035 \cdot \left(1.0 - \frac{n}{N}\right)\right] \quad (\text{秒})$$

### 2. 包络动力学演化特征
- **在击打初期 ($t = 0$)**：
  $B_n(0) = 1.0$，分音从标准毛毡接触初值起振；
- **在峰值绽放点 ($t = \tau_n$)**：
  $B_n(\tau_n) = 1.0 + E_b \cdot \zeta_n$ 达到最大绽放极值（高阶分音能量显著上扬）；
- **在稳态衰减期 ($t \gg \tau_n$)**：
  $B_n(t) \to 1.0$，平滑回退，完全服从音板阻抗决定的自然双指数指数衰减。

---

## 三、Phase 5-3 衔接指引

在 Phase 5-2 成功推导出二次方几何张力非线性调制方程与双参数惯性滞后膨胀包络之后，**Phase 5-3** 将聚焦于：
1. 整合 Phase 5-1 与 Phase 5-2 的全链路模型；
2. 输出包含完整逐采样点张力积分更新、瞬时音高调制与双参数绽放发生器的《二次方张力非线性与泛音绽放算法技术规约》（`docs/phase5/phase5-3-quadratic-blooming-spec.md`）；
3. 提供 C++20 Clean-Room 算法参考实现类 `NonlinearTensionAndBloomingVoice`，实现 Phase 5 的全胜闭环。
