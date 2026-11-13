# Story Branch · 短剧创作工作台 v0.6.0

面向英语短剧创作的课程原型，使用 FastAPI、SQLite 与原生 JavaScript。当前交付为五人协作与六阶段创作版，支持独立阶段稿件、整条路线分支、人工确认和上游变更检查。

## 小组成员先看哪些文件

| 文件 | 主要内容 | 建议阅读者 |
|---|---|---|
| [README.md](README.md) | 首次安装、账号初始化、启动、模型配置与故障排查 | 所有人先看 |
| [TEAM_QUICKSTART.md](TEAM_QUICKSTART.md) | 按姓名分工、操作步骤与交付物 | 所有人 |
| [VALIDATION.md](VALIDATION.md) | 验收清单、问题记录和测试优先级 | 吕兴治、赵哲、彭奥 |
| [WRITING_SKILLS.md](WRITING_SKILLS.md) | 写作方法来源、提示词适配和对照试写 | 王司恺、吕兴治 |
| [ROADMAP.md](ROADMAP.md) | 项目范围、后续工作和汇报排期 | 所有人，尤其PPT负责人 |
| [DEVELOPMENT.md](DEVELOPMENT.md) | 技术实现、开发与验证记录 | 彭奥、赵哲；整理技术汇报时参考 |

## 初次部署：先在自己的电脑运行（Windows）

本节适合第一次接触项目的成员。先用样例模式跑通，不需要云服务器、Docker 或 DeepSeek 密钥。整个过程在自己的电脑完成；各人安装得到的是独立数据库，不会自动共享项目。

### 1. 准备 Python 和项目文件

已有可用的 Python 3.12 或 3.13 时，直接检查版本并跳到下载项目文件，不必重复安装。下面两种方式任选一种；本项目已在 Windows 的 Python 3.12.14 和 3.13.17 上验证。

