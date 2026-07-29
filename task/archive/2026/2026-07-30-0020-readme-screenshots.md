# README 图文重构与演示截图

## 目标

- 将 README 顶部改成适合 GitHub 浏览的“产品定位、截图、核心能力、快速开始”结构。
- 使用本地演示夹具生成不含真实账号、Cookie、通知地址或运行日志的原生 Windows 截图。
- 截图覆盖主界面、多账号、完整任务节点和设置/日志。
- 清理更新说明中仅属于 v2 开发过程的 Bug 表述，保留最终用户能力。
- 更新当前 `codex/v2.0.0-release` 分支和私有草稿 PR。

## 截图规划

1. `docs/images/v2-main-overview.png`
   - 正式 v2.0.0 主界面、假账号、房间、运行状态和任务表格。
2. `docs/images/v2-multi-account.png`
   - 账号选择器展开，展示已保存、临时、挂机中等状态。
3. `docs/images/v2-task-progress.png`
   - 当天多任务及 60/120/180/240 分钟奖励节点。
4. `docs/images/v2-settings-log.png`
   - 设置与日志独立窗口、自动/固定并发和 Telegram 提示。

## 验收

- [x] 截图均为演示数据且没有敏感信息
- [x] 中文清晰、布局完整、无遮挡或开发辅助窗口
- [x] README 顶部可以在一分钟内说明产品用途与使用流程
- [x] 图片使用仓库相对路径并通过 Markdown 检查
- [x] 必要 GUI 测试通过
- [x] 提交并推送到现有私有 v2 PR

## 限制

- 不截取或停止用户当前正在挂机的程序。
- 不使用真实账号、Cookie、任务 ID、通知地址或日志。
- 不公开发布，不向公开仓库推送。

## 完成记录

- 使用隔离的内存演示档案生成 4 张 Qt 原生截图，演示数据均为虚构内容。
- README 已重排为产品说明、快速开始、界面截图、功能细节和开发文档结构。
- 正式更新说明已移除开发阶段 Bug 描述，改为最终用户能力。
- README 14 个本地链接、图片尺寸、`git diff --check` 均通过。
- `tests/test_gui_states.py` 与 `tests/test_window_chrome.py` 共 43 项测试通过。
- 文档和截图提交为 `b981fbd`，已推送到私有分支 `codex/v2.0.0-release`。
