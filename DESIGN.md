# Paperazzi：基于 Zotero 的学术作者知识库与关系网络

**状态：Design v0.2**  
**目标：Local-first / Human-triggered / AI-assisted / Evidence-first / Zotero-process-independent**

---

## 0. 项目定义

Paperazzi 是围绕个人 Zotero 文献库构建的**作者知识库、学术关系网络与作者动态追踪系统**。

它以 Zotero 中已经收藏的论文为研究兴趣入口，识别第一作者、通讯作者及重要合作者，为作者建立可追溯来源的个人档案，并通过网页展示作者、论文、机构、研究主题、合作网络、学术谱系与近期动态。

Paperazzi **不依赖 Zotero Desktop 是否正在运行**。Zotero 的本地数据库 `zotero.sqlite` 及其 `storage/` 文件目录是唯一的本地事实源。Paperazzi 对 Zotero 数据目录只读，不通过 Zotero Local API 获取核心数据，也绝不修改 Zotero 数据库。

所有更新由用户主动触发：

1. 从 `zotero.sqlite` 创建一致性只读快照；
2. 与上一次 Paperazzi 导入状态比较；
3. 找出新增、修改、删除或重新关联的 Zotero 条目；
4. 本地程序解析论文、作者、附件和 collection/tag 信息；
5. 本地 AI/确定性程序完成作者识别和资料缺口分析；
6. 需要互联网的信息生成固定格式在线检索需求包；
7. 在线 AI 返回固定格式 ZIP；
8. 本地程序校验、消歧、冲突检测并更新 Paperazzi 数据库；
9. 网页 Review Center 负责低置信度结果、merge/split 和冲突修复。

核心原则：

> **Zotero 只读；AI 只提交候选事实；Paperazzi 数据库只由确定性程序修改。**

---

# 1. 系统边界

## 1.1 Zotero 负责什么

Zotero 是以下数据的 Source of Truth：

- 本地收藏的论文；
- Zotero item key；
- creator 顺序；
- title / journal / year / DOI / abstract 等本地书目元数据；
- collection；
- tag；
- notes；
- attachment；
- PDF 文件实际位置。

Paperazzi 不尝试取代 Zotero 的文献管理功能。

## 1.2 Paperazzi 负责什么

Paperazzi 管理 Zotero 本身不适合表达的信息：

- 作者统一身份；
- 第一作者/通讯作者等 paper-level role；
- 作者履历；
- 教育经历；
- 当前与历史任职；
- ORCID/OpenAlex/Semantic Scholar 等外部身份；
- 导师/学生/实验室/合作关系；
- 研究主题及其时间演化；
- 作者近期论文和新闻；
- 本地 Zotero 尚未收藏的新论文；
- Evidence / Claim / Confidence；
- 人工 merge/split/lock；
- 作者网络及统计分析。

---

# 2. Zotero 数据读取架构

## 2.1 唯一入口：只读 `zotero.sqlite`

Paperazzi 不把 Zotero Local API 作为核心依赖。

原因：

- Local API 依赖 Zotero Desktop 进程；
- Local API 还要求相关本地通信设置处于可用状态；
- Paperazzi 的人工 batch 更新不应受到 Zotero 是否打开的影响；
- `zotero.sqlite` 已经包含 Paperazzi 所需的绝大多数本地元数据；
- attachment 的实际文件也直接存在 Zotero data directory 中；
- 对于只读科研数据提取，数据库快照比运行时服务更可重复。

**绝对禁止：**

- 对 `zotero.sqlite` 执行 INSERT/UPDATE/DELETE；
- 修改 Zotero schema；
- 把 Paperazzi 自身字段写入 Zotero 内部表；
- 依赖修改数据库来标记“已处理”。

Paperazzi 自己的状态全部保存在 `paperazzi.sqlite3`。

## 2.2 一致性快照，而不是长期占用原库

每次用户执行更新：

```text
paperazzi zotero scan
```

执行：

```text
Zotero data directory
        ↓
open zotero.sqlite READ ONLY
        ↓
SQLite consistent snapshot / backup
        ↓
data/cache/zotero-snapshots/<run_id>.sqlite
        ↓
所有后续解析只读取 snapshot
```