**方式A：官网安装。** 从 [Python 官方 Windows 下载页](https://www.python.org/downloads/windows/) 下载适合电脑架构的安装包，新安装可选择 Python 3.13。安装时选择将 Python 加入 PATH。安装后完全关闭旧的 PowerShell、Windows Terminal 或 VS Code 终端，再重新打开检查：

```powershell
python --version
```

如果显示未找到命令或打开 Microsoft Store，先执行 `Get-Command python -All` 查看命令位置。指向 `Microsoft\WindowsApps` 时可能只是商店占位入口，并不说明 Python 已安装。若 `py -3.13 --version` 可用，可在下面创建环境时改用 `py -3.13 -m venv .venv`；使用3.12的成员替换版本号即可。`py` 是可选启动器，没有它也可以用 `python` 完成全部步骤。

如果 Python 已安装但旧终端尚未刷新 PATH，也可以直接调用已确认存在的解释器，例如默认用户目录的3.13：

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe" --version
```

该路径只适用于安装在此目录的电脑，不要把它当成所有安装方式的固定路径。

**方式B：国内镜像完整运行时（可选）。** 官网下载慢，或EXE安装器受本机MSI问题阻碍时，可以使用下面的解压配置方式。本例固定为 **Windows x64 的 Python 3.13.17**，已在本项目验证；ARM电脑请使用方式A选择对应版本。

下载来源是 [华为云Python镜像](https://repo.huaweicloud.com/python/3.13.17/python-3.13.17-amd64.zip)，校验值来自 [Python官网发布清单](https://www.python.org/ftp/python/3.13.17/windows-3.13.17.json)。这是包含标准库、venv和pip的完整运行时，不是名称中带 `embeddable` 的精简包。

先在PowerShell下载并校验；出现报错就停止，完成后应显示“校验通过”：

```powershell
$pythonZip = Join-Path $env:TEMP 'story-branch-python-3.13.17-amd64.zip'
curl.exe --fail --location --retry 2 --output "$pythonZip" "https://repo.huaweicloud.com/python/3.13.17/python-3.13.17-amd64.zip"
if ($LASTEXITCODE -ne 0) { throw '下载未完成，请检查网络后重试' }
$expectedHash = 'b26ca4b4ee51e157836049934d2b8eabd55939be296f3130254251b6df96ec2f'
if ((Get-FileHash -LiteralPath $pythonZip -Algorithm SHA256).Hash -ne $expectedHash) { throw '校验失败，请勿使用此文件' }
Write-Output '校验通过'
```

在同一个PowerShell窗口中，解压到新的用户目录并检查签名和版本：

```powershell
$pythonDir = Join-Path $env:LOCALAPPDATA 'Programs\Python\StoryBranch313'
if (Test-Path -LiteralPath $pythonDir) { throw '目标目录已存在，请先确认是否已有可用Python，不要覆盖' }
Expand-Archive -LiteralPath $pythonZip -DestinationPath $pythonDir
$pythonExe = Join-Path $pythonDir 'python.exe'
$signature = Get-AuthenticodeSignature -LiteralPath $pythonExe
if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'O=Python Software Foundation') { throw '签名检查未通过，请停止并联系技术同学' }
& $pythonExe --version
$env:Path = "$pythonDir;$env:Path"
python --version
```

应显示 `Python 3.13.17`。这只设置当前终端的PATH；继续在同一个窗口完成第2、3步即可。若中途关闭窗口，在项目根目录用下面命令创建环境，再接第3步的依赖安装：

```powershell
& "$env:LOCALAPPDATA\Programs\Python\StoryBranch313\python.exe" -m venv .venv
```

这种方式不注册MSI卸载项，也不修改系统PATH或修复Windows安装器。后续启动使用项目 `.venv`；不要移动或删除它依赖的上述Python目录。镜像示例固定了版本和哈希，更换版本时要同时核对对应官网清单。

**下载项目文件（两种方式相同）：**

打开本仓库 https://github.com/PPPAAA913/story-branch ，点击绿色 **Code → Download ZIP**，下载后解压。进入解压后的项目目录，必须能看到 `README.md`、`requirements.txt` 和 `studio` 文件夹。不要直接在压缩包内运行。

也可以用已安装的 Git 下载：

```powershell
git clone https://github.com/PPPAAA913/story-branch.git
cd story-branch
```

### 2. 在正确目录打开 PowerShell

如果使用 ZIP，在资源管理器打开上述项目文件夹，在地址栏输入 `powershell` 并回车。执行：

```powershell
Get-Location
Test-Path .\requirements.txt
```

第二条应显示 `True`；如果为 `False`，说明尚未进入项目根目录。

### 3. 创建环境并安装依赖

逐行执行，上一条成功后再执行下一条：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

这里始终直接调用虚拟环境的 Python，不需要执行激活脚本，也不需要修改 PowerShell 执行策略。安装依赖需要联网。出现红色报错时先保留完整错误信息，不要继续后续步骤。

**依赖安装的可选方式：清华镜像。** 完成环境创建后，如果默认下载源速度慢或超时，可用下面命令替代上面的 `pip install` 命令。两种来源任选一种即可，不需要都安装一次；这仅对当前命令生效，不修改电脑的全局pip配置：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt --index-url https://pypi.tuna.tsinghua.edu.cn/simple --timeout 30 --retries 2
.\.venv\Scripts\python.exe -m pip check
```

最后应显示 `No broken requirements found.`。Python安装包本身如从镜像下载，应核对对应版本在官网公布的校验值和数字签名；它与上面的依赖镜像是两回事。

### 4. 初始化五人账号

```powershell
.\.venv\Scripts\python.exe -m studio.bootstrap
```

成功后终端会显示一个 `data\initial-credentials-……txt` 文件的完整路径。在资源管理器中打开该文件，按每行的姓名、账号、随机密码找到自己的登录信息。没有统一默认密码，不要把示例文字当密码。

账号为 `peng_ao`（管理员）、`lyu_xingzhi`、`xu_xiaodong`、`wang_sikai`、`zhao_zhe`。在独立本机安装中，需要使用本机生成的密码；另一台电脑生成的密码不一定相同。需要配置模型时，由本机安装负责人使用初始化的管理员账号。

凭据文件不要提交 GitHub、发群或作为截图公开。统一服务器部署时，由管理员分别分发每人的账号密码。重复初始化不会重置已有密码；看到“accounts already exist”时，应找原先生成的凭据文件。

**忘记文件在哪：** 默认在项目根目录的 `data` 文件夹，文件名为 `initial-credentials-随机字符.txt`，每台电脑的后缀可能不同。先进入第2步的项目根目录，再运行以下命令，只列文件路径，不输出密码：

