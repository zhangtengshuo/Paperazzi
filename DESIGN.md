# Paperazzi：基于 Zotero 的学术作者知识库、文献证据层与关系网络

**状态：Design v0.3**  
**目标：Local-first / Human-triggered / AI-assisted / Evidence-first / Zotero-process-independent**

---

## 0. 项目定义

Paperazzi 是围绕个人 Zotero 文献库构建的**作者知识库、文献证据系统、引用关系网络与作者动态追踪系统**。

它以 Zotero 中已经收藏的论文为研究兴趣入口：

- 从 `zotero.sqlite` 只读获取论文、creator、collection/tag、attachment 等结构化元数据；
- 对本地实际存在的 PDF，可选地使用 Python/PyMuPDF 读取其文本层，提取作者/单位/通讯信息线索与参考文献；
- 将 PDF references 解析为可追溯的 `paper_reference`，进一步匹配为 paper-to-paper `CITES` 关系；
- 统一作者身份，建立作者档案、合作网络、学术谱系、引用关系、研究主题和近期动态；
- 对需要互联网的信息生成固定格式在线检索请求，再由本地确定性程序校验并导入。

Paperazzi **不依赖 Zotero Desktop 是否正在运行**。核心本地入口始终是 Zotero data directory：

```text
zotero.sqlite            structured metadata, READ ONLY
storage/<key>/*.pdf      optional local document evidence, READ ONLY
```

Paperazzi 绝不修改 Zotero 数据库或 PDF 文件。

核心原则：

> **Zotero 元数据只读；PDF 只读且可缺失；AI 只提交候选事实；Paperazzi 数据库只由确定性程序修改；所有推导信息必须保留 provenance。**

---

# 1. 系统边界与数据源层级

## 1.1 Zotero metadata channel

Zotero 是以下本地信息的 Source of Truth：

- library/item identity；
- item type；
- creator 顺序和 creator type；
- title / journal / year / DOI / abstract 等 Zotero 已保存字段；
- collection；
- tag；
- attachment metadata；
- attachment 所记录的路径；
- deleted state；
- Zotero bookkeeping 信息。

Paperazzi 对 Zotero 数据采取**宽容抽取**：

```text
无 creator      合法
无 DOI          合法
字段不完整      合法
PDF 不在本机    合法
```

这些只意味着信息较少，不构成导入错误。

真正的 Zotero reader 错误只包括：schema 无法安全理解、错误 join、重复稳定 identity、把 deleted child 错误恢复等。

详见 `docs/architecture/ZOTERO_DATA_BOUNDARY.md`。

## 1.2 Local PDF evidence channel

如果 Zotero attachment 对应的本地 PDF 实际存在，Paperazzi 可以独立读取 PDF：

```text
local PDF
   ↓ READ ONLY
PyMuPDF
   ↓
PDF metadata / page text / blocks / bbox
   ↓
front-matter evidence
reference evidence
```

PDF 不是 Zotero metadata 的替代来源，而是独立的**本地证据源**。

可提取：

- PDF embedded title/author metadata；
- 第一页/前两页 displayed author information；
- affiliation/address blocks；
- e-mail / corresponding-author evidence；
- reference/bibliography section；
- reference entries；
- DOI/year 等强 identifier；
- 后续可扩展的其他 document-local evidence。

PDF 缺失、扫描件、无文本层、加密或解析失败都只减少 evidence，不阻塞 Zotero scan。

详见 `docs/architecture/LOCAL_PDF_EVIDENCE.md`。

## 1.3 Online evidence channel

互联网 enrichment 用于补充/验证：

- ORCID/OpenAlex/Semantic Scholar/Crossref identity；
- 当前与历史任职；
- 教育经历；
- corresponding author；
- portrait/public profiles；
- 新论文；
- awards/grants/news/events；
- 引用和参考关系的外部补全。

网络结果必须进入 Evidence/Claim 层，不直接覆盖 Zotero 或 local-PDF evidence。

## 1.4 Provenance classes

至少区分：

```text
SOURCE_ZOTERO_SQLITE
SOURCE_LOCAL_PDF_NATIVE_TEXT
SOURCE_ZOTERO_FULLTEXT_CACHE       optional fallback
SOURCE_LOCAL_PDF_OCR               future
SOURCE_ONLINE
SOURCE_MANUAL
```