这样做有四个目的：

1. Zotero 关闭时可以直接读取；
2. Zotero 打开并正在写入时，也尽可能获得事务一致的读取视图；
3. 一次 Paperazzi run 的输入被冻结，便于复现和审计；
4. 长时间 AI/解析工作不会持续占用 Zotero 原数据库。

快照是临时输入，不是长期备份系统。默认只保留最近若干次，旧快照可自动清理。

## 2.3 不使用 `immutable=1` 作为默认读取模式

如果 Zotero 正在运行，SQLite 可能存在 journal/WAL 状态。默认应使用正常的 `mode=ro` 只读连接，使 SQLite 自己处理一致性，而不是假定主文件永远是独立完整状态。

推荐抽象：

```text
ZoteroSQLiteSource
  ├── discover_data_dir()
  ├── open_readonly()
  ├── create_snapshot()
  ├── inspect_schema()
  └── close()
```

## 2.4 Zotero schema 是内部 schema：接受绑定，但必须隔离

直接读取 SQLite 的代价不是“不稳定”，而是**需要承担 Zotero schema 兼容层**。

因此所有 Zotero SQL 必须集中在：

```text
backend/paperazzi/zotero_sqlite/
├── source.py
├── snapshot.py
├── schema_probe.py
├── reader.py
├── attachments.py
├── adapters/
│   ├── current.py
│   └── ...
└── tests/
```

业务代码不得在其他位置直接查询 Zotero 表。

启动扫描时先执行 schema probe：

```text
PRAGMA user_version
sqlite_master tables/indexes
required columns
known Zotero schema fingerprints
```

结果分为：

```text
SUPPORTED
SUPPORTED_WITH_WARNING
UNKNOWN_SCHEMA
INCOMPATIBLE
```

如果 Zotero 升级导致结构变化，Paperazzi 应当**拒绝错误解析并报告 schema mismatch**，而不是静默产生错误作者数据。

## 2.5 Canonical Zotero Record

Zotero SQLite 的内部多表结构先被 reader 转换成 Paperazzi 自己的稳定中间对象：

```text
CanonicalZoteroItem
- library_id
- item_id
- item_key
- item_type
- date_added
- date_modified
- zotero_version
- fields{}
- creators[]
- collections[]
- tags[]
- attachments[]
- parent_item_key
- deleted
```

从这一层以后，Paperazzi 其他模块不需要知道 Zotero 内部表名。

这一步是隔离 Zotero schema 变化的关键。

## 2.6 PDF attachment 解析

不再通过 Local API 查询文件位置。

对 imported attachment：

```text
zotero_data_dir/
└── storage/
    └── <ATTACHMENT_ITEM_KEY>/
        └── <filename.pdf>
```

由 SQLite 中 attachment 记录和 item key 确定路径。

对 linked attachment，则读取 Zotero 保存的 linked path，并由 attachment resolver 解析。

Paperazzi 数据库保存：

```text
zotero_attachment_key
attachment_mode
relative_or_linked_path
content_type
filename
```

网页点击 **Open PDF** 时由 Paperazzi backend 直接解析本地路径并打开文件，**不需要启动 Zotero**。

## 2.7 Show in Zotero 与 Open PDF 分离

两个功能语义不同：

### Open PDF

核心功能。直接从 filesystem 打开，因此 Zotero 关闭也可用。

### Show in Zotero

辅助功能。如果 Zotero URL scheme/系统关联可用，则调用 Zotero 定位 item；此功能允许启动 Zotero，但不能成为阅读 PDF 或数据库运行的前置条件。

---

# 3. Zotero 增量更新

## 3.1 不依赖 Local API `since=version`

Paperazzi 自己维护导入状态。

每次扫描生成：

```text
zotero_scan_manifest
- run_id
- source_path
- source_db_size
- source_db_mtime
- schema_fingerprint
- scanned_at
- item_count
- attachment_count
- canonical_hash
```

对每个 canonical item 保存：

```text
zotero_item_state
- item_key
- item_type
- zotero_version
- date_modified
- canonical_hash
- present_in_last_scan
- last_seen_run_id
```

## 3.2 差异判定

