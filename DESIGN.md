# Paperazzi：基于 Zotero 的学术作者知识库与关系网络

**状态：Design v0.1**  
**目标：Local-first / Human-triggered / AI-assisted / Evidence-first**

---

## 0. 项目一句话定义

Paperazzi 是一个围绕个人 Zotero 文献库构建的**作者知识库、学术关系网络与作者动态追踪系统**。

它以 Zotero 中已经收藏的论文为“研究兴趣的事实入口”，抽取第一作者、通讯作者及重要合作者，为每位作者建立可追溯来源的个人档案，并以网页方式展示作者、论文、机构、研究主题及其关系网络。

系统不要求实时联网，也不要求持续自动爬取。所有更新均由用户主动触发：

1. 本地程序检查 Zotero 与上次快照的差异；
2. 本地 AI/确定性程序完成文献解析、作者识别和需求生成；
3. 对于需要互联网的信息，生成固定格式的“在线检索需求包”；
4. 在线 AI 根据需求检索公开资料并返回固定格式 ZIP；
5. 本地程序校验 ZIP、做作者消歧、冲突检测和数据合并；
6. 用户可以在网页的 Review Center 中查看证据、修正错误和执行 merge/split。

核心原则：**AI 不直接写数据库。AI 只产生候选事实与证据；数据库修改由确定性程序执行。**

---

# 1. 主要目标

## 1.1 作者数据库

针对 Zotero 中论文涉及的作者，重点维护：

- 第一作者；
- 通讯作者；
- 重要/高频合作者；
- 用户手工加入的重点关注作者。

每位作者建立统一档案：

- 标准姓名与姓名变体；
- ORCID / OpenAlex / Semantic Scholar 等外部 ID；
- 当前单位、职位；
- 历史任职经历；
- 教育经历；
- 博士导师/博士后导师等可验证学术关系；
- 出生日期或出生年份（仅在公开、可靠来源明确给出时）；
- 性别/性别认同（仅保存公开资料中明确陈述的信息，不从姓名、照片或国籍推断）；
- 个人主页；
- ORCID；
- Google Scholar / Semantic Scholar / GitHub / LinkedIn / X 等公开页面链接；
- 头像/照片及其来源；
- 简短人物简介；
- AI 总结的研究方向；
- 研究关键词；
- 研究方向随时间的变化；
- 论文时间线；
- 新闻、奖项、职位变化、基金、学术报告等动态。

所有非 Zotero 原始字段都必须保留**来源、检索时间、可信度和生成方式**。

## 1.2 作者关系网络

至少支持以下关系层：

### A. 直接事实关系

- coauthor：共同署名；
- first_author ↔ corresponding_author；
- advisor → student；
- postdoc_advisor → postdoc；
- same_lab / same_group（有证据时）；
- same_institution；
- former_same_institution；
- collaborator（由多篇共同论文归纳）；
- paper_citation（论文层关系，可进一步投影为作者层关系）。

### B. 计算关系

- topic_similarity：研究主题相似度；
- collaboration_strength：合作强度；
- collaboration_recency：近期合作强度；
- shared_reference / bibliographic_similarity；
- local_library_overlap：在本地 Zotero 关注范围内的共同覆盖度。

计算关系必须与“事实关系”视觉上区分。

## 1.3 Zotero 论文入口

网页中的论文记录必须保留 Zotero item key 和 attachment key。

点击论文时至少提供：

- **Open PDF**：通过本地 Paperazzi 后端/Zotero Local API 打开本地 PDF；
- **Show in Zotero**：定位到 Zotero 条目；
- DOI / publisher 页面；
- 作者详情；
- 本论文在作者网络中的位置。

Paperazzi 不复制 Zotero 成为第二套文献管理系统；Zotero 始终是本地 PDF 和核心书目元数据的主数据源。

---

# 2. 核心架构原则

## 2.1 Zotero 是文献 Source of Truth

优先使用 Zotero Desktop 的 Local API，而不是直接读写 `zotero.sqlite`。

原因：

