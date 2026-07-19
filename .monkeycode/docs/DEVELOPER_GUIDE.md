# 开发者指南

## 前置条件

- Python 3
- 可用的 Klipper 源码运行时，用于加载 `scanner.py`、`idm.py` 和扩展模块

## 验证

```bash
python3 -m py_compile scanner_auto_pa.py
python3 -m unittest test_scanner_auto_pa.py
git diff --check
```

## Scanner Auto PA 开发约定

- 用 `sample["data"]` 保留原始 Scanner 数据。
- 用 `baseline_freq - sample["freq"]` 计算背压代理；频率下降表示背压增大。
- Scanner 回调应只进行内存收集，文件写入和计算放在扫描结束后执行。
- 测试命令在每个候选 K 后恢复 G-code 状态，命令结束时恢复原加速度和 Pressure Advance。

## 实机验证顺序

1. 用单个 K、单周期和低流量确认 XY 往复运动路径安全。
2. 观察 Scanner 原始频率在流量阶跃时的方向与重复性。
3. 扩展到多个 K 候选值。
4. 在 `APPLY=0` 下复核推荐 K，再使用 `APPLY=1`。

原始信号检查可执行：

```gcode
SCANNER_AUTO_PA_DEBUG K=0.04 CYCLES=1 FILENAME=pa-debug.csv
```
