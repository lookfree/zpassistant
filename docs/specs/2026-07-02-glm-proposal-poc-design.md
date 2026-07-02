# GLM 技术方案智能生成 · 单体演示 POC 设计

日期：2026-07-02
状态：已与需求方逐节确认

## 1. 目标与范围

面向客户的**可真实演示** POC，展示「基于智谱 GLM 底座的技术方案智能生成」核心场景：
上传招标/需求文件 → 四阶段生成技术方案 → 导出 Word。同时支持客户自行上传历史
技术方案到智谱线上知识库（自动向量化），作为生成时的 RAG 参考。

**明确不做**：登录/多用户、数据库、计费、PDF 导出、多智能体并行。单体、单进程、
演示优先。

## 2. 技术选型

| 项 | 选择 | 理由 |
| --- | --- | --- |
| 形态 | 纯 Python 单体（FastAPI） | 单命令启动，POC 无需前后端分离 |
| 前端 | 静态 HTML/JS + Tailwind CDN | mbp 无 node，免构建 |
| 编排 | 轻量顺序编排（nodes/prompts/schemas 分层） | 不引入 LangGraph，POC 不需要 checkpoint |
| 模型 | 智谱 chat completions API（SSE 流式 + JSON 模式） | 需求指定 |
| 知识库 | 智谱线上知识库 API（托管向量化+检索） | 需求指定，本地零依赖 |
| 文档解析 | python-docx / pypdf | 招标文件本地抽文本 |
| Word 导出 | python-docx | 需求要求 Word 输出 |
| 状态 | 内存 + JSON 落盘 `data/tasks/<id>.json` | 重启不丢演示成果 |
| 部署 | Docker 单容器（python:3.12-slim）on mbp | mbp 有 Docker daemon（v29.2.1） |

## 3. 页面与演示流程

单页应用，左侧导航两个功能区：

### 3.1 知识库管理页
- 上传历史技术方案（docx/pdf/txt）→ 调智谱知识库 API 自动向量化
- 文档列表：文件名、大小、向量化状态（处理中/成功/失败）、删除
- 显示知识库 ID 与文档总数；首次启动自动创建知识库，ID 存 `data/kb.json`

### 3.2 方案生成页（核心演示区）
顶部四阶段步骤条，逐段推进：

1. **需求解析**：上传招标文件 → 流式展示解析过程 → 结构化结果五板块卡片
   （技术参数、工期里程碑、资质要求、评分标准、隐含风险预警）
2. **大纲规划**：展示知识库检索到的相似历史方案片段（体现"有据可依"）→
   生成树形两级大纲 → 用户可编辑（改标题/增删章节）→「确认大纲」进入下一步
3. **分段生成**：逐章推进；每章先显示检索到的参考片段，再 SSE 流式输出正文；
   侧栏展示全局术语表（体现术语统一）；整体进度条
4. **整合校验**：自动校验（章节完整性、参数一致性、关键条款缺失、格式符合度）
   → 问题清单可定位到章节 → 一键导出 Word 下载

每个阶段有「提示词」入口：查看/修改该阶段系统提示词（满足"客户可编写提示词"）。

## 4. 代码结构

```
app/
├── main.py              # FastAPI 入口 + 静态页面托管
├── config.py            # 环境变量（ZHIPU_API_KEY、GLM_MODEL、端口）
├── zhipu/
│   ├── llm.py           # chat API 封装（同步 + SSE 流式 + JSON 模式，失败重试一次）
│   └── kb.py            # 知识库 API（建库/传文档/查状态/检索/删除）
├── pipeline/
│   ├── state.py         # 任务状态（内存 dict + JSON 落盘）
│   ├── parse.py         # 阶段1：招标文件抽文本→分块→GLM JSON 模式→五板块结构化
│   ├── outline.py       # 阶段2：按项目类型/技术领域检索知识库→生成大纲 JSON 树
│   ├── generate.py      # 阶段3：逐章 检索→约束组装→流式生成→抽取术语并入全局术语表
│   └── review.py        # 阶段4：全文校验→问题清单 JSON；python-docx 模板渲染 Word
├── prompts/             # 每阶段一个提示词文件，界面可覆盖
└── static/              # 前端页面
```

### 4.1 阶段 3 约束组装
每章提示词 = 需求约束（阶段1输出）+ 大纲位置与本章要求 + 知识库参考片段 +
已定术语表 + 格式规范。生成后由模型抽取本章新术语，合并进全局术语映射表。

## 5. 智谱 API 对接

- 对话：`POST /api/paas/v4/chat/completions`，流式 SSE；结构化输出 JSON 模式 +
  Pydantic 校验，解析失败自动重试一次
- 知识库：创建知识库、上传文档（智谱侧切片+向量化）、查询状态、语义检索
- `GLM_MODEL` 可配置（默认 glm-4.6）；实现时先用真实 Key 冒烟实测各接口，
  以官方文档实际行为为准
- 容错：超时/限流统一重试与友好报错；任务状态落盘，演示中断可恢复

参考文档：
- 知识库 API：https://docs.bigmodel.cn/cn/guide/tools/knowledge/multimodal-retrieval
- 模型 API：https://docs.bigmodel.cn/cn/guide/develop/http/introduction

## 6. 演示素材

由本项目预制仿真素材（智慧园区/政务信息化类）：2~3 份历史技术方案（预上传知识库）
+ 1 份招标文件（演示时现场上传）。客户后续可上传自己的真实文档。

## 7. 部署（mbp）

- 目录：`/Users/Administrator/Documents/02-Work/zhoushuang/zpassistant`
- 单容器：`python:3.12-slim`，`docker compose up -d`，端口 `8100`；
  `data/` 挂载宿主目录持久化（任务状态、kb.json、导出 Word）
- docker CLI 路径：`/Applications/Docker.app/Contents/Resources/bin/docker`
- 流程：本地开发 → `rsync` 同步 → mbp 上 build + up
- 访问：`http://localhost:8100`（mbp 本机）或 `http://100.127.149.33:8100`
- `.env`（含 ZHIPU_API_KEY）只放 mbp 与本地，入 `.gitignore`

## 8. 测试口径（POC 级）

- 单测：提示词组装、大纲 JSON 解析、术语表合并、docx 渲染
- 冒烟：真实 Key 跑智谱各接口的脚本
- 端到端：界面完整走一遍四阶段人工演练