- Local API 与 Zotero Web API v3 基本一致；
- 可以通过 library/item version 做增量检查；
- 可获得 item、creator、collection 和 attachment；
- Local API 可返回 attachment 的本地文件位置；
- 避免直接绑定 Zotero 内部 SQLite schema。

Paperazzi 只缓存自己需要的规范化论文元数据和 Zotero key。

## 2.2 AI 不拥有数据库写权限

采用三层结构：

```text
AI / Internet Search
        ↓
Candidate JSON + Evidence
        ↓
Schema Validator + Resolver + Merge Rules
        ↓
Paperazzi Database
```

AI 不能直接执行 SQL UPDATE。

这样可保证：

- 同一个输入包可以重复导入并得到一致结果；
- 模型更换不会改变数据库语义；
- 每个字段可追溯；
- 错误可以回滚；
- 作者同名误合并不会不可逆地污染数据。

## 2.3 Evidence-first

数据库不只保存“当前答案”，还保存“这个答案为什么存在”。

例如：

```text
Current affiliation:
University X, Professor

Evidence:
1. University X faculty page, retrieved 2026-08-16
2. ORCID employment record, retrieved 2026-08-16

Confidence: verified
```

人物资料的来源优先级建议：

1. 大学/研究机构官方主页；
2. ORCID；
3. 本人实验室/个人主页；
4. 论文出版社页面；
5. 基金机构、学会、会议官方页面；
6. OpenAlex / Semantic Scholar；
7. 可靠新闻来源；
8. 社交网络；
9. 其他聚合网站。

任何冲突都保留，不由 AI 静默覆盖。

## 2.4 数据不是“实时数据库”

系统采用 batch run：

```text
Zotero Update Run
Author Enrichment Run
Monthly Watch Run
Manual Repair Run
```

每次 run 都生成唯一 `run_id`，记录：

- 输入快照；
- 产生的任务；
- AI 返回包；
- 实际写入；
- 冲突；
- 失败项。

---

# 3. 三条核心工作流

## 3.1 Workflow A：Zotero 增量更新

用户执行：

```text
paperazzi update-zotero
```

流程：

```text
读取上次 Zotero library version
        ↓
调用 Zotero Local API ?since=<version>
        ↓
new / modified / deleted items
        ↓
规范化论文元数据
        ↓
解析 authorship
        ↓
作者 identity resolution
        ↓
重新计算第一作者/通讯作者/合作者关系
        ↓
发现未知作者或资料缺失作者
        ↓
生成 enrichment request
```

### 第一作者

由 creator 顺序确定。

### 通讯作者

通讯作者信息不能假定 Zotero 必然包含。

建议按以下来源确定：

1. 已有人工标记；
2. PDF 第一页/author information/correspondence 信息；
3. publisher metadata；
4. 在线检索结果。

保存：

```text
is_corresponding
corresponding_confidence
corresponding_source
```

一篇论文允许多个通讯作者。

## 3.2 Workflow B：新作者资料补全

当 Zotero 增加论文后，本地程序首先做作者消歧。

对于新增或资料不足的作者，生成：

```text
requests/author_enrichment_2026-08-16/
├── REQUEST.md
├── manifest.json
├── authors.jsonl
└── schemas/
    ├── author_profile.schema.json
    ├── evidence.schema.json
    └── media.schema.json
```

`authors.jsonl` 中每项包含本地已知信息，例如：

```json
{
  "request_id": "ARQ-000012",
  "author_id": "A-01J...",
  "name": "Example Author",
  "known_affiliations": ["University X"],
  "known_papers": [
    {"title": "...", "doi": "...", "year": 2025}
  ],
  "known_external_ids": {
    "orcid": null,
    "openalex": null
  },
  "requested_fields": [
    "identity",
    "current_position",
    "affiliation_history",
    "education",
    "public_profiles",
    "research_summary",
    "keywords",
    "photo",
    "notable_news"
  ]
}
```

在线 AI 返回固定格式 ZIP：

```text
paperazzi-enrichment-result.zip
├── manifest.json
├── authors/
│   ├── ARQ-000012.json
│   └── ARQ-000013.json
├── evidence/
│   ├── ARQ-000012.jsonl
│   └── ARQ-000013.jsonl
└── assets/
    └── ...
```

