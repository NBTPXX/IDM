# 接口文档

## Scanner Auto PA

在 `printer.cfg` 增加：

```ini
[scanner_auto_pa]
# filament_diameter: 1.75
# xy_amplitude: 1.0
# baseline_time: 1.0
# min_samples: 20
```

命令：

```gcode
SCANNER_AUTO_PA START_K=0.00 END_K=0.10 STEP=0.002 CYCLES=14 \
  LOW_FLOW=1.92 HIGH_FLOW=19.24 LOW_TIME=1.0 HIGH_TIME=0.25 \
  ACCEL=5000 APPLY=0 EXPORT=pa-results.csv
```

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `START_K` | `0.00` | 扫描起始 K |
| `END_K` | `0.10` | 扫描结束 K |
| `STEP` | `0.002` | K 扫描步长 |
| `CYCLES` | `14` | 每个 K 的低/高/低测试周期数 |
| `LOW_FLOW` | `1.92` | 低流量，单位 mm3/s |
| `HIGH_FLOW` | `19.24` | 高流量，单位 mm3/s |
| `LOW_TIME` | `1.0` | 低流量持续时间，单位 s |
| `HIGH_TIME` | `0.25` | 高流量持续时间，单位 s |
| `ACCEL` | `5000` | 测试加速度，单位 mm/s2 |
| `APPLY` | `0` | `1` 时应用推荐 K |
| `EXPORT` | 空 | CSV 文件名，输出到 `/tmp` |

命令要求 Scanner 模型、活动挤出机和已 homing 的 XYZ 轴。`APPLY=0` 时，模块在扫描结束后恢复原 Pressure Advance 值。

## 单次信号调试

```gcode
SCANNER_AUTO_PA_DEBUG K=0.04 CYCLES=1 LOW_FLOW=1 HIGH_FLOW=2 FILENAME=pa-debug.csv
```

该命令执行单个候选 K 的测试周期，并将基线与测试阶段的 `time`、`data`、`freq`、`pressure_proxy`、`temp` 和 XYZ 位置写入 `/tmp/pa-debug.csv`。命令结束后恢复原 Pressure Advance 和加速度限制。

## IDM 阈值扫描日志

```gcode
IDM_THRESHOLD_SCAN DEBUG=1
```

`DEBUG=1` 会输出每次 Touch 触发的 `probe at X,Y is z=...` 记录，同时保留每个阈值的资格检查和验证汇总。默认 `DEBUG=0` 仅输出阈值阶段汇总。

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
```

`touch_mesh_probe_count` 控制 Touch Mesh 的 X、Y 点数，默认 `5,5`。`touch_mesh_samples` 控制每个 Touch 网格点的有效触发次数，默认 `3`。Scanner Mesh 继续使用 `[bed_mesh] probe_count`，并在 Touch 网格坐标上进行双线性插值后计算补偿。