---

# 2. Zotero SQLite 读取架构

## 2.1 唯一结构化入口：只读 `zotero.sqlite`

Paperazzi 不把 Zotero Local API 作为核心依赖。

禁止：

- INSERT / UPDATE / DELETE Zotero DB；
- 修改 schema；
- 把 Paperazzi 自身状态写回 Zotero；
- 依赖 Zotero Desktop 进程；
- 依赖 Local API 才能完成更新。

Paperazzi 自己的状态全部保存在 `paperazzi.sqlite3`。

## 2.2 每次扫描先建立一致性 snapshot

```text
real zotero.sqlite
        ↓ mode=ro
SQLite Backup API
        ↓
data/cache/zotero-snapshots/<run_id>.sqlite
        ↓
all Zotero SQL reads snapshot
```

这样一次 run 的结构化输入被冻结，并避免长期占用真实库。

不默认使用 `immutable=1` 读取正在使用的真实库；让 SQLite 正常处理 journal/WAL 一致性。

## 2.3 schema adapter

所有 Zotero 内部 SQL 只能存在于：

```text
src/paperazzi/zotero_sqlite/
├── source.py / probe.py
├── reader.py
└── adapters/
```

当前真实库验证目标：

```text
userdata = 125
globalSchema = 42
```

如果 Zotero 升级到未知 schema，必须显式拒绝静默误读，并建立新 adapter。

## 2.4 Canonical Zotero Record

```text
CanonicalZoteroItem
- library_id
- item_id                    diagnostic join key
- item_key
- item_type
- zotero_version
- date_added/date_modified
- fields{}
- creators[]
- collections[]
- tags[]
- attachments[]
- deleted
```

稳定 Zotero-side identity：

```text
(libraryID, itemKey)
```

而不是单独 itemKey，更不是内部 itemID。

Canonical semantic hash 不应因纯同步状态、内部 itemID 等 bookkeeping 变化而变化。

## 2.5 attachment path / Open PDF

Imported PDF 通常解析为：

```text
<zotero_data_dir>/storage/<ATTACHMENT_KEY>/<filename.pdf>
```

业务层只需要知道：

```text
PDF_AVAILABLE
PDF_RECORD_ONLY
NO_PDF
UNRESOLVED_PATH
```

如果本地文件存在，网页可以直接 Open PDF；Zotero 可以完全关闭。

---

# 3. Local PDF Evidence 子系统

## 3.1 模块边界

```text
src/paperazzi/local_evidence/
└── pdf.py
```

它不属于 `zotero_sqlite`，也不能修改 `CanonicalZoteroItem` 来伪装成 Zotero metadata。

## 3.2 Deterministic Layer A：文档读取

主 backend：PyMuPDF。

提取：

```text
page_count
PDF metadata
page text
text blocks + bbox
text-layer status
front-matter text
```

PyMuPDF 官方支持 `Page.get_text()` 的 text/blocks/words 等多种输出和 `Document.metadata`，因此可以同时保留文本与布局信息。

## 3.3 Deterministic Layer B：证据候选

第一版先提取强信号：

```text
affiliation-candidate block
correspondence/e-mail candidate block
reference-section heading
raw reference section
high-confidence numbered reference entries
DOI / year identifiers
```

原则：

> 宁可保留略有噪声的原始 evidence span，也不要在确定性层凭空建立 author-affiliation 关系。

## 3.4 Semantic Layer C：本地 AI / resolver

后续 local AI 消费带页码/bbox/原文的 evidence：

```text
PDF author line ↔ Zotero creators
author ↔ affiliation
correspondence evidence ↔ author
reference entry ↔ canonical paper
```

AI 产生 candidate/claim，不直接执行数据库写入。

## 3.5 Fallback

建议后续优先级：

```text
1 direct PDF native text / PyMuPDF
2 .zotero-ft-cache / .zotero-ft-unprocessed
3 OCR / MinerU for old scans
4 no local evidence
```

OCR 不是 v1 的前置条件。

---

# 4. Reference 与 Citation Graph

这是 v0.3 新增的核心能力。

## 4.1 Raw reference 是一等实体

PDF 中识别到：

```text
[17] Smith ... J. Chem. Phys. ... DOI ...
```

