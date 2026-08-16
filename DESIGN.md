# Paperazzi：基于 Zotero 的学术作者知识库、文献证据层与关系网络

**状态：Design v0.4**  
**日期：2026-08-17**  
**目标：Local-first / Human-triggered / AI-assisted / Evidence-first / Zotero-process-independent**

---

# 0. 项目定义

Paperazzi 是围绕个人 Zotero 文献库构建的**作者知识库、文献证据系统、引用关系网络与作者动态追踪系统**。

它不试图替代 Zotero，也不把 Zotero 数据库当成必须被清洗完整的数据集。Paperazzi 的目标是：

> 以用户已经收藏的文献为兴趣边界，尽可能提取其中关于论文、作者、机构、引用关系和研究脉络的信息，再通过本地 AI 与在线 enrichment 构建可追溯的 researcher-centric scholarly knowledge graph。

核心本地输入有两个独立通道：

```text
zotero.sqlite            structured metadata, READ ONLY
storage/<key>/*.pdf      optional local document evidence, READ ONLY
```

外部网络信息构成第三个 evidence channel。

核心原则：

> **Zotero 元数据只读；PDF 只读且可缺失；本地 AI 可执行有边界的自适应解析；AI 不直接写数据库；Paperazzi 只接受带 provenance 的结构化结果。**

---

# 1. 总体架构

```text
                       ┌──────────────────────┐
                       │ zotero.sqlite        │
                       │ structured metadata  │
                       └──────────┬───────────┘
                                  │
                                  ▼
                         CanonicalZoteroItem
                                  │
                                  ▼
                            Paper layer
                                  ▲
                                  │
                       ┌──────────┴───────────┐
                       │ local PDF evidence   │
                       │ PyMuPDF + local AI   │
                       └──────────┬───────────┘
                                  │
                                  ▼
                     Evidence / References / Claims
                                  │
                 ┌────────────────┴───────────────┐
                 ▼                                ▼
          Identity / Author DB              Citation / Graph
                 ▲                                ▲
                 └────────── online evidence ─────┘
```

三个来源必须保持 provenance 区分：

```text
SOURCE_ZOTERO_SQLITE
SOURCE_LOCAL_PDF_NATIVE_TEXT
SOURCE_ZOTERO_FULLTEXT_CACHE
SOURCE_LOCAL_PDF_OCR          future/optional
SOURCE_ONLINE
SOURCE_MANUAL
```

任何一条来源都不能无痕覆盖另一条来源。

---

# 2. Zotero metadata channel

## 2.1 唯一结构化入口

核心入口是只读 `zotero.sqlite`，不依赖 Zotero Local API，也不依赖 Zotero Desktop 是否运行。

禁止：

- INSERT / UPDATE / DELETE Zotero 数据库；
- 修改 Zotero schema；
- 把 Paperazzi 状态写回 Zotero；
- 依赖 Local API 才能运行；
- 修改 Zotero attachment/PDF 文件。

## 2.2 一致性 snapshot

每次人工触发更新：

```text
real zotero.sqlite
        ↓ mode=ro
SQLite Backup API
        ↓
Paperazzi-owned snapshot
        ↓
所有本轮 Zotero SQL 均读取 snapshot
```

Phase 1 已在真实 Windows/WSL2 Zotero 库中验证：Zotero 开启和关闭状态均可以安全 snapshot。

## 2.3 Schema adapter

所有 Zotero 内部 SQL 必须集中在：

```text
src/paperazzi/zotero_sqlite/
```

当前真实库 adapter：

```text
userdata = 125
globalSchema = 42
```

未知 schema 必须显式拒绝静默误读。

## 2.4 宽容抽取

Paperazzi 只要求 reader 忠实读取，不要求 Zotero 数据完整：

```text
无 creator         合法
无 DOI             合法
无 abstract        合法
无 PDF             合法
PDF metadata 有但文件不在本机   合法
```

这些状态只表示 information yield 较低，不构成 ingestion failure。

真正的 reader failure 包括：

