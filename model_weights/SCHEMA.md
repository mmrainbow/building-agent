# 模型文件说明

本目录用于本地存放模型权重文件，不纳入 Git 仓库。

需要放置的文件：

- `add_predict.pth`
- `best.pt`
- `main_building.pt`
- `material.pth`
- `outer_obj.pt`

请从项目成员本地或共享网盘手动放入该目录。

## 占位权重（仅便于本地启动 UI）

若目录中已有上述 5 个文件且 `python app.py` 能正常打开页面，但巡检结果明显不合理，说明当前为**占位权重**（例如 YOLO 使用 `yolov8n`、EfficientNet 为随机初始化），需用团队正式训练权重覆盖。

占位权重**不能**替代生产巡检；正式环境务必使用项目提供的真实模型文件。