首先保存为 `paper_reference`，不能直接假设它对应哪篇 Paperazzi paper。

即使无法解析 title/DOI，也保留原始 entry。

## 4.2 分段策略

v1 高置信支持：

```text
[1] ...
[2] ...

1. ...
2. ...
```

要求 numbering 序列基本单调递增。

Author-year 等难布局如果不能安全分条：

```text
raw-author-year-or-unsegmented
```

保留完整 References 区段，后续交给更强规则或 AI。

## 4.3 Reference matching

```text
paper_reference
      ↓
paper_reference_match
      ↓
cited paper
```

优先级：

```text
DOI_EXACT
TITLE_EXACT_NORMALIZED
BIBLIOGRAPHIC_COMPOSITE
AI_RESOLVED
UNRESOLVED
```

DOI exact match 可以作为最高置信自动匹配。

只有 ACCEPTED match 才产生：

```text
Paper A --CITES--> Paper B
```

## 4.4 Graph 价值

Citation graph 可以支持：

- 用户 Zotero 内部的引用网络；
- foundational papers；
- method/topic lineage；
- 两个作者群之间的知识桥梁；
- author-to-author citation projection；
- citation path；
- 与外部 OpenAlex/Semantic Scholar/OpenCitations 图比较；
- 后期“为什么这些论文会一起出现在我的研究路径里”的解释。

---

# 5. 增量更新

Paperazzi 自己维护 scan state，不依赖 API `since=`。

每次扫描保存：

```text
zotero_scan_run
source path/size/mtime
schema identity
scanned_at
item count
canonical corpus hash
```

每个 Zotero item 保存：

```text
library_id
item_key
zotero_version
date_modified
canonical_hash
present_in_last_scan
last_seen_run_id
```

比较得到：

```text
NEW
MODIFIED
UNCHANGED
REMOVED
RESTORED
```

## 5.1 PDF evidence 独立增量

PDF 不应该每次都重新解析。

Document change key：

```text
preferred: Zotero storageHash
fallback:  file size + mtime
```

仅在以下情况重提取：

```text
PDF 首次变成本地可用
PDF 文件变化
extractor version 变化
用户显式 rebuild
```

Zotero 书目字段变化本身不要求重新解析未变化的 PDF。

---

# 6. 核心工作流

## 6.1 Workflow A：Zotero 更新

```text
paperazzi update-zotero
```

```text
readonly snapshot
    ↓
schema adapter
    ↓
CanonicalZoteroItem
    ↓
scan diff
    ↓
persist Zotero-derived paper/creator/attachment projection
```

缺 DOI、作者或 PDF 都不会阻塞。

## 6.2 Workflow B：Local PDF Evidence

对 NEW/changed/local-new PDF：

```text
local PDF
  ↓
PyMuPDF deterministic extraction
  ↓
evidence spans + references
  ↓
cache/persist extraction
  ↓
local AI/resolver candidates
  ↓
claims / reference matches
```

它与 Workflow A 解耦；某个 PDF 失败不回滚 Zotero import。

### 第一作者

Zotero creator order 是本地结构化第一来源。

PDF displayed author line 可作为后续核对/补充证据，但不静默覆盖 Zotero。

### 通讯作者

来源可包括：

1. manual assertion；
2. local PDF correspondence/e-mail evidence；
3. publisher/structured online metadata；
4. online AI research。

PDF deterministic extractor只先产出 evidence span；resolver 再映射到具体 author。

## 6.3 Workflow C：新作者资料补全

Local knowledge 仍不足时生成：

```text
requests/author_enrichment_<date>/
├── REQUEST.md
├── manifest.json
├── authors.jsonl
└── schemas/
```

在线 AI 返回标准 ZIP。本地做 schema validation、identity check、evidence validation、conflict detection、deterministic merge。

## 6.4 Workflow D：月度作者动态

人工触发：

```text
paperazzi watch prepare
```

检查：new papers、position/affiliation、award、grant、conference、lab move、news、new public profile。

---

# 7. 作者身份消歧

内部永久 ID：

```text
author_id = UUIDv7 / ULID
```

ORCID/OpenAlex 等只是外部映射。

证据可使用：

- ORCID exact；
- DOI-author-ORCID；
- PDF affiliation/e-mail evidence；
- online affiliation；
- coauthor overlap；
- research topics；
- paper titles/year；
- aliases；
- career timeline consistency。

