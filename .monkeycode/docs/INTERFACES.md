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

`touch_mesh_probe_count` 控制 Touch Mesh 的 X、Y 点数，默认 `5,5`。系统先完成所有点的单次 Touch，再以网格几何中心对齐 Touch 与 Scanner 数据。中心对齐后的绝对差异大于 `touch_mesh_retry_threshold` 时，系统将该点加入复测列表并追加 `touch_mesh_samples` 次 Touch，默认阈值 `0.05 mm`、追加次数 `3`。系统使用该点所有 Touch 结果的中位数计算补偿。Scanner Mesh 继续使用 `[bed_mesh] probe_count`，并在 Touch 网格坐标上进行双线性插值后计算补偿。

每次初始采样的 Probe 日志会显示 `samples=1`。系统会输出完整的 `Touch mesh retry points` 坐标列表，并输出中心对齐后的两张网格和最终补偿矩阵。

`SAVE_CONFIG` 会生成 `[scanner touch_mesh_compensation]` 段保存补偿矩阵。该段由系统管理，Klipper 启动时会将其识别为持久化补偿数据。

后续 `BED_MESH_CALIBRATE METHOD=scanner` 会在生成原始 Scanner Mesh 后，对补偿覆盖范围内的每个坐标插值并叠加保存的补偿值。覆盖范围外坐标保留原始 Scanner 值，并在命令输出中列出。

`BED_MESH_CALIBRATE METHOD=touch_compensation` 始终使用原始 Scanner 测量值计算新的补偿矩阵。已有补偿不会参与该命令，命令输出会显示 `Touch mesh compensation uses raw Scanner measurements`。
