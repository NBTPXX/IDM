# 需求实施计划

- [x] 1. 在 `scanner.py` 实现补偿配置模型和持久化读写
  - 解析 `[scanner touch_mesh_compensation]` 的网格元数据与行优先矩阵，校验版本、范围、维度和数值有效性；对应需求 2.1。
  - 通过 `configfile.set()` 写入新补偿配置，并实现 `CLEAR=1` 清除路径；对应需求 2.1、2.2、2.6。
  - [x] 1.1 为补偿配置序列化、反序列化和损坏数据处理编写单元测试；对应需求 2.1、2.4。

- [x] 2. 实现全床 Scanner 与 Touch 对比校准
  - 复用 Scanner 网格的范围、分辨率和参考点配置采集 Scanner Mesh；对应需求 1.1。
  - 在相同逻辑网格坐标执行 Touch 采样、样本容差检查与回抽，并恢复触发模式和运动限制；对应需求 1.2、3.1、3.2、3.3、3.4。
  - 对归一化后的两张网格计算 `touch_height - scanner_height`，输出两张矩阵、逐点差值和差值范围；对应需求 1.3、3.5、3.6、3.7、3.8。
  - 在采样失败时保持已有补偿配置；对应需求 1.4、1.5。
  - [x] 2.1 为网格归一化与差值矩阵编写单元测试；对应需求 1.3。
  - [x] 2.2 为任意相同尺寸矩阵验证“Scanner Matrix + Compensation Matrix = Touch Matrix”的性质测试；对应设计“Correctness Properties”。

- [ ] 3. 在 Scanner 网格生成时应用保存的补偿
  - 实现 Compensation Matrix 的边界检查与双线性插值；对应需求 2.3、2.4、2.5。
  - 在 `BED_MESH_CALIBRATE METHOD=scanner` 路径中，生成原始 Scanner Mesh 后叠加补偿值；对应需求 2.3。
  - 输出覆盖范围外坐标并保留对应原始 Scanner 测量值；对应需求 2.4、2.5。
  - [ ] 3.1 为网格内部、边界与覆盖范围外坐标编写双线性插值单元测试；对应需求 2.4、2.5。
  - [ ] 3.2 为恒定补偿矩阵和线性梯度矩阵编写插值性质测试；对应设计“Correctness Properties”。

- [ ] 4. 扩展 `BED_MESH_CALIBRATE` 接口并更新文档
  - 增加 `METHOD=touch_compensation` 和 `CLEAR=1`，保持现有非 Scanner 方法委托给原始 Bed Mesh 命令；对应需求 1.1、2.6。
  - 在接口文档中记录命令、配置节、`SAVE_CONFIG` 流程和 `METHOD=scanner` 自动补偿行为；对应需求 2.1、2.2、2.3。
  - [ ] 4.1 为命令分发、成功持久化与失败保留配置编写模拟 Klipper 单元测试；对应需求 1.4、1.5、2.1、2.6。

- [ ] 5. 检查点 - 确保所有测试通过,如有疑问请询问用户
  - 执行 Python 语法检查、相关单元测试和 `git diff --check`。