比较当前扫描与上次扫描：

```text
NEW
MODIFIED
UNCHANGED
REMOVED
RESTORED
```

**最终以 canonical content hash 为准**，`version` 和 `dateModified` 仅作为快速筛选条件。

这样避免把增量逻辑绑定到 Zotero API 的同步语义。

## 3.3 删除检测

不能只看“新版本号”。

当前快照中不存在、而上一轮存在的 item key 标记为：

```text
REMOVED_FROM_ZOTERO
```

Paperazzi 不立即物理删除历史作者/关系，而是设置：

```text
removed_from_zotero_at
```

这样可以保留历史来源与 undo 能力。

## 3.4 第一版可以接受全库扫描

Paperazzi 更新是人工触发，而不是实时守护进程。因此 v1 优先考虑正确性与可重复性。

即使每次把数千或数万 Zotero item 规范化并 hash 一遍，成本通常远小于后续 PDF/AI 分析。

因此：

> **先做 deterministic full scan + diff，再考虑极限增量优化。**

---

# 4. 三条核心工作流

## 4.1 Workflow A：Zotero 更新

```text
paperazzi update-zotero
```

流程：

```text
发现 Zotero data directory
        ↓
创建只读一致性 snapshot
        ↓
schema probe
        ↓
SQLite → CanonicalZoteroItem
        ↓
与上次 scan state 比较
        ↓
NEW / MODIFIED / REMOVED
        ↓
规范化论文元数据
        ↓
解析 authorship
        ↓
作者 identity resolution
        ↓
重新计算本地作者关系
        ↓
生成 enrichment requests
```

### 第一作者

由 Zotero creator 顺序确定。

### 通讯作者

通讯作者信息不能假定 Zotero metadata 必然包含。

来源顺序：

1. 已有 Paperazzi 人工标记；
2. 本地 PDF 第一页 / Correspondence / Author Information；
3. publisher metadata；
4. 在线 AI 检索结果。

保存：

```text
is_corresponding
corresponding_confidence
corresponding_source
```

允许一篇论文有多个通讯作者。

## 4.2 Workflow B：新作者资料补全

对于新增或资料不足作者生成：

```text
requests/author_enrichment_<date>/
├── REQUEST.md
├── manifest.json
├── authors.jsonl
└── schemas/
    ├── author_profile.schema.json
    ├── evidence.schema.json
    └── media.schema.json
```

在线 AI 返回：

```text
paperazzi-enrichment-result.zip
├── manifest.json
├── authors/
├── evidence/
└── assets/
```

