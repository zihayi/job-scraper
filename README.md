# 招聘信息抓取器 (job-scraper)

输入一个网址，自动抓取该页面并抽取出结构化的招聘信息。

## 它如何应对“格式不固定”

招聘网页的排版千差万别：有的用表格、有的用列表、有的把信息塞在大段文字里。
靠写死正则或 CSS 选择器几乎无法通用。本程序的做法是：

1. **抓取** 网页 HTML（`fetch.py`）
2. **清洗** 成纯文本，去掉脚本、样式、导航噪声（`clean.py`）
3. **抽取**：把文本交给 DeepSeek，用 JSON 模式按固定结构输出（`extract.py`）

无论原网页怎么排版，模型都能理解语义并归一化成统一字段。

## 安装

```bash
cd job-scraper
pip install -r requirements.txt
```

动态抓取用 Playwright 复用系统已安装的 **Edge**（`channel="msedge"`），因此无需运行
`playwright install` 下载浏览器。

## 配置

### API Key 与模型（推荐：在网页里填）

启动网页后，点右上角 **设置**，即可直接填写 **DeepSeek API Key**，并分别选择岗位抽取模型
和岗位聊天模型。抽取默认使用 DeepSeek Chat，聊天默认使用 DeepSeek Reasoner。设置保存在
本机 `settings.json`，重启后仍生效。

也可用环境变量（命令行模式下使用，或作为网页未填时的回退）：

```bash
export DEEPSEEK_API_KEY=sk-...                 # Windows PowerShell: $env:DEEPSEEK_API_KEY="sk-..."
export JOB_SCRAPER_MODEL=deepseek-chat         # 可选，岗位抽取模型
export JOB_CHAT_MODEL=deepseek-reasoner        # 可选，岗位聊天模型
```

生效优先级：**网页设置 > 环境变量 > 默认值**。

公司网络若拦截 SSL，系统可能只在操作系统证书库中安装了公司根证书。本项目已集成
`truststore`，导入时会自动改用操作系统证书库验证。

## 使用

### 方式一：网页（推荐，可抓取 + 收藏跟踪）

```bash
python app.py
```

浏览器打开 <http://127.0.0.1:5000>，即可：

- 粘贴职位网址抓取（SPA 页面如大疆，勾选“动态渲染”）
- 自动收藏抓取结果到跟踪列表
- 可通过“添加职位”手动录入岗位信息
- 为每条收藏设置求职进度（待投递 / 已投递 / 笔试中 / 面试中 / 已offer / 已淘汰）和备注
- 标星重点职位并按进度筛选
- 使用 DeepSeek 与已保存岗位进行问答、比较和总结，可切换右侧栏或全页面聊天
- 聊天选择 DeepSeek Reasoner 时，点击“查看思维链”可展开详细分析过程
- 导出 Excel 职位名单

收藏数据存在 `saved_jobs.json`（可用 `JOB_STORE_PATH` 改路径）。
聊天历史存在 `chat_history.json`（可用 `CHAT_STORE_PATH` 改路径）。

### 方式二：命令行

```bash
python main.py https://example.com/careers              # 静态页面
python main.py "https://...#/job/..." --dynamic          # SPA / 动态页面
python main.py <url> --dynamic -o result.json            # 指定输出
```

终端会打印职位列表，同时把完整结果存成 JSON。

## 输出字段

每条职位包含：`title`、`company`、`location`、`salary`、`employment_type`、
`description`、`requirements`、`url`。缺失的字段会留空，不会编造。
`location` 统一保存为城市名，多个城市使用中文顿号分隔，例如 `深圳、上海`。

## 已知限制

- 动态抓取依赖系统已安装的 Edge（或修改 `fetch_dynamic.py` 里的 `channel`）。
- 超长页面会截断到约 4 万字符。
- 抽取需要可用的 DeepSeek API Key 和网络连接。