- schema 无法安全理解；
- 错误 join；
- 重复稳定 identity；
- resurrect 已删除 child；
- 无法保持只读/一致性。

## 2.5 Canonical identity

Zotero-side identity：

```text
(libraryID, itemKey)
```

`itemID` 只是内部 join/diagnostic key。

Canonical semantic hash 不应受纯同步 bookkeeping 状态影响。

---

# 3. Local PDF Evidence channel

本地 PDF 是**正式但可选的第二本地证据源**。

PDF 缺失不阻碍任何 Zotero import；有 PDF 时则尽量利用其中高价值信息。

可提取：

- PDF embedded metadata；
- displayed author line；
- affiliation/address block；
- author-affiliation marker evidence；
- corresponding-author / e-mail evidence；
- References / Bibliography；
- individual reference entries；
- DOI / year / journal / volume / page 等引用识别信息；
- 后续可扩展的 document-local evidence。

详细架构：

```text
docs/architecture/LOCAL_PDF_EVIDENCE.md
docs/architecture/AI_SUPERVISED_PDF_EXTRACTION.md
```

---

# 4. PDF 解析：固定代码 + 本地 AI 自适应审查

这是 Design v0.4 的关键变化。

真实 200 篇分层测试显示：

```text
200 PDFs sampled
198 NATIVE_TEXT_GOOD
0 parse errors
165 with affiliation candidates
81 with correspondence candidates
61 with e-mail candidates
45 exact reference headings found
30 usable deterministic reference segmentations
785 segmented reference entries
10 DOI strings in those entries
```

结论：

> **PyMuPDF 读取能力不是主要瓶颈；出版格式和布局异质性才是主要瓶颈。**

因此不能只依赖一套固定 regex，也不应把全部解析交给不可审计的自由 AI。

采用：

```text
Deterministic Attempt 1
        ↓
mandatory Local AI review
        ↓
PASS / ACCEPT_PARTIAL / RETRY
                         ↓
                   Attempt 2
                   targeted reparse
                         ↓
                   Local AI review
                         ↓
                   optional Attempt 3
                         ↓
                   final bounded result
```

## 4.1 Attempt 1：固定代码

固定 production parser 负责：

- PyMuPDF open/read；
- text/blocks/bbox；
- PDF metadata；
- text layer classification；
- front-matter candidate；
- exact reference heading；
- conservative numbered segmentation；
- DOI/e-mail/year regex；
- 已知 publisher noise suppression。

系统性错误一旦被真实库发现，应修入固定代码并添加 regression test。

例如真实测试曾发现年份：

```text
1943
1962
1954
```

被误判为 reference ordinal。该类问题属于 parser bug，不能长期交给 AI 兜底。

## 4.2 每篇 PDF 的 Attempt 1 都必须经过本地 AI review

即使固定 parser 返回：

```text
confidence = HIGH
```

也不能直接视为最终正确。

本地 AI 必须检查：

- affiliation 是否真的是机构地址而非正文；
- correspondence 是否真的是作者信息而非 publisher recommendation；
- reference section 是否合理；
- ordinal 是否可能其实是年份；
- reference entry 是否 citation-like；
- parser 是否漏掉了无 `References` 标题的 bibliography。

好的结果立即 `PASS`，不进入下一轮。

## 4.3 Attempt 2：有明确问题才 retry

AI 必须先说明 failure hypothesis，再选择有限策略：

```text
TAIL_REFERENCE_RECOVERY
BLOCK_COLUMN_RECONSTRUCTION
ALTERNATIVE_REFERENCE_SEGMENTATION
FRONT_MATTER_RECOVERY
ZOTERO_FT_CACHE_FALLBACK
OCR_IF_CONFIGURED
```

例如：

```text
native text = good
references = null
last pages clearly contain citation-like blocks
```

则 Attempt 2 可以专门读取末尾若干页，而不是重新处理整篇全文。

## 4.4 Attempt 3：最后一次局部恢复

只有 Attempt 2 仍存在具体可恢复问题时使用。

本地 AI 可在 Paperazzi runtime/temp 下写 document-specific Python，例如：