```powershell
Get-ChildItem -LiteralPath .\data -Filter 'initial-credentials-*.txt' | Select-Object -ExpandProperty FullName
```

也可以在资源管理器打开项目的 `data` 文件夹查找。如果只找到一个文件，可以这样用记事本打开：

```powershell
$credentialFiles = @(Get-ChildItem -LiteralPath .\data -Filter 'initial-credentials-*.txt')
if ($credentialFiles.Count -eq 1) {
    notepad.exe $credentialFiles[0].FullName
} else {
    Write-Output '未找到唯一文件，请根据上面的路径列表检查；不要删除数据库重新初始化。'
}
```

文件第一行是说明；之后每行依次为 **姓名、账号、密码**，用制表符隔开。管理员找 `PENG Ao / peng_ao` 那一行，最后一列就是登录密码；其他成员按自己的姓名查找。密码不是GitHub密码，也不是DeepSeek API Key。

如果设置了 `STUDIO_DB_PATH`，凭据文件保存在该数据库所在目录，需去那个目录查找；Docker方案则在容器的 `/app/data` 持久卷中，不是宿主机项目的 `data`。若有多个凭据文件，检查其中对应账号的行，不能仅凭文件日期判断；初始化只为当时缺少的账号生成新文件。若数据库里已有账号但凭据文件丢失，重复初始化不会找回或重置密码，请联系技术负责人处理。目前尚无网页改密/找回功能。

数据库只保存加盐的scrypt密码哈希，不能从中读出原密码；初始化文件则含明文初始密码，应由管理员私下保管并分别分发。各人独立本机安装与未来统一线上服务使用各自的数据库和密码，不能混用。

### 5. 启动服务并登录

```powershell
.\.venv\Scripts\python.exe -m uvicorn studio.main:app --host 127.0.0.1 --port 8766
```

看到 `Uvicorn running on http://127.0.0.1:8766` 后，保持这个终端窗口打开，在浏览器地址栏输入：

**http://127.0.0.1:8766/**

使用第4步的账号密码登录。这里是普通 `http`，不是 `https`。`127.0.0.1` 指当前电脑，这个地址不能直接发给异地组员访问。五个账号共享的是当前这个服务的数据；不同电脑各自运行的服务互不共享。

### 6. 做一次不收费的样例检查

1. 确认页面顶部显示“样例模式”。
2. 点击“新建”，填写项目名和简报。
3. 检查简报后点击“检查完成 · 确认本阶段”。
4. 进入“故事方向”，输入“生成三个故事方向”，点击发送。
5. 确认回复明确标有固定样例，并出现新版本。
6. 在右侧修改一句文字，保存为新版本，刷新检查内容仍在。

样例只验证流程，不代表模型写作质量。后续可按下面的六阶段说明继续试用。

### 7. 接入真实 DeepSeek（需要时再做）

1. 准备自己可用的 DeepSeek API Key，确认账户有余额、账户可用模型名称。
2. 用 `peng_ao` 管理员登录，打开“模型设置”。
3. 选择 DeepSeek，填写账户可用的模型名称和 API Key，保存配置。当前默认模型名只是预填值，需按真实账户核对。
4. 先发送一个短任务，确认得到非固定样例的回复，检查版本保存及账户消耗，再跑完整剧本流程。

保存设置本身不会调用模型。发送任务会产生账户计费；接口已接入，但本项目尚未完成真实账户联调，不保证只输入密钥就一定成功。界面填写的密钥只在当前服务进程有效，重启后需重新配置。普通组员在统一服务中不需要各自填写密钥。

本地 Python 启动不会自动读取 `.env` 文件；初次使用优先通过界面配置。服务器长期配置通过环境变量完成，Docker Compose 才会按现有配置读取 `.env`。

### 8. 停止、下次启动和备份

在运行服务的终端按 `Ctrl+C` 停止服务。下次打开同一项目目录的 PowerShell，只需重新执行第5步的启动命令，不必重新安装和初始化。

已保存项目默认在 `data\projects.db` 中。不要删除 `data` 文件夹，不要用新的下载目录替换旧目录中的数据。未保存草稿只暂存在当前浏览器标签页；关闭标签页或退出登录前先保存。

更新代码前，在项目目录运行：

```powershell
.\.venv\Scripts\python.exe -m studio.backup
```

终端会显示备份路径。备份与账号信息一样需要私下保管；初次更新建议让彭奥或赵哲协助保留数据再替换代码。

