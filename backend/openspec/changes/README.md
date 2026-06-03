# Changes — OpenSpec 变更记录

此目录存放 OpenSpec 的 delta 变更记录。每个变更是一个子目录，包含变更描述、影响的 spec 和实现任务。

## 目录结构

```
changes/
├── README.md           # 本文件
└── <change-name>/      # 每个变更一个子目录
    ├── spec.md         # Delta spec — 描述变更内容
    └── tasks.md        # 实现任务清单
```

## 变更流程

1. **Propose** — 创建 `changes/<name>/` 子目录，编写 delta spec 和任务清单
2. **Implement** — 按 tasks.md 逐项实现代码变更
3. **Archive** — 实现完成后，将 delta spec 合并到 `specs/` 对应 capability spec，然后移动 change 到 `archive/`

## 当前状态

暂无活动变更。所有 capability spec 反映 `feature_1.3` 分支的当前代码行为。