导入：

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
auto-accept safe fields / Review Center
```

## 4.3 Workflow C：月度作者动态

```text
paperazzi watch prepare
```

对作者按 `last_checked_at` 生成增量需求：

```text
Check since <last_checked_at>:
- new papers
- affiliation / position changes
- awards
- grants
- conference / invited talks
- lab moves
- major news
- newly discovered public profiles
```

在线 AI 返回固定格式 ZIP，本地程序导入。

---

# 5. 作者身份消歧

作者身份是整个系统最需要保守处理的部分。

## 5.1 内部永久 ID

```text
author_id = UUIDv7 / ULID
```

姓名、ORCID、OpenAlex ID 均不得作为内部主键。

## 5.2 消歧证据

可使用：

- ORCID 精确匹配；
- DOI-author-ORCID 映射；
- affiliation；
- email domain；
- coauthor overlap；
- research topics；
- paper titles / years；
- name variants；
- career timeline consistency。

## 5.3 状态

```text
IDENTIFIED
PROBABLE
AMBIGUOUS
UNRESOLVED
CONFLICT
```

低置信度候选不自动 merge。

## 5.4 人工修复

网页必须支持：

- Merge authors；
- Split identity；
- Mark not same person；
- Lock identity；
- Preferred name；
- 手工绑定 ORCID/OpenAlex；
- Undo merge。

---

# 6. Paperazzi 数据模型

Paperazzi 自己使用独立 SQLite：

```text
data/paperazzi.sqlite3
```

Zotero 数据库与 Paperazzi 数据库永远是两个数据库。

## 6.1 papers

```text
paper_id
zotero_item_key
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
zotero_canonical_hash
first_seen_run_id
last_seen_run_id
removed_from_zotero_at
created_at
updated_at
```

## 6.2 paper_attachments

```text
attachment_id
paper_id
zotero_attachment_key
attachment_mode
path_value
content_type
filename
is_primary_pdf
last_verified_at
```

## 6.3 authors

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

出生日期、性别等默认 NULL；仅接受公开来源明确陈述，不从姓名或照片推断。

## 6.4 authorships

```text
paper_id
author_id
author_order
role
is_corresponding
corresponding_confidence
affiliation_text
source_id
```

第一作者/通讯作者是论文上的 authorship 属性。

## 6.5 institutions / affiliations / education

分别记录机构实体、任职历史和教育历史，并保留 source/confidence。

## 6.6 author_relationships

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

关系示例：

```text
coauthor
advisor
postdoc_advisor
same_lab
same_institution
topic_similarity
```

其中 coauthor 必须由 authorships 确定性计算，而不是由 AI 自由生成。

## 6.7 topics / author_topics

保存作者研究主题及时间窗口，用于 Topic Evolution。

## 6.8 events

记录：

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

## 6.9 sources / claims

所有外部资料必须保留：

```text
source
retrieved_at
content_hash
claim
confidence
status
extractor
run_id
```

网页展示 accepted claim，但历史和冲突 claim 不删除。

## 6.10 zotero_scan_runs / zotero_item_state

专门保存 Zotero 快照导入历史和 canonical hash。

这是从 SQLite 自主实现可靠增量检测的基础。

---

# 7. 网页信息架构

Paperazzi 应当是**人物中心的科研情报界面**，不是 Zotero 的网页复制品。

## 7.1 Dashboard

回答：

> 我的 Zotero 文献背后有哪些人，最近发生了什么？

显示：

- Papers；
- Authors；
- Corresponding Authors；
- Institutions；
- Zotero 最近新增论文；
- 新作者；
- 已关注作者新论文；
- position/award/news；
- unresolved identities；
- claim conflicts；
- papers outside Zotero。

## 7.2 Authors

支持按以下条件过滤：

- first author；
- corresponding author；
- institution；
- country；
- topic；
- active year；
- local paper count；
- watchlist；
- profile completeness；
- identity confidence。

## 7.3 Author Profile

核心页面包括：

### Header

- portrait；
- preferred name；
- current position / institution；
- public profiles；
- identity confidence；
- last checked。

### Research Summary

AI 总结研究领域，同时记录生成时间和基础论文范围。

### Topic Evolution

按时间窗口展示研究方向变化。

### Local Papers

只列 Zotero 中已有论文：

- Open PDF；
- Show in Zotero；
- DOI；
- first/corresponding role。

**Open PDF 必须在 Zotero 未运行时仍可使用。**

### External Recent Papers

显示在线更新发现但尚未进入 Zotero 的论文：

```text
IN_ZOTERO
NOT_IN_ZOTERO
POSSIBLE_DUPLICATE
```

### Collaborators

- top collaborators；
- collaboration count；
- first/last collaboration year；
- relationship view。

### Career / Education

时间线展示。

### News / Events

展示月度更新结果。

### Evidence

每个字段可展开来源。

## 7.4 Network Explorer

作者作为节点，支持图层：

```text
Coauthor
Advisor/student
Same institution
Topic similarity
Citation-derived
```

控制：

- time range；
- minimum edge weight；
- first/corresponding only；
- institution；
- topic；
- 1-hop / 2-hop；
- local papers only / external included。

## 7.5 Relationship Path

选择两个作者：

```text
A → coauthor B → advisor of C → collaborator D
```

每一条边都能展开论文或证据。

## 7.6 Review Center

必须存在：

```text
Identity conflicts
Possible duplicates
Claim conflicts
Low-confidence corresponding authors
Missing sources
Broken profile URLs
Zotero schema warnings
Broken PDF paths
```

---

# 8. 建议增加的高价值功能

## 8.1 Library Gap Detector

比较：

```text
Tracked authors' recent works
vs.
Current Zotero canonical items
```

找出：

```text
NEW PAPER — NOT IN ZOTERO
```

## 8.2 Why do I know this author?

作者页显示其最初进入 Paperazzi 的原因：

```text
Entered Paperazzi because:
Zotero item ABC123
Role: corresponding author
Collection: Singlet Fission
```

## 8.3 Research Lineage

有可靠导师信息时形成 academic genealogy。

## 8.4 Collaboration Lifecycle

显示作者对之间合作随时间的变化。

## 8.5 Topic Drift / Research Pivot

按年度论文主题识别方向迁移，而不是只保存静态 keywords。

## 8.6 Data Completeness Score

评价的是 Paperazzi 对该作者资料的完整程度，而不是评价学者本人。

---

# 9. AI 数据交换协议

在线 AI 不直接连接 Paperazzi 数据库。

## 9.1 请求包

```text
author_enrichment_request/
├── REQUEST.md
├── manifest.json
├── authors.jsonl
└── schemas/
```

每个作者包含：

- Paperazzi author_id；
- known names；
- known affiliations；
- 本地 Zotero papers；
- known external IDs；
- requested fields；
- ambiguity notes。

## 9.2 返回包

```text
paperazzi-result.zip
├── manifest.json
├── authors/
├── works/
├── events/
├── evidence/
└── assets/
```

## 9.3 本地导入原则

```text
AI result
 ↓
