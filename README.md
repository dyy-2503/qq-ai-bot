# QQ AI 好友机器人 · 部署套件

在 QQ 私聊里养一个"记得住事、说人话、有固定性格"的 AI 好友。
技术栈：**NapCatQQ**（协议端）+ **AstrBot**（应用层）+ 任意大模型 API（本项目以 DeepSeek 为例）。

> 本仓库只包含**部署脚本、配置模板、人格设定与排障工具**。
> 不含任何聊天记录、记忆文件、API Key 或账号登录态。

---

## 目录

| 路径 | 内容 |
|---|---|
| `docs/部署手册.md` | 从零开始的手册：选型、Docker/手动两种部署、人格、记忆、验收清单 |
| `docs/运维备忘.md` | 部署完成后实际踩过的坑与运维命令（更贴近真实使用） |
| `scripts/` | 启动 / 守护 / 打开后台的 Windows 脚本 |
| `config-templates/` | AstrBot 主配置与表情包插件的配置模板（已脱敏） |
| `persona/大肥鱼.txt` | 示例人格：拟人化鲸鱼娘 |
| `tools/` | 改人格、改配置、查表情包库的小脚本（Python） |

---

## 架构

```
QQ 小号 ──私聊──> NapCat（无头 NTQQ）──OneBot v11 WS──> AstrBot ──HTTPS──> DeepSeek
```

三者职责：NapCat 只负责 QQ 收发；AstrBot 管人格、记忆、上下文、拟人化；模型只负责生成。

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

### 4. 启动

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
4. **NapCat WebUI 的 token 每次启动都变**，`webui.json` 里那个是旧值，以日志 `WebUi Token:` 为准。`scripts/打开扫码页.bat` 会自动抓最新 token。
5. **表情包插件只偷 QQ 表情（subType=1）**，普通图片会被跳过；`steal_chance` 默认 0.3，抽不中时只写 debug 日志，看起来像"没反应"。
6. **别同时跑两个 NapCat 实例**，同一个号会互相踢。
7. **改完能力要回头清 prompt**：我们曾因为人格里写着"你收不到图片"，导致视觉打通后它仍嘴硬说"只看到占位符"。

---

## 免责声明

个人 QQ 没有官方机器人接口，NapCat 属于第三方注入方案，**违反 QQ 用户协议**，存在被风控或封号的概率。
请只用**小号**测试，不要群发、不要高频。商用请走 [QQ 官方机器人平台](https://bot.q.qq.com/)。