导入流程：

```text
ZIP
 ↓
manifest validation
 ↓
JSON Schema validation
 ↓
identity check
 ↓
field-level evidence validation
 ↓
conflict detection
 ↓
merge proposal
 ↓
auto-accept safe fields / queue uncertain fields
```

## 3.3 Workflow C：每月作者动态更新

用户执行：

```text
paperazzi watch prepare
```

程序遍历作者，但不盲目要求完整重查。

根据每个字段的 `last_checked_at` 生成增量需求：

```text
Check since 2026-07-01:
- new papers
- affiliation / position changes
- awards
- grants
- conference / invited talks
- lab moves
- major news
- newly discovered public profiles
```

在线 AI 返回：

```text
paperazzi-watch-2026-08.zip
├── manifest.json
├── events/
│   ├── A-xxx.json
│   └── A-yyy.json
├── works/
│   └── ...
└── evidence/
    └── ...
```

导入后网页首页出现：

```text
Monthly Digest

+ 17 new papers
+ 2 affiliation changes
+ 4 awards/grants
+ 8 public news events
+ 6 possible identity conflicts
+ 11 papers not yet in Zotero
```

---

# 4. 作者身份消歧：整个系统最关键的部分

同名作者误合并的破坏性远高于漏掉一条新闻，因此 identity resolution 必须是独立模块。

## 4.1 内部永久 ID

永远不要把姓名、ORCID 或 OpenAlex ID 当数据库主键。

使用：

```text
author_id = UUIDv7 / ULID
```

外部 ID 都只是 identity links。

## 4.2 消歧证据

候选作者评分可以使用：

- ORCID 精确匹配；
- DOI-author-ORCID 映射；
- 单位；
- email domain；
- 已知合作者重合；
- 研究主题；
- 论文标题/年份；
- 姓名变体；
- 学术履历时间是否可能。

## 4.3 状态

```text
IDENTIFIED
PROBABLE
AMBIGUOUS
UNRESOLVED
CONFLICT
```

低置信度候选不自动 merge。

## 4.4 人工 Merge / Split

网页必须提供：

- Merge authors；
- Split identity；
- Mark not same person；
- Lock identity；
- Preferred name；
- 手工绑定 ORCID/OpenAlex。

`Lock identity` 后，AI 更新不得自动改变身份。

---

# 5. 数据模型

推荐 SQLite 起步。该项目的数据规模主要是数千到数万作者和论文，不需要一开始引入 Neo4j。

关系网络仍然存储为关系表，图分析时由 Python/igraph/NetworkX 或 SQL 投影。

## 5.1 papers

```text
paper_id
zotero_item_key
zotero_item_version
title
doi
pmid
arxiv_id
journal
year
publication_date
abstract
language
volume
issue
pages
url
created_at
updated_at
removed_from_zotero_at
```

## 5.2 paper_attachments

```text
attachment_id
paper_id
zotero_attachment_key
content_type
filename
is_primary_pdf
```

不长期硬编码绝对 PDF 路径；需要打开时向 Zotero Local API 请求当前 attachment 路径。

## 5.3 authors

```text
author_id
preferred_name
given_name
family_name
bio_summary
current_affiliation_id
current_position
birth_date
birth_year
gender_public_statement
research_summary
identity_status
identity_locked
created_at
updated_at
last_enriched_at
last_watched_at
```

`birth_date`、`gender_public_statement` 默认 NULL。

禁止根据姓名、照片或模型常识自动推断。

## 5.4 author_aliases

```text
author_id
name
name_type
language
source_id
```

## 5.5 external_identities

```text
author_id
type        # orcid/openalex/semantic_scholar/scopus/researcherid/github/...
value
url
confidence
verified
source_id
```

## 5.6 authorships

这是 Paperazzi 最重要的关系表之一。

```text
paper_id
author_id
author_order
role                # first / middle / last
is_corresponding
corresponding_confidence
affiliation_text
source_id
```

## 5.7 institutions

```text
institution_id
name
normalized_name
ror_id
openalex_id
country
city
url
```

## 5.8 affiliations