Schema Validator
 ↓
Identity Resolver
 ↓
Evidence Validator
 ↓
Conflict Detector
 ↓
Deterministic Merge
 ↓
Paperazzi DB
```

AI 永远不执行 SQL。

---

# 10. 技术栈

## Backend

```text
Python
FastAPI
SQLAlchemy 2
Alembic
Pydantic
SQLite + WAL + FTS5
```

Zotero 读取层直接使用 Python `sqlite3` 或兼容 SQLite driver，只读连接 Zotero snapshot。

可选：

```text
igraph
NetworkX
scikit-learn
```

v1 不需要 Neo4j、PostgreSQL 或 Elasticsearch。

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

---

# 11. 推荐目录结构

```text
Paperazzi/
├── README.md
├── DESIGN.md
├── pyproject.toml
├── config/
│   └── paperazzi.example.toml
├── schemas/
├── backend/
│   └── paperazzi/
│       ├── api/
│       ├── db/
│       ├── models/
│       ├── zotero_sqlite/
│       │   ├── source.py
│       │   ├── snapshot.py
│       │   ├── schema_probe.py
│       │   ├── reader.py
│       │   ├── attachments.py
│       │   └── adapters/
│       ├── identity/
│       ├── ingest/
│       ├── enrichment/
│       ├── graph/
│       ├── search/
│       └── cli/
├── frontend/
├── data/
│   ├── paperazzi.sqlite3
│   ├── cache/
│   │   └── zotero-snapshots/
│   ├── requests/
│   ├── imports/
│   └── assets/
├── tests/
└── docs/
```

`data/` 默认全部 `.gitignore`。

---

# 12. 外部数据源

外部网络信息用于 enrichment，而不是替代 Zotero 本地库。

建议使用：

- ORCID：身份、employment、education、works；
- OpenAlex：author/work/institution/topic/citation graph；
- Semantic Scholar：author/paper/citation/reference；
- Crossref / publisher：DOI 和出版社 metadata；
- University / lab / personal sites：当前职位、教育、biography、portrait、news；
- 公开社交网络：仅作为补充证据。

所有外部数据先进入 Evidence/Claim 层。

---

# 13. 人物公开信息边界

1. 只收集公开可访问、与职业/学术相关的信息；
2. 出生日期、年龄、性别等只在可靠公开来源明确给出时保存；
3. 不从姓名、照片、语言、国籍推断敏感属性；
4. 照片保留来源和许可信息；
5. 不绕过登录墙、付费墙或访问控制；
6. 每条人物事实必须可追溯；
7. 支持删除单个 claim/source/enrichment 结果；
8. identity merge 必须可撤销。

---

# 14. MVP 开发阶段

## Phase 0 — Zotero SQLite Foundation

- repository skeleton；
- Paperazzi SQLite schema；
- Zotero data directory 配置/发现；
- read-only source；
- snapshot；
- schema probe；
- CanonicalZoteroItem；
- full scan + hash diff；
- attachment path resolver；
- tests with fixture Zotero databases。

## Phase 1 — Core Website

- Dashboard；
- Authors；
- Author Profile；
- Papers；
- Open PDF without Zotero process；
- simple coauthor graph；
- search。

## Phase 2 — Identity + AI Package

- author resolution；
- external IDs；
- JSON Schema；
- enrichment request export；
- ZIP import；
- sources/claims；
- Review Center。

## Phase 3 — Research Intelligence

- monthly watch；
- external recent papers；
- Library Gap Detector；
- events/news；
- watchlist。

## Phase 4 — Advanced Graph

- multi-layer network；
- topic evolution；
- community detection；
- relationship path；
- academic genealogy；
- institution/topic views。

---

# 15. 第一版验收标准

```text
Zotero 可以处于关闭状态
       ↓
