# Scanner Auto PA

Feature Name: scanner-auto-pa
Updated: 2026-07-19

## Description

`scanner_auto_pa.py` 提供 `SCANNER_AUTO_PA` G-code 命令。模块将 Scanner 原始频率作为喷嘴背压代理信号，扫描 Pressure Advance K 值并返回评分最低的候选值。

`SCANNER_AUTO_PA_DEBUG` 使用相同的测试运动执行单个 K、单周期采集，导出逐样本 CSV 供信号质量检查。

## Architecture

```mermaid
flowchart LR
    A["SCANNER_AUTO_PA"] --> B["K scan controller"]
    B --> C["XY and extrusion bursts"]
    C --> D["Scanner raw samples"]
    D --> E["Pressure proxy analysis"]
    E --> F["K result and optional apply"]
```

模块在每个候选 K 下执行基线采样和多次低流量、高流量、低流量测试周期。Scanner 回调保存时间、原始 data、频率、温度和位置。分析器以基线频率减实时频率生成背压代理信号，并按过渡段的超调、欠调、稳态斜率和面积计算评分。

## Components and Interfaces

### ScannerAutoPA

- `load_config(config)` 从 `[scanner_auto_pa]` 创建模块并注册 `SCANNER_AUTO_PA`。
- `cmd_SCANNER_AUTO_PA(gcmd)` 解析命令参数、验证打印机状态、运行 K 扫描并输出结果。
- `_run_candidate(k, settings)` 执行一个 K 候选值的基线和测试周期。
- `_analyse_candidate(samples, settings)` 计算候选 K 的背压代理评分。

### G-code Interface

```gcode
SCANNER_AUTO_PA [START_K=0.00] [END_K=0.10] [STEP=0.002] [CYCLES=14]
                [LOW_FLOW=1.92] [HIGH_FLOW=19.24]
                [LOW_TIME=1.0] [HIGH_TIME=0.25]
                [ACCEL=5000] [APPLY=0]

SCANNER_AUTO_PA_DEBUG [K=0.04] [CYCLES=1] [FILENAME=pa-debug.csv]
```

- 流量单位为 mm3/s。
- 模块基于配置的 `filament_diameter` 将体积流量换算为 E 轴线速度。
- 每段挤出附带小幅 XY 往复运动，保证 Pressure Advance 应用于打印运动。
- `APPLY=1` 时，模块在成功分析后设置推荐 K；默认恢复测试前 K。
- 调试命令总是恢复测试前 K，并将文件写入 `/tmp/<FILENAME>`。

## Data Models

```text
Sample: time, raw_data, frequency, temperature, position
CandidateResult: k, sample_count, overshoot, undershoot, plateau_slope, area, score
```

背压代理使用 `baseline_frequency - sample_frequency`。原始 `data` 用于保存和诊断，评分基于频率以获得温度校正和现有单位换算后的稳定信号。

## Correctness Properties

- 每个候选 K 使用相同的流量、持续时间、XY 位移和周期数。
- 每个候选 K 在开始测试前获得独立基线频率。
- 评分仅使用带有时间和频率的有效样本。
- 命令结束时 Scanner 流停止。
- `APPLY=0` 时，Pressure Advance 恢复到命令开始前的值。

## Error Handling

- Scanner 未加载模型、轴未 homing、挤出机缺失或样本不足时，命令报告错误。
- 运行期间发生异常时，模块停止数据流并恢复原始 Pressure Advance 和加速度限制。
- 候选 K 没有足够有效样本时，模块报告该候选 K 无效并继续其余候选值。
- 调试导出文件名使用基础文件名，输出目录固定为 `/tmp`。

## Test Strategy

- 单元测试体积流量到 E 轴速度的换算。
- 单元测试频率反向背压代理和候选评分。
- 使用模拟 Scanner 样本验证评分在已知最优 K 附近取得最小值。
- 在打印机上以单 K、单周期和低流量完成受控验证后扩大扫描范围。

## References

[^1]: [CNCKitchen PrusaPATuner](https://github.com/CNCKitchen/PrusaPATuner) - K 扫描参数、阶跃响应指标和原始信号分析参考。
[^2]: `scanner.py:1602` - Scanner 原始数据、频率和距离计算。
[^3]: `scanner.py:1668` - Scanner 数据流回调接口。