```text
author_id
institution_id
position
start_date
end_date
is_current
confidence
source_id
```

## 5.9 education

```text
author_id
institution_id
degree
field
start_year
end_year
advisor_author_id
confidence
source_id
```

## 5.10 author_relationships

```text
relationship_id
source_author_id
target_author_id
type
weight
first_year
last_year
is_inferred
confidence
source_id
```

`type` 示例：

```text
coauthor
advisor
postdoc_advisor
same_lab
same_institution
topic_similarity
```

其中 coauthor 不应由 AI 创建，而由 authorships 表确定性计算。

## 5.11 topics

```text
topic_id
name
normalized_name
parent_topic_id
source
```

## 5.12 author_topics

```text
author_id
topic_id
score
start_year
end_year
method
```

这使网页可以显示“研究方向演化”，而不是只有一组永久关键词。

## 5.13 events

```text
event_id
author_id
event_type
title
summary
event_date
url
importance
confidence
source_id
first_seen_at
```

类型：

```text
new_paper
position_change
institution_change
award
grant
conference
interview
lab_news
public_announcement
other
```

## 5.14 media_assets

```text
asset_id
author_id
type
local_path
remote_url
source_url
license
retrieved_at
```

图片建议默认保存 URL + 来源。只有许可证/使用条件允许或用户明确选择时才缓存本地副本。

## 5.15 sources

```text
source_id
url
title
publisher_or_site
source_type
retrieved_at
content_hash
archive_path
```

## 5.16 claims

建议增加通用 claim 层，解决“同一个字段有多个相互冲突来源”的问题。

```text
claim_id
subject_type
subject_id
predicate
value_json
valid_from
valid_to
confidence
status
source_id
extractor
run_id
created_at
```

例如：

```text
subject=A123
predicate=current_position
value={"position":"Professor","institution":"..."}
status=accepted
```

网页展示的是 accepted claim；旧 claim 和冲突 claim 仍然保留。

## 5.17 runs / jobs

```text
runs
- run_id
- run_type
- started_at
- finished_at
- status
- input_manifest
- result_summary

jobs
- job_id
- run_id
- subject_id
- request_type
- status
- request_path
- result_path
```

---

# 6. 网页信息架构

Paperazzi 应该是**人物中心的科研情报界面**，而不是 Zotero 的网页复制品。

## 6.1 Home / Dashboard

首页回答：**“我的文献库背后有哪些人，最近发生了什么？”**

建议布局：

### 顶部指标

```text
Papers      Authors      Corresponding Authors      Institutions
2,814       4,932        781                        642
```

### 中部左：Recent Update Feed

- 新增 Zotero 论文；
- 新识别通讯作者；
- 已关注作者新论文；
- 人事变动；
- 奖项/基金/新闻。

### 中部右：Network Pulse

小型作者网络图：

- 新出现的作者；
- 最近合作边；
- 热点 cluster。

### 底部

- Unresolved Authors；
- Conflicting Claims；
- Missing Author Profiles；
- Papers outside Zotero。

## 6.2 Authors

默认是信息密度较高的 table/card 混合页面。

过滤：

- first author；
- corresponding author；
- both；
- institution；
- country；
- topic；
- year active；
- Zotero paper count；
- watchlist；
- profile completeness；
- identity confidence。

卡片信息：

```text
[photo] Name
        Position @ Institution
        SF · excited states · multireference methods
        12 papers in Zotero · 7 coauthors in tracked network
        Corresponding author in 5 local papers
```

## 6.3 Author Profile

这是核心页面。

### Hero

- photo；
- preferred name；
- current title/institution；
- ORCID 等链接；
- watch/unwatch；
- profile confidence；
- last checked。

### Research Summary

AI 总结，但明确标注生成时间和基础论文范围。

### Topic Evolution

例如：

```text
2008–2013  Organic electronics
2013–2018  Singlet fission
2018–2023  Exciton dynamics / ultrafast spectroscopy
2023–      Quantum materials / data-driven molecular design
```

用 timeline / stacked area 展示。

### Local Papers

只显示 Zotero 中已有论文，支持：

- Open PDF；
- Show in Zotero；
- DOI；
- first/corresponding 标记。

