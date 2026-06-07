# Bilibili 直播掉宝助手增强版

这是一个基于 [mi0e/BiliBiliDropsMiner](https://github.com/mi0e/BiliBiliDropsMiner) 的 B 站直播掉宝/观看时长任务挂机工具。
本版本同步了上游最近版本的主要功能，并额外加入 GUI Cookie 档案管理，默认线程数调整为 128。

## 许可与来源

- 原项目：<https://github.com/mi0e/BiliBiliDropsMiner>
- 原项目说明：B 站直播掉宝助手，支持多线程加速
- 本项目遵守 MIT License，已在 [LICENSE](LICENSE) 中保留原项目与本项目的版权声明。
- 本项目仅供个人学习研究使用，不提供稳定性保证或技术支持。

## 本版本增强

- GUI 支持将 Cookie 保存到 `cookies.json`。
- GUI 支持在下拉框中切换多个 Cookie。
- 每个 Cookie 档案支持自定义备注，未填写备注时会优先使用 `DedeUserID` 自动生成。
- 默认线程数从 1 调整为 128，包括 GUI、CLI、配置默认值和示例配置。
- 版本检查目标改为本仓库 release。

`cookies.json` 保存位置：

- 源码运行：当前工作目录。
- 打包 exe 运行：exe 同目录。

示例格式：

```json
{
  "cookies": [
    {
      "remark": "主号",
      "cookie": "SESSDATA=xxx; bili_jct=xxx; DedeUserID=123",
      "updated_at": "2026-06-05 23:00:00"
    }
  ]
}
```

## 已同步的上游更新

对比上游最近几个版本，本版本已同步到上游 `v1.6.0`，包含以下能力：

- `v1.4.3`：改进任务 ID 提取逻辑，支持 Nuitka 打包。
- `v1.5.0`：新增一键领取全部掉宝奖励，改进 Chrome/Edge 跨平台检测，修复按日期分组的掉宝任务识别。
- `v1.5.1`：修复自动获取浏览器优先级和任务进度误判。
- `v1.5.2`：修复多标签检测，加入新版本检查。
- `v1.6.0`：修复 Chrome 自动获取任务 ID 时新页面注入问题，重构 GUI 模块，改为通过 API 获取观看时长，优化任务进度结构化展示，并修复首次启动时 anyio 并发初始化异常。

## 功能

- 多房间并发挂机，支持每个房间多会话连接。
- GUI 与 CLI 双模式。
- 任务进度自动轮询与手动刷新。
- 直播观看时长预估展示。
- 一键领取掉宝奖励。
- 自动获取 Cookie、房间号、任务 ID。
- GUI 配置保存/加载。
- Cookie 档案保存、备注和切换。
- Gotify、Server 酱等通知地址支持。

## 免责声明

> 本项目仅供个人学习研究，不保证稳定性，不提供技术支持。
> 使用本项目产生的一切后果由用户自行承担。
> 禁止商业用途，请遵守版权及平台规则。

## 参数获取

### Cookie

方式 1：GUI 中点击“自动获取”，在打开的 Chrome/Edge 浏览器中登录 B 站。
方式 2：登录 B 站后打开浏览器开发者工具复制 Cookie。

Cookie 必须至少包含：

- `SESSDATA`
- `bili_jct`

建议同时保留：

- `DedeUserID`
- `DedeUserID__ckMd5`
- `buvid3`

### 房间号

直播间 URL 中的数字部分就是房间号。
例如 `https://live.bilibili.com/23612045` 的房间号为 `23612045`。

### 任务 ID

可在 GUI 中点击“自动获取任务 ID”。
也可以从任务接口请求里提取 `task_ids` 参数：

```text
https://api.bilibili.com/x/task/totalv2?csrf=xxx&task_ids=taskId1,taskId2
```
多个任务 ID 使用英文逗号分隔。

## 快速开始

### Windows GUI

```powershell
python -m pip install -r requirements.txt
python bilibili_gui.py
```

也可以直接运行 release 中的 exe。

### CLI

```powershell
python bilibili.py --cookie "SESSDATA=xxx; bili_jct=xxx" --rooms "23612045"
```

常用参数：

```text
--cookie COOKIE                 B 站登录 Cookie
--rooms ROOMS                   房间号，多个用逗号分隔
--threads THREADS               每个房间会话数，默认 128
--reconnect-delay SECONDS       断线重连延迟
--task-ids TASK_IDS             用于进度监控的任务 ID
--task-interval SECONDS         任务查询间隔
--notify-urls URLS              通知 URL，多个用逗号分隔
--disable-task-notify           关闭任务完成通知
--no-color                      禁用彩色日志
-v, --verbose                   显示详细日志
```

示例：

```powershell
python bilibili.py `
  --cookie "SESSDATA=xxx; bili_jct=xxx" `
  --rooms "23612045,1017" `
  --threads 128 `
  --task-ids "taskId1,taskId2"
```

## GUI 使用

1. 填写或自动获取 Cookie。
2. 填写直播间号。
3. 可选：填写或自动获取任务 ID。
4. 可选：填写通知 URL。
5. 按需调整线程数、重连延迟和任务查询间隔。
6. 点击“启动”。

Cookie 档案：

1. 在 Cookie 输入框填入 Cookie。
2. 在“备注”中填写账号备注。
3. 点击“保存Cookie”写入 `cookies.json`。
4. 之后可从“Cookie档案”下拉框切换账号。
5. 选择档案后点击“删除Cookie”可删除该档案。

## 配置文件

GUI 支持保存/加载 JSON 配置文件，示例见 [config.example.json](config.example.json)。

## 打包

PyInstaller：

```powershell
python build.py --release --target gui --clean
python build.py --target cli --clean
```

`--release` 会输出单个可直接运行的 exe；默认不带 `--release` 时输出开发用文件夹。

Nuitka：

```powershell
python -m pip install nuitka
python build_nuitka.py --target gui
```

## 常见问题

### 任务时长为什么一直为 0？

任务时长通常不是实时结算。启动后至少等待 30 秒再观察。若长时间为 0，可能是账号风控或直播任务未被平台认可。

### 线程数越高越好吗？

不是。线程数过高可能触发平台风控。当前默认值是 128，适合追求高并发的场景；如果出现异常，建议降低到 60 到 80 后重试。

### 自动获取打不开浏览器怎么办？

自动获取依赖 Chrome/Edge 和 Selenium。请确认浏览器安装在常见路径，首次运行时 Selenium Manager 可能会下载驱动。

## 开发验证

```powershell
python -m compileall bilibili_drops_miner bilibili.py bilibili_gui.py build.py build_nuitka.py
python bilibili.py --help
```
