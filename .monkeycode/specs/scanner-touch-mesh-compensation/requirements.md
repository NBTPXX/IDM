# Requirements Document

## Introduction

Scanner Touch Mesh Compensation 通过在同一张床网格上分别执行 Scanner 扫描和 Touch 触发采样，计算并保存二维高度差值。后续 Scanner 网格校准将叠加已保存的差值，使 Scanner 网格与 Touch 测量基准对齐。

## Glossary

- **Scanner Mesh**: Scanner 在床网格坐标上采集并生成的高度矩阵。
- **Touch Mesh**: Touch 模式在相同床网格坐标上触发并生成的高度矩阵。
- **Compensation Matrix**: Touch Mesh 减去 Scanner Mesh 得到的二维高度差值矩阵。
- **Compensated Scanner Mesh**: 叠加 Compensation Matrix 后生成的 Scanner Mesh。

## Requirements

### Requirement 1

**User Story:** 作为打印机使用者，我希望执行全床 Scanner 与 Touch 对比校准，以获得 Scanner 网格的二维高度补偿。

#### Acceptance Criteria

1. WHEN 用户执行 `BED_MESH_CALIBRATE METHOD=touch_compensation`，系统 SHALL 使用 `[bed_mesh] probe_count` 采集 Scanner Mesh。
2. WHEN 用户未配置 `touch_mesh_probe_count`，系统 SHALL 使用 `5,5` 采集 Touch Mesh。
3. WHEN 用户未配置 `touch_mesh_samples`，系统 SHALL 在每个 Touch 网格坐标采集 3 个有效 Touch 样本。
4. WHEN 系统完成两张网格采集，系统 SHALL 将 Scanner Mesh 插值到 Touch Mesh 坐标并计算 `touch_height - scanner_height`。
5. IF 任一网格点的 Touch 采样失败，系统 SHALL 终止校准。
6. IF 全床补偿校准终止，系统 SHALL 保留已有 Compensation Matrix。

### Requirement 2

**User Story:** 作为打印机使用者，我希望保存全床补偿结果，以便后续 Scanner 网格自动使用相同基准。

#### Acceptance Criteria

1. WHEN 系统完成全床补偿校准，系统 SHALL 将 Compensation Matrix 及其网格范围和网格点数写入 Klipper 运行时配置。
2. WHEN 用户执行 `SAVE_CONFIG`，Klipper SHALL 将已写入运行时配置的 Compensation Matrix 持久化到配置文件。
3. WHEN 用户执行 `BED_MESH_CALIBRATE METHOD=scanner`，系统 SHALL 根据当前网格坐标对已保存的 Compensation Matrix 进行二维插值并叠加补偿。
4. IF 当前网格范围超出 Compensation Matrix 覆盖范围，系统 SHALL 报告未补偿坐标。
5. IF 当前网格范围超出 Compensation Matrix 覆盖范围，系统 SHALL 使用 Scanner 原始测量值。
6. WHEN 用户清除补偿结果，系统 SHALL 停止在后续 Scanner 网格中叠加 Compensation Matrix。

### Requirement 3

**User Story:** 作为打印机使用者，我希望在执行全床 Touch 校准时保持可预测的运动和热状态。

#### Acceptance Criteria

1. WHEN 系统开始全床补偿校准，系统 SHALL 验证 XYZ 轴已完成 homing。
2. WHEN 系统开始 Touch Mesh 采样，系统 SHALL 使用 Scanner Touch 的速度、回抽距离、样本数和容差配置。
3. WHEN 系统结束全床补偿校准，系统 SHALL 恢复命令开始前的运动限制。
4. WHEN 系统结束全床补偿校准，系统 SHALL 恢复命令开始前的触发模式。
5. WHEN 系统生成 Compensation Matrix，系统 SHALL 输出 Scanner Mesh。
6. WHEN 系统生成 Compensation Matrix，系统 SHALL 输出 Touch Mesh。
7. WHEN 系统生成 Compensation Matrix，系统 SHALL 输出逐点差值。
8. WHEN 系统生成 Compensation Matrix，系统 SHALL 输出差值范围。