### External Recent Papers

显示在线更新发现、但**尚未进入 Zotero**的论文。

这是一个非常有价值的功能：Paperazzi 不只整理过去，还可以帮助发现“我关注的人最近发表了什么”。

状态：

```text
IN_ZOTERO
NOT_IN_ZOTERO
POSSIBLE_DUPLICATE
```

### Collaborators

- top collaborators；
- 合作次数；
- 最近一次合作；
- 点击进入 relationship view。

### Career / Education

时间线展示教育和任职经历。

### News & Events

按月/年显示。

### Evidence

每个字段可点击 `Sources`，展开来源。

## 6.4 Network Explorer

参考 Connected Papers / ResearchRabbit 的交互逻辑，但节点主体是**作者**。

网络图支持 layer：

```text
[✓] Coauthor
[ ] Advisor/student
[ ] Same institution
[ ] Topic similarity
[ ] Citation-derived
```

控制：

- time range；
- minimum edge weight；
- first/corresponding only；
- institution；
- topic；
- 1-hop / 2-hop；
- local papers only / external papers included。

节点：

- size：默认 local paper count；
- ring：通讯作者状态；
- label：作者名；
- cluster：community detection；
- hover：机构、方向、论文数。

点击节点后右侧 drawer 显示作者摘要。

### Relationship Path

非常建议增加：

```text
Find path: Author A → Author B
```

返回：

```text
A
 └─ coauthored 3 papers with B
      └─ PhD advisor of C
           └─ coauthored with D
```

每一步可查看证据。

## 6.5 Papers

这里不是完整 Zotero UI，而是人物网络的论文索引。

字段：

- title；
- year；
- journal；
- first author；
- corresponding author；
- tracked author count；
- topics；
- PDF status。

## 6.6 Institutions

展示：

- 当前跟踪作者；
- 历史作者；
- 本地论文数；
- 研究主题；
- 作者之间的内部网络。

## 6.7 Topics

每个 topic 页面显示：

- 相关作者；
- 相关论文；
- 年度趋势；
- 机构；
- 作者 community。

## 6.8 Updates

管理所有 batch run：

```text
Zotero Sync
Enrichment Requests
Import AI Package
Monthly Watch
```

并显示：

- 待导出的 request；
- 待导入 ZIP；
- 校验错误；
- 本次改动摘要。

## 6.9 Review Center

必须存在。

页面队列：

```text
Identity conflicts
Possible duplicates
Claim conflicts
Low-confidence corresponding authors
Missing sources
Broken profile URLs
```

系统可信度很大程度取决于这个页面，而不是 AI 模型有多强。

---

# 7. 值得增加的功能

## 7.1 Library Gap Detector

每月更新后比较：

```text
Known recent works of tracked authors
vs.
Papers currently in Zotero
```

得到：

```text
Missing from Zotero
```

用户可直接看到 DOI、摘要和作者，然后决定是否加入 Zotero。

这是建议作为 v1 的核心特色之一。

## 7.2 Author Watchlist

不是所有 5,000 个作者都值得同样强度更新。

级别：

```text
NORMAL
WATCH
HIGH_PRIORITY
IGNORE_EXTERNAL_UPDATES
```

月度在线检索可优先处理重点作者。

## 7.3 Research Lineage

当导师关系有可靠来源时生成：

```text
academic genealogy
```

这与普通 coauthor graph 是不同的信息层。

## 7.4 Collaboration Lifecycle

显示某两位作者合作历史：

```text
2012  first paper
2013  3 papers
2014  5 papers
2015  1 paper
2016– no collaboration
```

可辅助判断实验室成员、长期合作组、一次性合作等。

## 7.5 Topic Drift / Research Pivot

不是只生成 `keywords=[...]`，而是按时间窗口重新聚类论文关键词/embedding。

可识别：

- 研究方向转移；
- 新方向形成；
- 合作网络改变后带来的主题改变。

## 7.6 “Why do I know this author?”

作者页给出：

```text
Entered Paperazzi because:
2026-07-14 Zotero item ABC123
Role: corresponding author
Collection: Singlet Fission / NOCI
```

