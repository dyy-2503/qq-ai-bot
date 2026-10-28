# QQ AI 好友机器人 · 部署套件

在 QQ 私聊里养一个"记得住事、会说话、有固定性格"的 AI 好友。
技术栈：**NapCatQQ**（协议端）+ **AstrBot**（应用层）+ 任意大模型 API（本项目以 DeepSeek 为例）。

> 本仓库只包含**部署脚本、配置模板、人格设定、自研插件与排障工具**。
> 不含任何聊天记录、记忆文件、API Key 或账号登录态。

---

## 它能做什么

| 能力 | 实现方式 | 说明 |
|---|---|---|
| 文本聊天 | AstrBot 主 Agent + DeepSeek | 人格约束：一两句话、不用 Markdown、可以沉默 |
| **看图片** | 模型多模态（`modalities` 含 `image`） | 对方发表情包/照片，它能描述内容 |
| **发语音** | `edge-tts` + 自研插件 `voice_reply` | 短句按概率转语音条；长回复永不转 |
| **主动搭话** | 自研插件 `proactive` | 没人说话时按"命中线"掷骰，掷中就开口 |
| **表情包** | `astrbot_plugin_stealer` + 自研 `meme_cmd` | 自动偷图入库；`/表情 关键词` 直接发 |
| **自己刷 B 站** | 自研 `bili_ingest` | 谷时自动刷 → 读字幕 → 判定 → 入库，只存不发 |
| **推荐视频** | 自研 `recommend` | 每天挑一条没推过的库存，她的话 + BV 链接 |
| **写说说** | 自研 `daily_post` | 结合当天刷到的视频和聊天内容，自动发到 QQ 空间 |
| **群聊氛围** | 自研 `group_vibe` | 低概率自己接话、@ 必回、固定上下文窗口、防 AI 互相套娃 |
| **闭嘴** | 自研 `mute` | `/闭嘴 30` 静音会话，管理员专用 |
| 长期记忆 | `astrbot_plugin_memory_beyond` | 索引式 Markdown 档案 + 关键词召回 |

---

## 目录

| 路径 | 内容 |
|---|---|
| `docs/部署手册.md` | 从零开始的手册：选型、Docker/手动两种部署、人格、记忆、验收清单 |
| `docs/运维备忘.md` | 实际踩过的坑、运维命令、补丁记录（比手册更贴近真实使用） |
| `docs/云端部署.md` | Ubuntu 22.04 + systemd + Docker NapCat 的完整步骤与三个坑 |
| `docs/手机扫码.md` | QQ 掉线自救：`qr` 命令、Termius 配置、看门狗怎么区分状态 |
| `plugins/` | 八个自研插件，可直接丢进 `data/plugins/` |
| `scripts/` | 启动 / 守护 / 打开后台的 Windows 脚本 |
| `config-templates/` | AstrBot 主配置与插件配置模板（已脱敏） |
| `persona/大肥鱼.txt` | 示例人格：拟人化鲸鱼娘 |
| `tools/` | 改人格、改配置、查表情包库的小脚本（Python） |
| `CHANGELOG.md` | 更新记录 |

---

## 架构

```
QQ 小号 ──私聊──> NapCat（无头 NTQQ）──OneBot v11 WS──> AstrBot ──HTTPS──> DeepSeek
                                                         │
                          ┌──────────────────────────────┼──────────────────────────────┐
                          ▼                              ▼                              ▼
                    voice_reply                    proactive                      meme_cmd
                 （短句转语音条）              （掷骰主动开口）              （/表情 查库发图）
```

NapCat 只负责 QQ 收发；AstrBot 管人格、记忆、上下文与插件编排；模型只负责生成。

---

## 三个自研插件

### `voice_reply` — 语音回复

短句按概率转成语音条（**只发语音，不发文字**）。

- 触发：回复 ≤ `max_chars`（默认 30 字）+ `probability`（默认 0.25）
- 冷却：两条语音至少隔 3 分钟；每天上限 40 条
- 命令的回复永不转语音
- TTS 走 `edge-tts`（微软，免费无 Key），需要 `ffmpeg` 把 mp3 转 wav

### `proactive` — 主动搭话

没人说话时自己开口。**不是固定概率，是"命中线"模型**：

```
命中线 = min(100, 基础线 × 时机因子 + min(32, 连续没中 × 8))
掷 0~100，掷到线以下才开口
```

- 基础线：谷时 45 / 峰时 15（工作日 9–12、14–18 为峰时）
- 时机因子：超过 6 小时没说话 ×1.5
- 硬闸：夜间静默（0–8 点）、你 10 分钟内有消息就不插嘴、冷却 25 分钟、每天最多 3 条
- 命令：`/主动状态`、`/主动 演练`、`/主动 现在`

### `meme_cmd` — 表情包命令

绕过模型工具调用，直接查库发图：