状态：

```text
IDENTIFIED
PROBABLE
AMBIGUOUS
UNRESOLVED
CONFLICT
```

低置信不自动 merge。

网页必须支持 Merge / Split / Not-same / Lock / Preferred name / external-ID binding / Undo。

---

# 8. Paperazzi 数据模型

Paperazzi 使用独立：

```text
data/paperazzi.sqlite3
```

## 8.1 Zotero projection / papers

`papers`：Paperazzi paper entity，可对应 Zotero paper，也可来自未来 external works。

`zotero_items`：保存 `(library_id,item_key)`、canonical hash、scan lifecycle 等 Zotero source projection。

`paper_attachments`：保存 attachment key、mode、path、content type、PDF availability。

## 8.2 authors / authorships

```text
authors
author_aliases
author_external_ids
authorships
```

`authorships` 保存 paper-level role：author order / first / corresponding 等。

## 8.3 paper_documents

本地 document/PDF 状态：

```text
document_id
paper_id
zotero_attachment_key
local_path
availability_status
content_type
file_size
file_mtime
zotero_storage_hash
extraction_status
extraction_backend
extraction_backend_version
extracted_at
```

## 8.4 document_evidence_spans

```text
evidence_span_id
document_id
kind
page_index
bbox_json
raw_text
extractor_version
created_at
```

kind 包括：front-matter、affiliation-candidate、correspondence-candidate 等。

## 8.5 paper_references

```text
reference_id
citing_paper_id
document_id
ordinal
raw_text
parsed_doi
parsed_year
parse_method
parse_confidence
reference_section_start_page
reference_section_end_page
```

解析不完整时 raw_text 仍然保留。

## 8.6 paper_reference_matches

```text
reference_match_id
reference_id
cited_paper_id
match_type
match_score
status = ACCEPTED/CANDIDATE/REJECTED
resolver
created_at
```

Accepted match 投影为 `CITES` 图边。

## 8.7 institutions / affiliations / education

机构实体、任职历史、教育历史全部保留 evidence/source/confidence。

## 8.8 author_relationships

```text
coauthor
advisor
postdoc_advisor
same_lab
same_institution
topic_similarity
citation-derived
```

coauthor 必须从 authorships 确定性投影。

## 8.9 events / topics

保存作者动态和 research topic evolution。

## 8.10 sources / claims

所有非 Zotero 直接事实应支持：

```text
source_type
source locator
retrieved_at
claim
confidence
status
extractor/resolver
run_id
```

Claim 可以指向 local PDF evidence span，也可以指向 online evidence。

## 8.11 scan/extraction history

```text
zotero_scan_runs
zotero_item_state
pdf_extraction_runs
```

用于复现、diff、cache invalidation 和 extractor migration。

---

# 9. 网页信息架构

Paperazzi 是**人物中心 + 文献关系中心**的科研情报界面。

## 9.1 Dashboard

显示 Papers / Authors / Corresponding Authors / Institutions / new Zotero items / new author events / unresolved identity/claim conflicts / papers outside Zotero。

## 9.2 Author Profile

Header、research summary、topic evolution、career/education、events、evidence。

### Papers 表格

建议字段：

```text
Year | Title | Journal | Role | DOI | Zotero | PDF | Citations-in-library
```

`Zotero` 和 `PDF` 分开：某论文可能在 Paperazzi 中但不在 Zotero，也可能在 Zotero 中但本机没有 PDF。

PDF available 时可直接在网页打开。

## 9.3 Paper Profile

新增一等页面：

- Zotero metadata；
- local PDF availability/extraction status；
- authors；
- PDF-derived affiliation/correspondence evidence；
- References；
- matched cited papers；
- papers in library citing this paper；
- unresolved references；
- evidence provenance。

## 9.4 Network Explorer

节点可切换：Author / Paper / Institution / Topic。

Author graph layers：coauthor、advisor、same institution、topic similarity、citation-derived。

Paper graph layers：CITES、shared authors、topic similarity。

所有边应可展开到原始论文/reference/evidence。

## 9.5 Relationship / Citation Path

```text
Author A → coauthor B → cited Paper X → authored by C
```

或：

```text
Paper A → cites B → cites C
```

