# Phase 1-2 验收报告：琴槌参数注册与映射函数定向反编译与结构体逆向

> **任务编号**：Phase 1-2  
> **研究目标**：对 Phase 1-1 锁定的整音参数主初始化函数 `0x00000001806c49f0` 及核心子例程执行定向反汇编与数据流切片分析，逆向提取 Pianoteq 9 琴槌参数内部存储结构体、长短键名别名绑定机制，以及三力度琴槌硬度（Piano / Mezzo / Forte）到击弦物理刚度的离散数学映射模型。  
> **报告归档路径**：`docs/phase1/phase1-2-hammer-mapping-decompilation.md`  
> **当前状态**：历史切片与节点解释保留；旧 Accepted 不等于别名、硬度映射或接触求解器已获当前认证。
> **复核入口**：[统一证据等级与旧主张处理](../acoustic_benchmark_report.md#证据等级与旧主张处理)。汇编及表内作者注释是当时解释，未在本轮重做Ghidra验证。

---

## 一、主函数反汇编与执行流切片 (VoicingSetup_HammerParams)

- **函数地址**：`0x00000001806c49f0` ~ `0x00000001806c6bb4`（RVA `0x006c49f0` ~ `0x006c6bb4`，总长 8,644 字节）
- **寄存器约定**：
  - `rcx`：主整音引擎上下文指针（`VoicingEngine*` / `this`）
  - `rsi`：传入的整音参数注册管理器（`VoicingRegistry*`，函数序言由 `rdx` 移入 `rsi`）
  - `rbp-0x40`：局部栈帧上的临时参数键名容器（`ParameterKey`）

### 核心汇编指令切片 (0x1806c4e7c ~ 0x1806c4f1c)

```assembly
; === 1. 注册 Forte (强奏硬度) ===
1806c4e7c:  lea    -0x40(%rbp), %edx      ; 传入临时键名缓存
1806c4e7f:  mov    %rsi, %rcx             ; rcx = VoicingRegistry*
1806c4e82:  call   0x18033e9d0            ; 调用参数节点分配器 (分配 96 字节 ParameterTreeNode)
1806c4e87:  mov    %rax, %rcx             ; rcx = 新分配的节点指针
1806c4e8a:  lea    -0x64b7f9(%rip), %rdx  ; rdx = "hammer_hardness_forte" (VA 0x180079698)
1806c4e91:  call   0x1801be160            ; 绑定主键名
1806c4e97:  lea    -0x40(%rbp), %rcx      ; 清空临时容器
1806c4e9b:  call   0x1805631c0            
1806c4ea0:  lea    -0x69505f(%rip), %rdx  ; rdx = "hammer_hard_mezzo" (预设短别名，VA 0x18002fe48)
1806c4ea7:  lea    -0x40(%rbp), %rcx      
1806c4eab:  call   0x1802873e0            ; 注册别名索引并绑定到同一节点

; === 2. 注册 Mezzo (中等力度硬度) ===
1806c4eb1:  lea    -0x40(%rbp), %rdx      
1806c4eb5:  mov    %rsi, %rcx             
1806c4eb8:  call   0x18033e9d0            ; 分配节点
1806c4ebd:  mov    %rax, %rcx             
1806c4ec0:  lea    -0x647c97(%rip), %rdx  ; rdx = "hammer_hardness_mezzo" (VA 0x18007d230)
1806c4ec7:  call   0x1801be160            ; 绑定主键名
1806c4ecd:  lea    -0x40(%rbp), %rcx      
1806c4ed1:  call   0x1805631c0            
1806c4ed6:  lea    -0x687b35(%rip), %rdx  ; rdx = "hammer_hard_piano" (预设短别名，VA 0x18003d3a8)
1806c4edd:  lea    -0x40(%rbp), %rcx      
1806c4ee1:  call   0x1802873e0            ; 注册别名

; === 3. 注册 Piano (弱奏力度硬度) ===
1806c4ee7:  lea    -0x40(%rbp), %rdx      
1806c4eeb:  mov    %rsi, %rcx             
1806c4eee:  call   0x18033e9d0            ; 分配节点
1806c4ef3:  mov    %rax, %rcx             
1806c4ef6:  lea    -0x643c15(%rip), %rdx  ; rdx = "hammer_hardness_piano" (VA 0x1800812e8)
1806c4efd:  call   0x1801be160            ; 绑定主键名
1806c4f03:  lea    -0x40(%rbp), %rcx      
1806c4f07:  call   0x1805631c0            
1806c4f0c:  lea    -0x64cdf3(%rip), %rdx  ; rdx = "hard_forte" (极短别名，VA 0x180078120)
1806c4f13:  lea    -0x40(%rbp), %rcx      
1806c4f17:  call   0x1802873e0            ; 注册极短别名
```

---

## 二、参数节点结构体逆向 (ParameterTreeNode Layout)

原稿将子例程 `0x18033e9d0` 解释为参数节点分配/构造，并提出 **96 字节（0x60）** 的 MSVC STL 红黑树布局猜测。以下偏移记录保留，字段角色与C++草案不视为已重新核对的专有结构或工程实现：

### 内存布局表 (Node Size: 96 Bytes / 0x60)

| 偏移区间 (Offset) | 字段名称 | 类型 | 详细作用与汇编证据 |
| :--- | :--- | :--- | :--- |
| `+0x00 ~ +0x07` | `left` | `ParameterTreeNode*` | 红黑树左子节点指针（`mov %rbx, (%rax)`） |
| `+0x08 ~ +0x0F` | `parent` | `ParameterTreeNode*` | 红黑树父节点指针（`mov %rbx, 0x8(%rax)`） |
| `+0x10 ~ +0x17` | `right` | `ParameterTreeNode*` | 红黑树右子节点指针（`mov %rbx, 0x10(%rax)`） |
| `+0x18` | `color` | `uint8_t` | 红黑树颜色标志（0: Red, 1: Black）（`mov %bp, 0x18(%rax)`） |
| `+0x19` | `isNil` | `uint8_t` | 哨兵节点标志位（`cmpb $0x0, 0x19(%rbx)`） |
| `+0x1A ~ +0x1F` | `_pad` | `uint8_t[6]` | 内存对齐填充 |
| `+0x20 ~ +0x2F` | `nameBuffer` | `char[16]` | SSO 内联字符串缓冲区（小字符串直接内联存放） |
| `+0x30 ~ +0x37` | `nameLength` | `size_t` | 参数主键名有效长度 |
| `+0x38 ~ +0x3F` | `nameCapacity`| `size_t` | 缓冲区容量（初始化设为 `0xF = 15` 字节，`movq $0xf, 0x18(%rsi)`） |
| `+0x40 ~ +0x4F` | `aliasBuffer`| `char[16]` | 第二个 SSO 字符串缓冲区（别名或物理单位） |
| `+0x50 ~ +0x57` | `aliasLength` | `size_t` | 别名有效长度 |
| `+0x58 ~ +0x5F` | `aliasCapacity`| `size_t` | 缓冲区容量（初始化设为 `0xF = 15` 字节，`movq $0xf, 0x58(%rax)`） |

### 原稿的 C++ 结构体草案（字段解释未重新认证）

```cpp
// Pianoteq 内部参数注册红黑树节点定义 (MSVC x64 ABI, 96 字节)
struct alignas(8) ParameterTreeNode {
    // 0x00 ~ 0x1F: STL _Tree_node 树控制块
    ParameterTreeNode* left;
    ParameterTreeNode* parent;
    ParameterTreeNode* right;
    uint8_t color;
    bool isNil;
    uint16_t reserved;
    uint32_t padding;

    // 0x20 ~ 0x3F: 参数长键名 (MSVC std::string, 32 字节)
    union {
        char inlineBuffer[16];
        char* heapPointer;
    } name;
    size_t nameLength;
    size_t nameCapacity;

    // 0x40 ~ 0x5F: 参数短键名/别名/单位 (MSVC std::string, 32 字节)
    union {
        char inlineBuffer[16];
        char* heapPointer;
    } alias;
    size_t aliasLength;
    size_t aliasCapacity;
};
static_assert(sizeof(ParameterTreeNode) == 0x60, "ParameterTreeNode size must be 96 bytes");
```

---

## 三、别名绑定解释的当前限制

上方切片中的名字、地址与作者注释保留原样。原稿将相邻注册调用推定为 Forte↔Mezzo 等跨力度别名和“绝对向下兼容”，本次不采用该解释；字符串共现不能证明同一对象、槽位或物理状态的绑定关系。

必须分别确认节点身份、调用参数和后续读取链条，才能讨论别名。当前没有这组补证，也不据此让 devpiano 增加旧字段别名或迁移路径。

## 四、三力度与接触模型的证据等级

- 官方 Voicing 语义支持 Piano / Mezzo forte / Forte 约41/70/98；硬度的具体滑块范围和默认值未复核，不再将原稿 `[0,2]` 与规格书 `[0.1,2.5]` 两种范围都写成已知。
- 归一化力度 `(v-1)/126` 可作为候选设计口径，但 MIDI 值不等于已标定的机械初速度或压缩量。
- 原稿的分段幂指数、`K=K0*H³`、动态接触指数与迟滞力模型是候选重构，不是由本页注册切片证实的内部方程。三力度高频输出不能唯一标定这些值。
- 原稿与后续规格书的 `p(H)` 表达不一致，数值/单位没有完整来源，已撤去作为生产映射的指引；不以任意一种新表达补成专有算法。

经典非线性接触理论仍可研究，但质量、刚度、位移尺度、损耗、反作用耦合及稳定性必须另行建立。当前 [声学基准报告](../acoustic_benchmark_report.md) 只准入指定文件的输出观察。

## 五、后续补证边界

若有真实研究需求，先补注册对象到渲染状态的身份/数据流，再用受控输入验证候选接触模型；本轮未开展这项新逆向。当前模型限制见 [琴槌候选规格](phase1-3-hammer-dynamics-spec.md)，原文与旧草案见输入修订/本机封存。