- blocks/words + bbox 重排双栏；
- 扩大 tail window；
- 按实际 hanging indent 分条；
- 根据 creator anchor 定位 front matter；
- 处理 split heading/superscript numbering。

禁止修改生产 parser、Zotero 或 PDF。

最多三轮，绝不无限尝试。

最终状态：

```text
PASS
ACCEPT_PARTIAL
UNRESOLVED
NEEDS_OCR
```

`ACCEPT_PARTIAL` 是正常成功结果。

## 4.5 Local AI prompt 与 schema

操作提示词：

```text
prompts/local_ai/PDF_EVIDENCE_AGENT.md
```

结构化 review contract：

```text
schemas/pdf_evidence_review.schema.json
```

Prompt 本身属于运行版本的一部分。后续数据库要保存：

```text
prompt_version / prompt_hash
extractor_version
```

---

# 5. Reference 与 Citation Graph

## 5.1 Raw reference 是一等实体

PDF 中识别到的一条引用先保存：

```text
paper_reference
- citing_paper
- source_document
- attempt_id
- ordinal nullable
- raw_text
- parsed fields
- parse method
- confidence/status
```

不能因为暂时匹配不到 Paperazzi paper 就丢弃。

## 5.2 Reference matching 与 raw parsing 分离

```text
paper_reference
      ↓
paper_reference_match
      ↓
cited paper
```

只有 ACCEPTED match 才产生：

```text
Paper A --CITES--> Paper B
```

## 5.3 DOI 不是主匹配轴

200 篇测试的 785 条确定性 segmented references 中仅找到 10 个 DOI，说明老文献和常见 bibliography 不能依赖 DOI。

匹配梯度：

```text
DOI_EXACT
TITLE_EXACT_NORMALIZED
AUTHOR_YEAR_JOURNAL
JOURNAL_VOLUME_PAGE_YEAR
BIBLIOGRAPHIC_COMPOSITE
AI_RESOLVED
UNRESOLVED
```

DOI 有则极强，但 absence 正常。

## 5.4 Citation graph 的用途

- in-library citation network；
- foundational papers；
- method/topic lineage；
- author-to-author citation projection；
- knowledge bridge；
- citation path；
- 与 OpenAlex/Semantic Scholar/OpenCitations 比较；
- 解释“为什么这些论文和作者构成同一研究路径”。

 false positive citation edge 比 missing citation edge 更有害，因此 matching 必须保守。

---

# 6. 作者信息与 Identity

## 6.1 第一作者

优先由 Zotero `creatorType=author` 与顺序确定。

PDF displayed author line 可以作为补充/核对 evidence，但不无痕覆盖 Zotero。

## 6.2 通讯作者

来源可以包括：

```text
manual assertion
local PDF correspondence/e-mail evidence
publisher/online structured metadata
online AI research
```

PDF fixed parser 先产出 correspondence evidence；AI review/resolver 再判断具体 author。

## 6.3 Affiliation

PDF 第一页/前几页的 affiliation 是重要的 identity evidence。

本地 AI 可以根据：

- Zotero creators；
- displayed author line；
- superscript/符号；
- affiliation block；
- e-mail domain；

提出 author-affiliation candidate。

所有结果保留 source page/raw evidence。

## 6.4 Author identity

内部 ID：

```text
author_id = UUIDv7 / ULID
```

ORCID/OpenAlex 等只是 mappings。

可使用证据：

- ORCID exact；
- DOI-author-ORCID；
- local PDF affiliation/e-mail；
- online affiliation；
- coauthor overlap；
- research topics；
- titles/year；
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

---

# 7. 增量更新

## 7.1 Zotero scan diff

Paperazzi 自己维护：

```text
NEW
MODIFIED
UNCHANGED
REMOVED
RESTORED
```

最终依据 canonical semantic hash。

## 7.2 PDF 独立增量

PDF 不应每次重解析。

Document change key：

```text
preferred: Zotero storageHash
fallback: file size + mtime
```

重新处理条件：

- PDF 第一次本地可用；
- PDF 文件变化；
- extractor version 变化；
- review prompt version 发生有意义变化；
- 用户显式 rebuild。