## 9.6 Review Center

处理：identity ambiguity、claim conflicts、reference-match candidates、low-confidence corresponding author、schema warnings、parse diagnostics。

PDF missing 不需要作为“错误修复任务”；它只是 availability state。

---

# 10. 高价值特色功能

## 10.1 Library Gap Detector

Tracked author recent works vs Zotero，显示 `NEW PAPER — NOT IN ZOTERO`。

## 10.2 Why do I know this author?

给出最初进入 Paperazzi 的 Zotero paper/role/collection 路径。

## 10.3 Citation Lineage / Method Genealogy

利用 PDF reference graph 展示某个方法、理论或研究方向在用户文献库中的传播路径。

## 10.4 Bridge Papers / Bridge Authors

结合 coauthor + citation graph 找到连接两个研究社区的关键论文/作者。

## 10.5 Research Lineage / Topic Drift

导师谱系与研究方向时间演化。

---

# 11. AI 数据交换协议

AI 永远不直接连接/修改 Paperazzi DB。

请求包：

```text
manifest.json
REQUEST.md
authors.jsonl
papers.jsonl
evidence summaries
schemas/
```

返回：

```text
manifest.json
authors/
works/
events/
evidence/
assets/
```

本地流程：

```text
AI result
 ↓
Schema Validator
 ↓
Identity / Reference Resolver
 ↓
Evidence Validator
 ↓
Conflict Detector
 ↓
Deterministic Merge
 ↓
Paperazzi DB
```

对于 local PDF，可先让 AI 只消费短 evidence spans/reference entries，而不是每次传整篇 PDF 全文。

---

# 12. 技术栈

## Backend

```text
Python
sqlite3                   Zotero read-only layer
PyMuPDF                   optional local PDF evidence
FastAPI
SQLAlchemy 2
Alembic
Pydantic
SQLite + WAL + FTS5       Paperazzi-owned DB
```

可选 graph/analysis：NetworkX / igraph / scikit-learn。

v1 不需要 Neo4j、PostgreSQL、Elasticsearch。

## Frontend

```text
React
TypeScript
Vite
TanStack Query/Table
Cytoscape.js
ECharts
```

---

# 13. 推荐目录结构

当前采用 `src/` layout：

```text
Paperazzi/
├── DESIGN.md
├── pyproject.toml
├── docs/
│   ├── architecture/
│   ├── phase1/
│   ├── phase2/
│   └── phase2_5/
├── src/paperazzi/
│   ├── zotero_sqlite/       # only code that knows Zotero DB schema
│   ├── ingest/              # canonical models / diff
│   ├── local_evidence/      # PDF/cache/OCR evidence; no Zotero SQL
│   ├── identity/
│   ├── database/
│   ├── enrichment/
│   ├── graph/
│   └── api/
├── scripts/
├── tests/
├── frontend/
├── requests/
├── imports/
└── data/                    # gitignored
```

关键依赖规则：

```text
zotero_sqlite  -> ingest canonical records
local_evidence -> evidence records
identity/graph -> consume both
```

`local_evidence` 不能查询 Zotero 内部表；它只接收明确的 local document path/context。

---

# 14. 人物与文献证据边界

1. 只收集公开可访问、与职业/学术相关的人物信息；
2. 年龄/性别仅在可靠公开来源明确陈述时保存；
3. 不从姓名、照片、国籍推断敏感属性；
4. 图片保留来源与许可信息；
5. 不绕过登录墙/访问控制；
6. 每条外部人物事实可追溯；
7. local PDF evidence 只来自用户本地已有文件，只读处理；
8. reference raw text 只保存完成匹配所需的证据，不把全文复制进 Git；
9. identity merge 必须可撤销。

---

# 15. 开发阶段（当前路线）

## Phase 1 — Zotero SQLite reconnaissance — COMPLETE

真实库只读/snapshot/schema/attachment/creator 验证。

## Phase 2 — Production ZoteroSQLiteReader — COMPLETE / freeze after correctness fixes

CanonicalZoteroItem、userdata125 adapter、全库 reader。

缺作者/DOI/PDF 不是 blocker。

## Phase 2.5 — Local PDF Evidence validation — CURRENT

实现/测试：

