# 接口文档

## 全床 Touch Mesh 补偿校准

```gcode
BED_MESH_CALIBRATE METHOD=touch_compensation
SAVE_CONFIG
```

该命令先使用现有 Scanner 网格路径生成 Scanner Mesh，再对相同的逻辑网格坐标执行 Touch 采样。系统保存 `touch_mesh - scanner_mesh` 的差值矩阵到 Klipper 运行时配置，并输出三张矩阵和差值范围。`SAVE_CONFIG` 用于持久化补偿数据。

命令要求 X、Y、Z 已 homing。Touch 采样使用 `[scanner]` 的 `scanner_touch_speed`、`scanner_touch_sample_count`、`scanner_touch_tolerance`、`scanner_touch_retract_dist` 和 `lift_speed` 配置。

Touch 网格参数独立于 `[bed_mesh] probe_count`：

```ini
[scanner]
touch_mesh_probe_count: 5,5
touch_mesh_samples: 3
touch_mesh_retry_threshold: 0.05
```

`touch_mesh_probe_count` 控制 Touch Mesh 的 X、Y 点数，默认 `5,5`。每个点先 Touch 一次；首次结果与 Scanner 插值值的绝对差异大于 `touch_mesh_retry_threshold` 时，追加 `touch_mesh_samples` 次 Touch，默认阈值 `0.05 mm`、追加次数 `3`。系统使用该点所有 Touch 结果的中位数计算补偿。Scanner Mesh 继续使用 `[bed_mesh] probe_count`，并在 Touch 网格坐标上进行双线性插值后计算补偿。

`SAVE_CONFIG` 会生成 `[scanner touch_mesh_compensation]` 段保存补偿矩阵。该段由系统管理，Klipper 启动时会将其识别为持久化补偿数据。