```
/表情 开心     → 在 desc / 图内文字 / tags / scenes / 分类 五个字段里模糊匹配
```

同时兜底过滤模型偶尔泄漏的 `<||DSML||...>` 协议文本，避免把协议原文发给用户。

---

## 快速开始（Windows）

### 1. 装 Python 与 AstrBot

```powershell
winget install --id Python.Python.3.12 --exact --silent
python -m venv D:\qq-ai\venv
D:\qq-ai\venv\Scripts\python.exe -m pip install astrbot -i https://pypi.tuna.tsinghua.edu.cn/simple
```

初始化（**必须在 `D:\qq-ai\astrbot` 目录下执行**，否则会报 `not a valid AstrBot root directory`）：

```powershell
mkdir D:\qq-ai\astrbot
cd D:\qq-ai\astrbot
D:\qq-ai\venv\Scripts\astrbot.exe init -y
```

### 2. 装 NapCat（无头版，不动你本机的 QQ）

下载 [NapCat.Shell.Windows.Node.zip](https://github.com/NapNeko/NapCatQQ/releases/latest)，解压到：

```
D:\qq-ai\napcat\versions\<版本号>\resources\app\
```

启动：

```powershell
cd D:\qq-ai\napcat\versions\<版本号>\resources\app
node.exe index.js -q <小号QQ号>
```

首次会打印二维码和 WebUI 地址；二维码过期就开 WebUI 重新刷新。

### 3. 配置

1. 复制 `config-templates/cmd_config.template.json` → `D:\qq-ai\astrbot\data\cmd_config.json`，把 `<YOUR_WS_TOKEN>`、`<OWNER_QQ>` 换掉
2. 复制 `config-templates/stealer_config.template.json` → `D:\qq-ai\astrbot\data\config\astrbot_plugin_stealer_config.json`
3. 在 `D:\qq-ai\.env` 里写 `DEEPSEEK_API_KEY=sk-...`（**不要提交进 git**）
4. 把 `persona/大肥鱼.txt` 的内容写进人格（或用 `tools/set_persona_dafeiyu.py`）
5. 把 `plugins/` 下三个目录复制到 `D:\qq-ai\astrbot\data\plugins\`

### 4. 语音依赖（可选）

```powershell
D:\qq-ai\venv\Scripts\python.exe -m pip install edge-tts -i https://pypi.tuna.tsinghua.edu.cn/simple
```

还需要 `ffmpeg`：把 `ffmpeg.exe` 放进 `D:\qq-ai\bin\ffmpeg\`，并在 `start-astrbot.bat` 里加一行
`set "PATH=%ROOT%bin\ffmpeg;%PATH%"`。

### 5. 启动

```powershell
scripts\start-napcat.bat
scripts\start-astrbot.bat
```

后台：<http://127.0.0.1:6185>　NapCat 后台：<http://127.0.0.1:6099>（token 在 NapCat 日志里）

---

## 必踩的坑（血泪版）

1. **AstrBot 必须在自己的根目录启动**。`astrbot init` 生成的 `.astrbot` 标记在 `astrbot\` 下，在别的目录跑会直接退出。
2. **白名单要会话 ID**，不是纯 QQ 号：`qq:FriendMessage:<QQ号>`。写错会被静默拦截，日志里有一行 `not in the session allowlist`。
3. **DeepSeek 能看图，但要显式声明**：模型配置里 `modalities` 必须是 `["text","image"]`，否则框架在送模型前把图丢掉，只留占位符。
4. **想要原生工具调用，`modalities` 还得加 `tool_use`**。少了它，框架会把工具定义降级成文本提示，DeepSeek 就会吐 `<||DSML||>` 这种协议文本，被当成普通消息发给用户。
5. **NapCat WebUI 的 token 每次启动都变**，`webui.json` 里那个是旧值，以日志 `WebUi Token:` 为准。
6. **表情包插件只偷 QQ 表情（subType=1）**，普通图片会被跳过；`steal_chance` 默认 0.3，抽不中时只写 debug 日志，看起来像"没反应"。
7. **改完 prompt 要回头清历史**：我们曾因为人格里写着"你收不到图片""发不了语音"，导致能力打通后它仍嘴硬否认。增能力时，一定要把旧假设的提示词和历史一起清掉。
8. **计划任务别用 `IgnoreNew`**：杀掉进程后任务会卡在 `Queued`，之后 `/Run` 全部无效。用 `Parallel` + 允许电池启动。
9. **别同时跑两个 NapCat 实例**，同一个号会互相踢。

---

## 免责声明

个人 QQ 没有官方机器人接口，NapCat 属于第三方注入方案，**违反 QQ 用户协议**，存在被风控或封号的概率。
请只用**小号**测试，不要群发、不要高频。商用请走 [QQ 官方机器人平台](https://bot.q.qq.com/)。
