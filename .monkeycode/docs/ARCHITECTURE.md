# IDM Scanner 架构

## 概述

本仓库提供 Klipper 的感应式 Scanner/IDM 探针扩展。核心模块负责 MCU 数据流、频率到距离的模型换算、Z 探测、Touch 触发和床网格相关操作。

`scanner_auto_pa.py` 是实验性扩展模块。它将 Scanner 频率下降映射为喷嘴背压代理信号，通过 K 值扫描评估 Pressure Advance。

## 结构

```text
.
├── scanner.py             Scanner、Touch 与 MCU 数据流实现
├── idm.py                 IDM 探针实现
├── scanner_auto_pa.py     Scanner 自动 Pressure Advance 校准
├── arg_fit.py             参数拟合工具
├── test_scanner_auto_pa.py 自动 PA 单元测试
└── install.sh             安装脚本
```

## 数据流

```mermaid
flowchart LR
    A["Scanner MCU samples"] --> B["scanner.py"]
    B --> C["data and frequency"]
    C --> D["scanner_auto_pa.py"]
    D --> E["Pressure Advance K score"]
```

`scanner.py` 将 MCU 的原始 `data` 按时间与工具头位置对齐，生成 `data_smooth`、`freq` 和 `dist`。自动 PA 模块通过 `streaming_session()` 收集样本，计算 `baseline_freq - freq` 作为背压代理信号。

## 模块职责

| 模块 | 职责 |
|---|---|
| `scanner.py` | Scanner 配置、样本流、模型、探测和 Touch G-code 命令 |
| `idm.py` | IDM 探针与模型配置 |
| `scanner_auto_pa.py` | `SCANNER_AUTO_PA` K 扫描、样本分析、结果应用和 CSV 导出 |
| `arg_fit.py` | 离线拟合工具 |