### 常见问题

| 现象 | 处理 |
|---|---|
| 找不到 requirements.txt 或 studio | 检查第2步，终端必须位于项目根目录 |
| 找不到 .venv 中的 python.exe | 第3步环境创建尚未成功，查看其报错 |
| python 打开商店，或安装后仍找不到命令 | 完全退出终端应用再打开；执行 `Get-Command python -All` 检查路径，必要时用实际解释器的完整路径创建环境 |
| Python安装器报0x80070003 | 保存安装日志，定位找不到的目录或缓存包；这是安装器问题，需要单独处理，反复安装项目依赖无法修复 |
| 安装依赖超时 | 检查网络，重试依赖安装；把完整报错交给技术同学 |
| 端口占用 / WinError 10048 | 先检查是否已有本项目服务；不要重复启动。也可将启动参数改为 `--port 8767`，浏览器同步改为8767 |
| 浏览器无法连接 | 确认服务终端仍运行、地址和端口一致，不要只双击HTML文件 |
| 账号或密码错误 | 查本机凭据文件，避免复制空格；GitHub账号不是平台账号 |
| 登录次数过多 | 等待15分钟，核对密码后再试 |
| 没有“模型设置”按钮 | 普通成员不显示，需管理员账号 |
| 模型401 / 402 / 429 | 分别检查密钥、账户余额、请求频率；不把密钥贴进问题截图 |
| 一直提示样例 | 检查模型设置是否切换并保存；服务重启后界面配置会丢失 |
| 下游不能生成 | 先保存并确认前序阶段；“待检查”需要人工核对后确认或重生成 |
| 另一位成员看不到项目 | 确认是否访问同一个服务；各自本机运行时数据不共享 |

macOS/Linux成员可在项目目录用 `python3 -m venv .venv` 创建环境，再将上述 `.\.venv\Scripts\python.exe` 替换为 `.venv/bin/python`；其余模块名和端口不变。当前浏览器验收主要在Windows完成，其他系统需由使用者实际验证。

## 六阶段使用方法

1. 新建项目，检查简报，点击“检查完成 · 确认本阶段”。
2. 依次进入故事方向、人物设定、前三集大纲、首集剧本；使用本阶段模板对话生成，或手工填写成果。
3. 故事方向生成候选后，将选定方向整理到稿件再确认。每阶段确认后，后续生成才能引用它。
4. 首集剧本要求英文正文与中文梗概。第六阶段保存审阅和修改建议；实际修改请回到对应阶段。
5. 从某个路线版本创建分支，继承当时所有阶段的文本、确认状态和引用依据。
6. 上游改动后，下游显示“待检查”。可按需重新生成，或者检查后确认沿用；系统不会擅自重写。
7. 导出整条路线包含六阶段成果和状态。版本对照查看当前阶段在另一版本中的内容。

旧版稿件保留在“历史稿件 · 待人工整理”，由人整理到相应阶段。样例模式提供固定阶段样本，不能用于评价真实 AI 质量。

## 本轮体验改进（v0.6.0）

- 左侧“历史导航”可折叠、限高滚动，右侧“版本对照”用于阅读另一版本，不再让长版本列表撑高网页。
- 普通分支可以删除，全组共享生效；主线受保护。删除前若有新版本则拒绝并要求刷新，当前分支未保存稿件需先处理。删除只移除分支入口，历史记录仍保留，以保障其他分支的引用链；不属于彻底清除数据。其他成员若仍打开已删除分支，刷新会回到现存分支；生成期间删除产生的完整结果会另存分支保留。
- 顶部“外观”可选跟随系统、浅色、深色，选择保存在当前浏览器。
- 默认输出上限从8192提高到81920 token；管理员在模型设置调整，持久部署通过 `DEEPSEEK_MAX_TOKENS=81920` 配置。此值是上限，不强制模型生成这么长，仍受服务商模型限制。应用允许1024–393216；根据所选模型实际能力设置。
- 上下文保护阈值从65000提高到650000字符；普通阶段稿件和回复最大500000字符，创作简报仍为8000字符。字符与token并非同一单位；超过模型实际上下文限制仍需拆分任务。
- 模型连接超时延长至600秒；长输出可能增加等待和计费，服务器反向代理也需匹配超时。截断与格式错误分别提示；未通过校验的返回可在页面下载（最多100万字符），不会自动保存成正式版本。请在刷新或切换项目之前下载，页面暂存不是数据库备份。