这能把人物信息重新连接回用户自己的研究上下文。

## 7.7 Data Completeness Score

不是评价学者，而是评价**数据库对该人物了解有多完整**：

```text
Identity      100%
Affiliation   100%
Education      70%
Public links   80%
Research       90%
Recent check  stale
```

用于生成下一次 enrichment request。

---

# 8. 技术栈建议

目标是固定、简单、容易让本地 AI/Codex 操作。

## Backend

```text
Python
FastAPI
SQLAlchemy 2
Alembic
Pydantic
SQLite + WAL + FTS5
httpx
```

可选分析库：

```text
igraph
NetworkX
scikit-learn
```

不建议 v1 上 Neo4j、PostgreSQL、Elasticsearch。

## Frontend

```text
React
TypeScript
Vite
TanStack Query
TanStack Table
Cytoscape.js
Apache ECharts
```

UI 可以使用轻量组件库，但业务数据结构不要绑定组件库。

## Search

v1：SQLite FTS5。

搜索对象：

- author names；
- aliases；
- papers；
- institutions；
- topics；
- event titles/summaries。

## Local AI

AI 层做成 provider adapter，不把系统绑定到某一个模型：

```text
LocalAgentProvider
├── cli provider
├── OpenAI-compatible provider
└── manual package provider
```

但无论模型是什么，都只能输出 schema-defined JSON。

---

# 9. 推荐目录结构

```text
Paperazzi/
├── README.md
├── DESIGN.md
├── pyproject.toml
├── package.json
├── config/
│   └── paperazzi.example.toml
├── schemas/
│   ├── author_profile.schema.json
│   ├── author_update.schema.json
│   ├── evidence.schema.json
│   ├── request_manifest.schema.json
│   └── result_manifest.schema.json
├── backend/
│   └── paperazzi/
│       ├── api/
│       ├── db/
│       ├── models/
│       ├── zotero/
│       ├── identity/
│       ├── ingest/
│       ├── enrichment/
│       ├── graph/
│       ├── search/
│       └── cli/
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   ├── components/
│   │   ├── graph/
│   │   └── api/
│   └── ...
├── data/
│   ├── paperazzi.sqlite3
│   ├── cache/
│   ├── requests/
│   ├── imports/
│   └── assets/
├── tests/
└── docs/
```

`data/` 默认全部加入 `.gitignore`。

人物资料、Zotero 元数据和照片不应默认提交 GitHub。

---

# 10. 外部数据源策略

Paperazzi 不应依赖任何一个学术平台做唯一身份源。

## Zotero

用途：

- 本地收藏论文；
- creator 顺序；
- PDF attachment；
- collections/tags；
- 增量版本。

## ORCID

用途：

- 稳定身份 ID；
- employment；
- education；
- works；
- public profile。

## OpenAlex

用途：

- author disambiguation 候选；
- works；
- institutions；
- topics；
- citation graph；
- affiliation history 的辅助信息。

## Semantic Scholar

用途：

- author/paper identity 交叉验证；
- citation/reference；
- author paper list；
- bibliometric metadata。

## Crossref / Publisher

用途：

- DOI metadata；
- author/affiliation metadata；
- publication date；
- publisher landing page。

## University / Lab / Personal sites

用途：

- 当前职位；
- 教育经历；
- biography；
- portrait；
- news；
- group membership。

任何来源数据均先进入 evidence/claim 层，不直接覆盖 author 表。

---

# 11. 公开人物信息的边界

Paperazzi 的目标是科研知识组织，不应成为无来源的人物画像生成器。

规则：

1. 只收集公开可访问的职业/学术相关资料；
2. 出生日期、性别等字段只在公开来源明确陈述时保存；
3. 不从姓名、照片、语言、国籍推断性别、年龄、族裔等属性；
4. 对照片保存来源 URL 和许可信息；
5. 不要求在线 AI 绕过登录墙、付费墙或访问控制；
6. 每条人物事实应能回答“来源是什么”；
7. 支持删除某个字段、某个 source 或某个 author 的 enrichment 数据；
8. 对错误身份合并提供完整 undo/repair 路径。