单纯 Zotero bibliographic metadata 改变不要求重读未变化 PDF。

---

# 8. Paperazzi persistence model

Paperazzi 使用独立：

```text
data/paperazzi.sqlite3
```

## 8.1 Zotero projection

```text
zotero_scan_runs
zotero_item_state
papers
paper_attachments
```

## 8.2 PDF/document evidence

```text
paper_documents
```

包含：

```text
document_id
paper_id
zotero_attachment_key
local_path
availability_status
document_change_key
extractor_version
prompt_version
prompt_hash
extraction_status
accepted_attempt_id
attempt_count
last_reviewed_at
```

## 8.3 Extraction history

新增一等表：

```text
document_extraction_attempts
```

字段至少包括：

```text
attempt_id
document_id
attempt_number             1..3
actor                      DETERMINISTIC / LOCAL_AI_CONTROLLED / OCR
strategy
strategy_parameters_json
extractor_version
prompt_version
prompt_hash
text_source
decision
problem_codes_json
quality_notes
output_hash
runtime_artifact_path nullable
started_at / completed_at
```

约束：

```text
UNIQUE(document_id, attempt_number)
attempt_number BETWEEN 1 AND 3
```

## 8.4 Evidence spans

```text
document_evidence_spans
- document_id
- attempt_id
- kind
- page_index
- bbox_json
- raw_text
- acceptance_status
```

`acceptance_status`：

```text
ACCEPTED
SUPERSEDED
REJECTED
CANDIDATE
```

这样 Round 1 错误结果仍然可审计，但不会进入后续 claims。

## 8.5 References

```text
paper_references
paper_reference_matches
```

reference 必须关联 originating `attempt_id`。

## 8.6 Authors / claims / relationships

继续使用：

```text
authors
author_aliases
author_external_ids
authorships
institutions
affiliations
education
sources
claims
author_relationships
topics
author_topics
events
```

AI 生成 candidate/claim，不直接执行 SQL。

---

# 9. 核心工作流

## Workflow A — Zotero update

```text
readonly snapshot
  ↓
CanonicalZoteroItem
  ↓
scan diff
  ↓
persist Zotero projection
```

## Workflow B — Local PDF Evidence

```text
NEW/changed/local-new PDF
  ↓
Attempt 1 deterministic parser
  ↓
mandatory local AI review
  ↓
PASS/PARTIAL or targeted retry (max 3)
  ↓
validated structured result
  ↓
deterministic persistence
  ↓
reference matching / author evidence
```

## Workflow C — Author enrichment

Local evidence 不足时生成固定 request package，在线 AI 返回标准 ZIP，本地 deterministic validator 导入。

## Workflow D — Monthly author watch

人工触发，检查：

- new papers；
- affiliation/position；
- awards/grants；
- conference/talk；
- lab moves；
- news；
- public profiles。

---

# 10. 网页信息架构

Paperazzi 是人物中心科研情报界面，不是 Zotero 网页复制。

## Author Profile

显示：

- portrait / preferred name；
- position / institution；
- research summary；
- topic evolution；
- career / education；
- collaborators；
- local + external papers；
- evidence；
- citation relations；
- news/events。

## Paper list

至少显示：

```text
Year | Title | Journal | Role | DOI | In Zotero | PDF
```

`PDF` 状态：

```text
Available → Open
Not local
None
```

Open PDF 不依赖 Zotero Desktop。

## Citation Explorer

可查看：

```text
paper → references
paper → cited by (within known graph)
author → cited authors
citation paths
```

## Review Center

用于：

- identity conflicts；
- merge/split；
- claim conflicts；
- low-confidence author/corresponding mapping；
- unresolved PDF evidence；
- suspicious citation matches；
- schema warnings。

---

# 11. 外部数据源

外部 enrichment 不替代 Zotero/local PDF：

- ORCID；
- OpenAlex；
- Semantic Scholar；
- Crossref；
- publisher pages；
- university/lab/personal sites；
- later OpenCitations。

所有外部事实进入 Evidence/Claim 层。