- PyMuPDF read-only extraction；
- text status；
- front-matter blocks；
- affiliation/correspondence candidates；
- reference heading；
- conservative entry segmentation；
- DOI extraction；
- representative real-library validation。

先看真实 200-PDF stratified report，再决定 parser enhancement。

## Phase 3 — Persistence + diff + evidence/reference schema

- `paperazzi.sqlite3`；
- Alembic v1；
- scan history；
- NEW/MODIFIED/UNCHANGED/REMOVED/RESTORED；
- paper_documents；
- document_evidence_spans；
- paper_references；
- paper_reference_matches；
- DOI-exact in-library citation resolver。

## Phase 4 — Author identity + Local/Online enrichment

- author resolution；
- PDF author-affiliation/correspondence semantic resolver；
- external IDs；
- request/ZIP protocol；
- claims/evidence；
- Review Center。

## Phase 5 — Core Website

Dashboard、Authors、Author Profile、Paper Profile、Open PDF、reference/citation views、simple coauthor/citation graph、search。

## Phase 6 — Research Intelligence

monthly watch、external recent papers、Library Gap Detector、events/news、advanced graph、topic evolution、relationship/citation paths、academic genealogy。

---

# 16. 第一版验收标准

```text
Zotero 可关闭也可运行
       ↓
READ ONLY snapshot
       ↓
Canonical Zotero corpus
       ↓
增量更新 Paperazzi DB
       ↓
本地 PDF 有则可直接网页打开
       ↓
PDF 有文本则异步/可选提取 local evidence
       ↓
References 保留 raw evidence
       ↓
能高置信匹配的 reference 建立 CITES
       ↓
local/online evidence 帮助作者 identity / affiliation / corresponding author
       ↓
网页展示 authors + papers + citation/coauthor relations
       ↓
所有非原始事实可追溯到 evidence
```

任何单篇 PDF 缺失/解析失败都不能阻塞整个流程。

---

# 17. 当前关键决策

1. **只读 `zotero.sqlite` 是结构化 Zotero 数据的唯一主入口。**
2. **Paperazzi 不依赖 Zotero Desktop 或 Local API。**
3. **每次结构化更新先建立 SQLite 一致性 snapshot。**
4. **所有 Zotero SQL 集中在 adapter 层。**
5. **Zotero 数据宽容抽取，不负责修复 metadata。**
6. **本地 PDF 是独立、可选、只读的一等 evidence source。**
7. **PDF 缺失/scan-only/解析失败只减少 evidence，不影响 ingestion。**
8. **PyMuPDF 是 native PDF text/layout 的首选 backend。**
9. **raw reference 是一等数据，不能只存最终 citation edge。**
10. **DOI exact 是 reference-to-paper 自动匹配的最高置信首选路径。**
11. **Author-year 等不确定 bibliography 宁可保留 raw section，也不强制错误分条。**
12. **PDF evidence 与 Zotero metadata provenance 永远分开。**
13. **作者使用内部永久 ID；外部 ID 只是映射。**
14. **AI 输出候选事实/匹配，不直接写数据库。**
15. **Network graph 是 evidence-backed database projection。**
16. **月度更新人工触发。**
17. **Library Gap Detector 与 in-library citation graph 是核心特色。**

---

# 18. 参考资料

- Zotero — Direct SQLite Database Access: https://www.zotero.org/support/dev/client_coding/direct_sqlite_database_access
- Zotero — Data Directory: https://www.zotero.org/support/zotero_data
- Zotero source/schema: https://github.com/zotero/zotero
- PyMuPDF documentation: https://pymupdf.readthedocs.io/
- ORCID Public API: https://info.orcid.org/what-is-orcid/services/public-api/
- OpenAlex API: https://developers.openalex.org/
- Semantic Scholar Academic Graph API: https://www.semanticscholar.org/product/api
- Crossref REST API: https://api.crossref.org/

---

## 下一步

当前优先级固定为：

1. **执行 Phase 2.5 的真实 PDF evidence validation；**
2. **根据真实 references/front-matter 布局修正 parser；**
3. **冻结 Phase 3 `paperazzi.sqlite3` ER schema，其中必须包含 document evidence 与 paper references；**
4. **首先实现 DOI-exact 的 in-library reference matching；**
5. **之后再做 author-affiliation/corresponding-author semantic resolution 和在线 enrichment。**
