# iTeachBuddy

iTeachBuddy 是面向高校教师的智能教学支持系统，围绕课堂评估、课程设计和教学咨询，帮助教师整理教学证据并形成可执行的改进建议。

在线系统：<https://iteachbuddy.ai>。由于并发限制，需要联系管理员发放邀请码注册。



## 功能概览

| 功能 | 输入 | 主要结果 |
| --- | --- | --- |
| 教学视频评估 | 教学视频；可附课件、大纲和讲稿 | 多模态客观特征、五维评价与 25 项二级指标、诊断报告及导出 |
| 教学智能问答 | 教学问题；可选知识库、附件和本人历史评估报告 | 结合来源材料生成回答，保留引用和会话记录 |
| 教学大纲优化 | PDF、Word、Markdown 等格式的大纲 | 保留原结构或按规范框架重构，检查课程目标、活动与评价的衔接，并导出结果 |

问答提供**通用问答、大纲设计、教学设计、学情诊断**四种模式。公共知识库涵盖教育学理论、北大教学沙龙、学科教学知识及国内外课程和教学案例。教师上传的附件和主动选取的历史评估报告与公共语料分开处理。

视频评估将文本、声音、画面和课件信息作为不同来源的证据；缺少某类材料时，依赖该材料的指标会标记为未评估。系统结果用于辅助教师复盘，不替代专家评价。

## 技术组成

| 部分 | 主要技术 |
| --- | --- |
| 前端 | Vue 3、Vite、Element Plus、ECharts |
| 后端 | Python 3.11、FastAPI、SQLAlchemy、PostgreSQL、Alembic |
| 检索与媒体处理 | Chroma、FFmpeg、faster-whisper、librosa、PyMuPDF |
| 模型服务 | 默认使用 DeepSeek Flash 处理文本、通义千问 Qwen3-VL-Plus 处理图像、text-embedding-v3 生成向量；语音识别在本地运行 |

代码按 `frontend/`、`backend/app/` 和 `ai_engine/` 分层；教学语料位于 `knowledge/corpora/`，模型及功能参数集中在 `config.yaml`。可通过 `PKU_MODE=local` 切换到本地 Ollama 模型，所需模型及硬件由使用者自行准备。

## 本地环境

- Python **3.11**、Node.js **18 或更高版本**。
- PostgreSQL 和客户端工具（`psql`、`pg_isready`）；也可用 Docker 启动项目提供的 PostgreSQL 16。
- FFmpeg，用于视频音频与画面处理。
- 默认云端模式需要 `DEEPSEEK_API_KEY` 和 `DASHSCOPE_API_KEY`。首次运行本地语音识别时还需下载模型权重。

以下命令在项目根目录执行。macOS 可用 `brew install ffmpeg postgresql@16` 安装系统依赖；其他系统请使用对应包管理器。

### 1. 安装依赖

```bash
python3.11 -m venv .venv
source .venv/bin/activate
make install
cp .env.example .env
```
编辑本机的 `.env`，填入两项模型 API Key，并按本机情况核对 `DATABASE_URL`。

### 2. 初始化数据库和知识库

```bash
make db-up
make db-migrate
make create-admin
make ingest
make check
```

`make db-up` 优先使用本机 5432 端口的 PostgreSQL；若没有运行中的数据库且 Docker 可用，则启动项目的数据库容器。默认本地连接使用 `pku2` 数据库和用户；若已有数据库配置不同，请先修改 `.env`。`make ingest` 会根据 `knowledge/corpora/` 中的文件建立 Chroma 索引，首次执行可能需要较长时间并调用向量模型 API。

### 3. 启动服务

在两个终端分别执行：

```bash
make backend
```

```bash
make frontend
```

打开 <http://localhost:5174> 登录使用。后端 OpenAPI 文档位于 <http://localhost:8010/docs>。`make frontend` 会安装前端依赖并启动 Vite 开发服务器。

## 本地配置

- `.env.example`：本地环境变量模板。
- `config.yaml`：模型、知识库和评估参数。当前云端文本模型使用 DeepSeek，视觉和向量模型使用阿里云百炼。
- `knowledge/corpora/`：公共教学语料；新增文档后运行 `make ingest` 更新索引。