---

# 12. 技术栈

Backend：

```text
Python
sqlite3 for Zotero read-only adapter
PyMuPDF for PDF evidence
FastAPI
SQLAlchemy 2
Alembic
Pydantic
SQLite + WAL + FTS5
```

Frontend：

```text
React
TypeScript
Vite
TanStack Query/Table
Cytoscape.js
Apache ECharts
```

v1 不需要 Neo4j、PostgreSQL 或 Elasticsearch。

---

# 13. 目录结构

```text
Paperazzi/
├── DESIGN.md
├── README.md
├── pyproject.toml
├── prompts/
│   └── local_ai/
│       └── PDF_EVIDENCE_AGENT.md
├── schemas/
│   └── pdf_evidence_review.schema.json
├── docs/
│   ├── architecture/
│   ├── phase1/
│   ├── phase2/
│   └── phase2_5/
├── src/paperazzi/
│   ├── zotero_sqlite/
│   ├── ingest/
│   ├── local_evidence/
│   ├── database/
│   ├── identity/
│   ├── graph/
│   ├── enrichment/
│   └── api/
├── scripts/
├── tests/
├── frontend/
└── data/
```

详细模块边界：

```text
docs/architecture/REPOSITORY_LAYOUT.md
```

---

# 14. 开发阶段

## Phase 1 — Zotero SQLite reconnaissance

完成。

## Phase 2 — Production Zotero reader

完成核心验证与 deleted-child correctness fix。

## Phase 2.5 — Local PDF Evidence

已完成 200 篇 deterministic validation。

当前新增 Phase 2.5b：

> 验证 mandatory local-AI review + maximum-three-attempt adaptive retry workflow。

测试说明：

```text
docs/phase2_5/AI_ADAPTIVE_REVIEW_VALIDATION.md
```

## Phase 3 — Paperazzi DB

建立：

- Zotero scan persistence；
- authors/papers/authorships；
- paper_documents；
- document_extraction_attempts；
- evidence spans；
- references / reference matches；
- claims/sources；
- incremental scan/diff。

## Phase 4 — Identity + local semantic resolution

- author identity；
- PDF author-affiliation/corresponding mapping；
- in-library reference matching；
- basic graph。

## Phase 5 — Core website

- Dashboard；
- Authors；
- Author Profile；
- Papers；
- Open PDF；
- citation/network views；
- Review Center。

## Phase 6 — Online enrichment + research intelligence

- enrichment package；
- monthly author watch；
- Library Gap Detector；
- events/news；
- advanced graph/topic evolution。

---

# 15. v0.4 验收思想

Paperazzi 不追求“每份 PDF 100% 完美解析”。

正确目标是：

> **在海量、格式异构的私人学术库中，以可控成本最大化可靠信息产出，并确保每一条结果可追溯。**

因此：

```text
PASS             正常
ACCEPT_PARTIAL   正常且重要
UNRESOLVED       可接受
NEEDS_OCR        可接受
```

以下原则不可妥协：

- 一个困难 PDF 不阻塞整个 batch；
- 一份 PDF 最多三轮；
- Round 1 必须由 local AI review；
- AI 不无痕覆盖 deterministic output；
- prompt / parser version 可追溯；
- raw reference 不因无法匹配而丢失；
- false citation edge 比 missing edge 更糟；
- 系统性错误进入固定代码与 regression test；
- 长尾异构版式交给 AI-controlled retry。

---

# 16. 当前关键文件

```text
docs/architecture/ZOTERO_DATA_BOUNDARY.md
docs/architecture/LOCAL_PDF_EVIDENCE.md
docs/architecture/AI_SUPERVISED_PDF_EXTRACTION.md
prompts/local_ai/PDF_EVIDENCE_AGENT.md
schemas/pdf_evidence_review.schema.json
docs/phase2_5/PHASE2_5_ANALYSIS.md
docs/phase2_5/AI_ADAPTIVE_REVIEW_VALIDATION.md
```

这些文件共同定义当前 Paperazzi v0.4 的本地数据与 PDF evidence 行为。