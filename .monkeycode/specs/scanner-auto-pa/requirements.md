# Requirements Document

## Introduction

Scanner Auto PA 使用 Scanner 的原始感应数据作为喷嘴背压代理信号，执行 Pressure Advance K 值扫描并输出推荐值。

## Glossary

- **Pressure Advance K**: 影响挤出压力补偿的系数。
- **背压代理信号**: 由基线频率减去实时频率得到的相对信号；数值增大表示挤出背压增大。
- **K 扫描**: 在多个候选 K 值下执行相同挤出测试并比较信号响应的过程。
- **测试周期**: 一个低流量、高流量、低流量的挤出速度阶跃序列。

## Requirements

### Requirement 1

**User Story:** 作为打印机使用者，我希望执行自动 K 扫描，以获得一个可复现的 Pressure Advance 推荐值。

#### Acceptance Criteria

1. WHEN 用户执行自动 PA 校准命令，系统 SHALL 验证 Scanner 模型和挤出机处于可用状态。
2. WHEN 用户指定 K 扫描范围和步长，系统 SHALL 为范围内的每个 K 值执行相同数量的测试周期。
3. WHEN 系统执行每个测试周期，系统 SHALL 生成包含 XY 运动的低流量、高流量、低流量挤出序列。
4. WHEN 扫描完成，系统 SHALL 输出评分最低的 K 值和每个候选 K 值的评分。
5. WHEN 用户未指定扫描参数，系统 SHALL 使用 `START_K=0.00`、`END_K=0.10`、`STEP=0.002` 和 `CYCLES=14`。
6. WHEN 用户未指定流量参数，系统 SHALL 使用低流量 `1.92 mm3/s` 持续 `1.0 s` 和高流量 `19.24 mm3/s` 持续 `0.25 s`。

### Requirement 2

**User Story:** 作为打印机使用者，我希望使用 Scanner 原始数据评估挤出背压，以避免增加专用压力传感器。

#### Acceptance Criteria

1. WHILE 自动 PA 校准运行，系统 SHALL 采集带有时间戳的 Scanner 原始 `data`、温度和工具头位置。
2. WHEN 系统开始每个测试周期，系统 SHALL 采集无挤出基线数据。
3. WHEN 系统计算背压代理信号，系统 SHALL 使用基线频率减去实时频率。
4. WHEN 背压代理信号的有效样本数量少于配置的最小数量，系统 SHALL 将当前 K 标记为无效并报告原因。

### Requirement 3

**User Story:** 作为打印机使用者，我希望校准过程在运动和温度条件异常时保留打印机安全状态。

#### Acceptance Criteria

1. WHEN 自动 PA 校准开始，系统 SHALL 验证 XYZ 轴已完成 homing。
2. WHEN 当前喷嘴温度低于配置目标温度，系统 SHALL 等待喷嘴达到目标温度后开始扫描。
3. IF Scanner 流在配置的超时时间内未产生样本，系统 SHALL 终止校准并恢复先前的 Pressure Advance K 值。
4. WHEN 自动 PA 校准结束，系统 SHALL 停止 Scanner 数据流并恢复先前的 Pressure Advance K 值，除非用户显式请求应用推荐值。

### Requirement 4

**User Story:** 作为开发者，我希望获得可离线复核的扫描样本和评分，以验证推荐 K 值。

#### Acceptance Criteria

1. WHEN 用户启用数据导出，系统 SHALL 将每个候选 K 的原始样本、背压代理信号和评分写入 CSV 文件。
2. WHEN 系统计算候选 K 评分，系统 SHALL 分别记录超调、欠调、相位滞后、稳态斜率和积分面积指标。
3. WHEN 用户请求调试输出，系统 SHALL 输出每个 K 的有效样本数量和评分指标。

### Requirement 5

**User Story:** 作为开发者，我希望执行单次自动 PA 调试测试，以验证 Scanner 信号是否适合作为背压代理。

#### Acceptance Criteria

1. WHEN 用户执行 `SCANNER_AUTO_PA_DEBUG`，系统 SHALL 执行一个指定 K 值的低流量、高流量、低流量测试周期。
2. WHEN 调试测试完成，系统 SHALL 将逐样本时间、原始 data、平滑数据、频率、背压代理、温度和位置写入 CSV 文件。
3. IF 调试测试的有效样本数量少于配置的最小数量，系统 SHALL 报告样本不足。
4. WHEN 调试测试结束，系统 SHALL 恢复命令开始前的 Pressure Advance 和加速度限制。