模型上限参考：[DeepSeek官方文档](https://api-docs.deepseek.com/quick_start/pricing/)。本轮通过模拟接口验证长文本与截断恢复，未代替真实账号的长篇生成验收。

## 已实现

- 登录、退出、12 小时会话、密码哈希、服务端会话摘要、登录尝试限制。
- 共享项目与逐项目成员检查，普通成员不能修改模型连接。
- 内置/自定义提示词、对话生成、人工编辑、Markdown 导出。
- 不可覆盖的版本，记录作者、提示词和模型来源。
- 从历史版本创建分支，查看另一版本全文。
- 人工保存冲突保留编辑内容，支持另存分支；AI 生成期间发生冲突，结果自动保留为分支。
- 标签页内草稿恢复（sessionStorage；退出登录会清除），不等同于服务端自动保存。
- 首次升级旧数据库时自动创建 `.pre-v03-*.db` 备份；旧版本标为“历史记录”。旧版流程数据保留，但旧接口已停用。

## 写作方法与任务模式

已适配五项 MIT 开源写作技能：人物动机与口吻、情节因果、场景写作、对白润色、证据式审阅。方法按阶段进入模型请求；页面可查看来源。

本轮任务支持创作/修改、只讨论、只审阅、英文对白润色。只讨论和只审阅由服务端保持原稿。每轮记录规则版本和来源，方便复盘。

详见 [WRITING_SKILLS.md](WRITING_SKILLS.md)，包含开源筛选、适配边界和对照试写命令。当前功能测试通过，真实模型质量提升尚未验证。

## 模型配置

管理员可在“模型设置”输入 DeepSeek 密钥；界面配置只在当前进程有效。持久部署请通过服务器环境变量 `DEEPSEEK_API_KEY` 和 `DEEPSEEK_MODEL` 配置。密钥不返回前端、不写入版本或数据库。

默认模型名称沿用现有配置，需在真实账户联调时验证可用性。没有配置密钥时运行固定样例模式；目前真实账户、质量与费用尚未验证。API 调用不等于模型训练。

当前上下文为本路线简报、当前阶段稿件、已确认上游成果、本阶段最近最多 8 个祖先版本的请求/回复及本轮提示词。生成异常不覆盖已有版本。

## 部署准备

已提供 Dockerfile 与 compose.yaml，尚未构建验证或部署。复制 `.env.example` 为 `.env` 后，容器方案的预期步骤为：

```sh
docker compose build
docker compose run --rm app python -m studio.bootstrap
docker compose up -d
```

数据库及初始化凭据保存在持久卷 `/app/data`；需要保留数据时不要执行 `docker compose down -v`，因为它会删除持久卷。当前端口只绑定服务器回环地址，在线部署还需配置 HTTPS 入口、实际允许域名与 `STUDIO_COOKIE_SECURE=1`。反向代理需传递正确 Host，并仅信任指定代理的转发头。预算、供应商与两地网络测试另行确认。

上线前仍需完成调用限额、真实 API 验证、备份恢复和实际访问测试。当前不能宣称已上线。

## 测试与后续

从仓库目录执行 `.\.venv\Scripts\python.exe -m unittest discover -s tests -v`（Windows）。当前 44 项测试通过；另完成双账号浏览器验证：登录、权限、共享项目、冲突草稿另存、作者记录、刷新恢复、退出与窄屏布局。

六阶段独立稿件、完整路线快照和下游待检查标记已完成；逐行差异、调用统计与限额、真实 API 联调和上线仍待完成。详细排期、真实分工和验收边界见 [ROADMAP.md](ROADMAP.md) 与 [DEVELOPMENT.md](DEVELOPMENT.md)。

仓库禁止提交数据库、账号凭据、API 密钥及 `.env`。公开源码不代表应用已经公开部署。

## 小组操作与备份

按姓名的简要指南见 [TEAM_QUICKSTART.md](TEAM_QUICKSTART.md)。运行 `python -m studio.backup` 可创建一致性快照并检查完整性；默认写入忽略的 data/backups。恢复时先复制备份，再将 STUDIO_DB_PATH 指向副本并用独立端口启动核对，避免覆盖运行中的数据库。