---

# 12. UI 参考方向

不是复制这些产品，而是分别吸收一种交互模式：

- **Connected Papers**：force-directed graph、局部关系探索；
- **ResearchRabbit**：论文/作者/概念关系探索和 collection 思维；
- **OpenAlex**：author/work/institution/topic 作为知识图谱实体；
- **Semantic Scholar**：作者页面 + 论文列表 + citation metadata；
- **ORCID**：结构化个人履历和稳定 researcher identity。

Paperazzi 的差异是：

> 它不是从“全球文献搜索”出发，而是从“我的 Zotero 里已经出现的人”出发。

因此首页和网络图应优先体现 **local relevance**，而不是全局 citation count。

---

# 13. MVP 范围建议

## Phase 0 — Foundation

- repository skeleton；
- SQLite schema；
- migrations；
- Zotero Local API connectivity；
- initial full import；
- incremental Zotero import；
- authors/papers/authorships。

## Phase 1 — Core Website

- Dashboard；
- Authors；
- Author Profile；
- Papers；
- local PDF opening；
- simple coauthor graph；
- full-text search。

## Phase 2 — Identity + AI Package Protocol

- author resolution；
- external IDs；
- JSON Schemas；
- enrichment request export；
- ZIP result import；
- sources/claims；
- Review Center。

## Phase 3 — Research Intelligence

- monthly watch workflow；
- external recent papers；
- Library Gap Detector；
- news/events；
- watchlist。

## Phase 4 — Advanced Graph

- multi-layer author network；
- topic evolution；
- community detection；
- relationship path；
- academic genealogy；
- institution/topic views。

---

# 14. 第一版开发验收标准

Paperazzi v0.1 不需要“所有人物资料都完整”。它需要先证明整个闭环可靠：

```text
Zotero 新增一篇论文
       ↓
Paperazzi 发现它
       ↓
正确识别第一作者/作者顺序
       ↓
生成未知作者 enrichment request
       ↓
在线 AI 返回标准 ZIP
       ↓
本地校验并创建作者档案
       ↓
网页出现该作者
       ↓
作者页可看到该论文
       ↓
点击可打开本地 PDF
       ↓
网络图出现合作关系
       ↓
所有外部人物信息都可追溯到 source
```

这个闭环稳定后，再扩展月度动态和高级图分析。

---

# 15. 当前建议的关键决策

1. **Local API，不直接依赖 Zotero SQLite schema。**
2. **SQLite，不在 v1 引入图数据库。**
3. **作者使用内部永久 ID，外部 ID 只是映射。**
4. **AI 输出候选 JSON，不直接写数据库。**
5. **所有互联网信息进入 evidence + claim 层。**
6. **第一作者/通讯作者是 authorship 属性，不是作者永久属性。**
7. **Network graph 是数据库的投影视图，不是主数据。**
8. **月度更新是人工触发 batch，不做后台持续监控。**
9. **重点实现 identity merge/split 和 Review Center。**
10. **把“已知作者新论文但 Zotero 尚未收藏”作为核心特色功能。**

---

# 16. 参考资料

- Zotero Local API: https://www.zotero.org/support/dev/web_api/v3/local_api
- Zotero Web API v3: https://www.zotero.org/support/dev/web_api/v3/basics
- Zotero Syncing / version model: https://www.zotero.org/support/dev/web_api/v3/syncing
- ORCID Public API: https://info.orcid.org/what-is-orcid/services/public-api/
- OpenAlex API: https://developers.openalex.org/
- OpenAlex Authors: https://developers.openalex.org/api-reference/authors
- Semantic Scholar Academic Graph API: https://www.semanticscholar.org/product/api
- Crossref REST API: https://api.crossref.org/
- Connected Papers: https://www.connectedpapers.com/about
- ResearchRabbit: https://www.researchrabbit.ai/features

---

## 下一步建议

下一份设计应当优先固定两个东西：

1. **SQLite ER model / migration v1**；
2. **在线 AI request/response ZIP protocol + JSON Schema v1**。

这两个协议一旦稳定，前端和 AI provider 都可以独立迭代，而不会破坏已有数据。