Paperazzi 读取 zotero.sqlite
       ↓
创建一致性 snapshot
       ↓
识别 Zotero 新增论文
       ↓
正确读取 creator 顺序和 attachment
       ↓
识别第一作者
       ↓
必要时从 PDF/在线结果确定通讯作者
       ↓
生成 enrichment request
       ↓
在线 AI 返回标准 ZIP
       ↓
本地校验并更新作者档案
       ↓
网页出现作者、论文和关系
       ↓
点击论文可直接打开 storage 中 PDF
       ↓
全部外部信息可追溯到 evidence
```

同时必须验证另一种情况：

```text
Zotero 正在运行并修改数据库
       ↓
Paperazzi 仍然只能 READ ONLY
       ↓
创建事务一致 snapshot
       ↓
不阻断或污染 Zotero
       ↓
本次 run 基于被冻结的 snapshot 完成
```

---

# 16. 当前关键决策

1. **只读 `zotero.sqlite` 是 Zotero 数据的唯一主入口。**
2. **Paperazzi 不依赖 Zotero Desktop 进程，也不依赖 Local API。**
3. **每次更新先建立 SQLite 一致性 snapshot，再做后续解析。**
4. **所有 Zotero SQL 集中在独立 adapter 层，schema 变化必须显式检测。**
5. **增量更新由 Paperazzi 自己的 canonical hash + scan state 完成。**
6. **本地 PDF 路径直接从 SQLite + Zotero data directory 解析。**
7. **Paperazzi 使用独立 SQLite，不向 Zotero 数据库写入任何内容。**
8. **作者使用内部永久 ID；ORCID/OpenAlex 等只是身份映射。**
9. **AI 输出候选 JSON，不直接写数据库。**
10. **所有互联网信息进入 evidence + claim 层。**
11. **第一作者/通讯作者是 authorship 属性。**
12. **Network graph 是数据库投影，不是主数据。**
13. **月度更新人工触发，不做后台持续监控。**
14. **identity merge/split、Review Center 和 schema compatibility 属于可靠性核心。**
15. **“已知作者新论文但 Zotero 尚未收藏”作为核心特色功能。**

---

# 17. 参考资料

- Zotero — Direct Access to the Zotero SQLite Database: https://www.zotero.org/support/dev/client_coding/direct_sqlite_database_access
- Zotero — Data Directory: https://www.zotero.org/support/zotero_data
- Zotero data schema repository: https://github.com/zotero/zotero-schema
- Zotero source repository: https://github.com/zotero/zotero
- ORCID Public API: https://info.orcid.org/what-is-orcid/services/public-api/
- OpenAlex API: https://developers.openalex.org/
- Semantic Scholar Academic Graph API: https://www.semanticscholar.org/product/api
- Crossref REST API: https://api.crossref.org/

---

## 下一步

下一份设计优先固定：

1. **`ZoteroSQLiteReader` 的实际 SQL / CanonicalZoteroItem schema / snapshot 策略；**
2. **Paperazzi SQLite ER model + migration v1；**
3. **在线 AI request/response ZIP protocol + JSON Schema v1。**

其中第 1 项现在应当排在最前面，因为它定义 Paperazzi 与 Zotero 之间唯一、长期稳定的本地数据边界。