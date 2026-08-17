# Paperazzi 项目交接文档：总体流程、当前状态与下一步

**用途：下一聊天窗口的首要上下文。**  
**更新时间：2026-08-17**  
**当前仓库 HEAD（写本文档前）：`8e601f6b349d20f832bf1abae8980cec392f39d2`**  
**最近一次完整 Phase 5.5 真实测试所测试的代码 revision：`6417119e452ce3e3c088400ea7218bd10d654dc9`**

> 新聊天窗口应先完整阅读本文档，再阅读本文末尾列出的权威文件。不要仅依据 README 的旧状态描述判断当前阶段，也不要要求用户重新叙述本项目历史。

---

## 1. 项目目标

Paperazzi 是一个围绕**个人 Zotero 收藏**建立的 researcher-centric scholarly knowledge graph / scholarly author knowledge base。

它的边界条件不是“互联网中的全部论文”，而是：

> 以用户已经收藏在 Zotero 中的论文为兴趣边界，先忠实保存论文、全部作者和本地 PDF 证据，再逐步建立作者身份、作者角色、机构、引用关系、研究脉络和后续在线 enrichment。

核心输入分为三个证据通道：

```text
1. zotero.sqlite                structured metadata, READ ONLY
2. Zotero storage/*.pdf         local document evidence, READ ONLY
3. online/public information    future enrichment evidence
```

Paperazzi 有自己的 SQLite 数据库，不把任何状态写回 Zotero。

核心原则：

```text
Zotero read-only
PDF read-only
all source records preserved
AI does not create silent truth
all derived facts require provenance
wrong derived facts must be retractable
identity ambiguity is preferable to false merge
```

---

## 2. 当前强制运行环境

本地开发、真实数据库测试、PDF 测试和本地 AI 必须使用：

```text
environment manager = micromamba
environment name    = Paperazzi
Python              = 3.13
current tested Python = 3.13.15
```

`pyproject.toml` 当前明确要求：

```text
requires-python = ">=3.13,<3.14"
```

不要维护 Python 3.11 兼容层，也不要修改用户的 Anaconda/base 环境。

当前 Alembic head：

```text
0007_similar_author_review_queue
```

注意：README 中仍有一句旧文字声称 CI 同时测试 Python 3.11/3.13；这是**过时文档**。当前项目约定和 `pyproject.toml` 以 Python 3.13-only 为准。该 README 文字后续应顺手修正。

---

## 3. 项目总体数据流程

### 3.1 Zotero metadata ingestion

```text
real zotero.sqlite
    ↓ mode=ro
SQLite Backup API snapshot
    ↓
src/paperazzi/zotero_sqlite/
    ↓
CanonicalZoteroItem
    ↓
Paperazzi persistence
```

Zotero 内部稳定 identity 是：

```text
(libraryID, itemKey)
```

`itemID` 只用于内部 join/diagnostic。

允许 Zotero 信息缺失：无 DOI、无 abstract、无 creator、无 PDF 都不是 ingestion failure。

### 3.2 Paper/source-author persistence

所有 Zotero 论文作者都必须保存：

```text
Paper
  ↓
PaperCreatorMention
```

`PaperCreatorMention` 是**来源层的一次作者出现**，保存：

- paper；
- 作者顺序；
- Zotero 中的 first/last/display name；
- source creator ID；
- provenance。

关键语义：

```text
paper_creator_mention != canonical person
```

即使 identity unresolved，作者记录仍然存在，论文详情也必须显示。

### 3.3 Canonical author identity

```text
PaperCreatorMention
    ↓ identity candidate / decision
Canonical Author
    ↓
Authorship
```

只有 accepted canonical identity 才产生 semantic `Authorship`。

姓名规范化只能用于：

- search；
- blocking；
- review candidate generation。

**不能仅凭姓名自动 merge。**

### 3.4 Author name variants

同一人可能在不同来源中出现：

```text
Tengshuo Zhang
Teng-Shuo Zhang
Teng Shuo Zhang
T Zhang
T. Zhang
```

设计要求不是把这些名字“清洗成一个字符串”，而是：

```text
source spelling remains on PaperCreatorMention
        ↓
all spellings recorded in AuthorNameVariant
        ↓
multiple variants may point to one Canonical Author
```

人工 merge canonical identities 时：

- 不改写原始 `PaperCreatorMention`；
- 两侧全部 source spellings 保留；
- 全部 paper memberships/publications 转移到目标 canonical author；
- decision history 保留；
- source canonical author 变为 `MERGED`。

### 3.5 First / corresponding roles

第一作者和通讯作者是**论文级角色**，不是作者类别，也不能决定作者是否被记录。

```text
all authors recorded
        ↓
role metadata added where known
        ├── FIRST
        └── CORRESPONDING
```

第一作者主要来自 Zotero 作者顺序。

通讯作者必须来自可靠证据：PDF correspondence marker/email relation、可信结构化来源或人工确认。

后续 Phase 6 的广泛 public-profile enrichment 默认目标是：

```text
first author OR corresponding author
```

普通 coauthor 仍完整保留在 publication/network 中，但不默认做大规模人物档案 enrichment。

### 3.6 Local PDF evidence

PDF 是正式但可选的第二本地证据源。

```text
PaperDocument
  ↓
DocumentExtractionRun
  ↓
DocumentExtractionAttempt
  ↓
DocumentEvidenceSpan
  ├── affiliation evidence
  ├── correspondence/email evidence
  └── reference section/reference entries
```

PDF parser 使用 PyMuPDF + bounded local-AI review。

原则：

```text
Deterministic parse
    ↓
Local AI review
    ↓
PASS / ACCEPT_PARTIAL / RETRY / UNRESOLVED / NEEDS_OCR
```

最多有限次数 retry；不能无限 AI 重试。

### 3.7 PDF document role

同一 Zotero paper 可能有 article + SI。

当前 role：

```text
PRIMARY_ARTICLE
SUPPLEMENTARY
UNKNOWN
```

已修复过一个真实 bug：paper 2468 曾错误优先打开 `ct6c00473_si_001.pdf`（SI），而不是正文 PDF。

现在 primary-document selection 优先 article，SI 不允许产生 paper-level corresponding/affiliation truth。

### 3.8 Provenance / retraction

所有非 Zotero 派生事实遵循：

```text
SOURCE -> PROCESS -> EVIDENCE -> ASSERTION -> PROJECTION
```

错误不是 `DELETE`，而是：

```text
retain history
    + retract/supersede invalid support
    + recompute current projection
```

已有：

```text
retraction_events
retraction_impacts
```

可追踪：

- 哪个 document/attempt 被撤销；
- 哪些 downstream facts 失效；
- 是否还有其他独立 evidence 支撑同一事实。

新 reviewed rebuild 已经实现**跨 extraction run replacement**：如果新 rebuild 被 PASS/ACCEPT_PARTIAL 接受，会在同一事务中 retract 该 document 旧的 current accepted attempt；如果新 rebuild 没被接受，则旧有效 attempt 保持不变。

### 3.9 Reference / citation graph

PDF 中的 citation 先作为原始实体保存：

```text
PaperReference
    ↓ conservative resolution
PaperReferenceMatch
    ↓ ACCEPTED only
Paper A --CITES--> Paper B
```

`paper_reference != cited paper`。

当前 Phase 4 resolver 已实现并有 synthetic tests，但真实库目前没有 accepted reference inputs，所以：

```text
candidate reference inputs matched = 0
direct CITES edges = 0
```

这不是数据完整性 bug，但意味着**真实 citation graph 目前还没有形成**。

### 3.10 Backend / UI

当前已有：

```text
PaperazziQueryService
FastAPI
paper list/detail
all source authors including unresolved
FIRST/CORRESPONDING labels
author profile
publication chronology
coauthors
identity review
search
local PDF open
minimal browser UI
```

近期已增加：

- Paperazzi numeric paper ID 显示；
- Papers / Authors 分页和直接跳页；
- `IDENTITY UNRESOLVED` 明确说明；
- author sourced affiliation/contact evidence；
- multi-candidate Identity Review；
- manual Merge / Different people / Link / Not same / Create separate identity。

---

## 4. 已完成阶段

```text
Phase 1   Zotero SQLite reconnaissance                         PASS
Phase 2   production read-only Zotero adapter/reader          PASS
Phase 2.5 local PDF evidence architecture + parser baseline   PASS
Phase 3   relational persistence + incremental scan           PASS
Phase 3.1 persistence hardening                               PASS
Phase 4   author identity + reference resolution model        PASS
Phase 5   backend/minimal UI                                  IN PROGRESS
Phase 5.5 identity reconciliation + correspondence validation NOT PASSED
```

Phase 4 的真实库 closeout：

```text
papers with source authors                2485
source author mentions                   12207
canonical authors                         7398
accepted author memberships              10448
active authorships                       10448
unresolved author mentions                1759
resolved first-author papers              2028
unresolved first-author papers             457
foreign-key violations                       0
name-only auto-merges                        0
```

---

## 5. 最新 Phase 5.5 真实测试结果

权威报告：

```text
docs/phase5/runs/20260817-170014-phase5_5-identity-correspondence/
  PHASE5_5_VALIDATION_REPORT.md
```

真实测试使用代码 revision：

```text
6417119e452ce3e3c088400ea7218bd10d654dc9
```

运行环境：

```text
Python 3.13.15
Alembic 0007_similar_author_review_queue
136 tests / OK
0 failures
0 errors
0 skips
```

测试全部在 Paperazzi DB 副本上完成：

```text
Zotero modified = NO
live Paperazzi DB modified = NO
Anaconda/base modified = NO
foreign_key_check = []
```

### 5.1 Phase 5.5 status

```text
PHASE5_5_STATUS = AWAITING_USER_BROWSER_CONFIRMATION
PYTHON_313_CONTRACT = PASS
SYNTHETIC_REGRESSION = PASS
NAME_VARIANT_RECONCILIATION = FAIL
SIMILAR_NAME_CANDIDATES = PASS
IDENTITY_REVIEW_ACTIONS = PASS
IDENTITY_REVIEW_REAL_SAMPLE = PENDING_USER_REVIEW
CANONICAL_DIFFERENT_PAIR_PERSISTENCE = PASS
PAGINATION_UX = FAIL
PAPER_ID_TRACEABILITY = PASS
IDENTITY_UNRESOLVED_EXPLANATION = PASS
SOURCED_AUTHOR_EVIDENCE_API = PASS
CORRESPONDENCE_BENCHMARK = FAIL
FULL_CORRESPONDENCE_POPULATION = BLOCKED_BY_BENCHMARK
```

因此：**不能把 Phase 5.5 描述为通过。**

---

## 6. 当前最重要的问题

## P0 — 通讯作者 parser/resolver 的真实准确率严重不足

80 篇真实 primary PDF benchmark：

```text
reviewed cases = 80
explicit correspondence present = 70
TP = 25
FP = 2
FN = 83
precision = 0.9259259259
recall = 0.2314814815
```

项目门槛是：

```text
false positives = 0
precision = 1.0
recall >= 0.90
```

当前远未达到，因此：

```text
FULL_CORRESPONDENCE_POPULATION = BLOCKED_BY_BENCHMARK
```

不能为了 coverage 直接批量扫描 2161+ PDF 并把推断写成 accepted truth。

### 已知失败类型

#### 1. 普通 `Electronic mail` 被误认为 corresponding author

Paper 389：

```text
On the role of symmetry in XDW-CASPT2
```

PDF 明确通讯作者是 Roland Lindh，但 parser 从普通 Electronic mail 行选中了 Stefano Battaglia。

必须建立明确语义：

```text
email evidence != correspondence evidence
```

有 email 只能说明 contact/e-mail 与某人有关，不自动说明 corresponding role。

#### 2. 星号/符号 author-header 信息没有稳定保留

真实出版社常见：

```text
*
**
***
†
‡
superscript letter/number
```

author line 与 footnote/affiliation/correspondence block 的对应关系目前没有可靠恢复。

#### 3. 多通讯作者 recall 很低

例如：

```text
Paper 2169: Dylan M. Owen + Patrick Rubin-Delanchy
当前只预测 Dylan M. Owen

Paper 1608: Fernando Fernández-Lázaro + Dirk M. Guldi
当前只预测 Dirk M. Guldi
```

parser/resolver 需要天然支持 0/1/N corresponding authors，而不是围绕单一作者设计。

#### 4. grouped email block 会错误 over-map

Paper 1683：PDF 用 `* / ** / ***` 映射 Yue Zhang、Mei Lin、Chenglin Zhou，但 parser 又错误加入 Xiaobin Zhou。

#### 5. correspondence 与 canonical identity 绑定过紧

Paper 389 的 Roland Lindh source mention 仍 unresolved，因此没有 active canonical Authorship。这会阻碍 paper-level correspondence evidence 投影。

这里存在一个重要架构问题：

> **通讯作者首先是“某篇论文中的 source author mention 的角色”，不应要求 canonical person 已经解析成功才能保存。**

下一轮应认真考虑把 correspondence assertion/evidence 首先关联到：

```text
PaperCreatorMention
```

然后在 canonical identity 可用时再投影到 `Authorship` / `Author`。

这样可以避免：

```text
source PDF 明明能证明“第 3 个作者是通讯作者”
但因为这个人 canonical identity unresolved
于是 Paperazzi 什么都不能记录
```

这应是下一轮设计重点之一。

---

## P1 — 真实姓名 variant 归并尚未得到真实语料验证

代码侧 synthetic tests 已证明：

- `Tengshuo Zhang` / `Teng-Shuo Zhang` 可进入 similar review；
- Merge 后两种 spelling 保留；
- publication memberships 保留；
- reverse merge 可行；
- same-paper merge 被阻断；
- `Different people` 可以永久抑制同一 pair 再次推荐；
- structured given/family reversal 进入 review candidate；
- initials/full name 可以生成 candidate；
- 姓名相似不会自动 merge。

但真实库状态是：

```text
accepted memberships = 10448
canonical authors with >1 accepted mention = 1145
canonical authors with >1 distinct SOURCE raw spelling = 0
```

因此 `NAME_VARIANT_RECONCILIATION = FAIL` 并不是 sync 函数崩溃，而是：

> 当前 conservative identity state 还没有真实 canonical author 已经被人工确认合并多个 source spelling，因此无法证明 real-data variant retention。

与此同时 similar-name scan 找到：

```text
pairs examined = 4895
candidate sources = 2182
open SIMILAR_AUTHOR_IDENTITY rows created/updated = 500
runtime = 2.267 s
```

这说明潜在 duplicate identities 很多，但尚未人工 review。

下一步应由用户/本地 AI 对真实候选分批做：

```text
SAME_PERSON
DIFFERENT_PERSON
UNCERTAIN
```

UNCERTAIN 不做任何强制决策。

注意 queue 当前每次最多创建/更新 500 个 similar review entry；需要评估这个 cap 是否符合后续人工维护方式。

---

## P1 — 仍有大量 unresolved author identities

当前：

```text
unresolved author mentions = 1759
unresolved first-author papers = 457
```

这个状态本身符合“宁缺毋错”的原则，但会影响：

- corresponding author projection；
- future enrichment targeting；
- author profile completeness；
- coauthor/career timeline reasoning。

不要通过降低 name-only identity threshold 来解决。

正确方向应是逐步增加证据：

```text
name variants
paper history
coauthor overlap
affiliation
e-mail domain
ORCID/external IDs
online profile evidence
manual decisions
```

---

## P1 — 作者 sourced affiliation/contact API 已实现，但真实库尚未 population

Phase 5.5 测试副本：

```text
GET /api/authors/{id}/evidence -> rows = 0
```

这是因为真实 copy 当前没有 populated `authorship_evidence`。

Synthetic tests 已证明：

- ACCEPTED/CANDIDATE 可区分；
- provenance 可返回；
- SUPERSEDED/retracted evidence 不作为 current 展示；
- candidate affiliation 不会被错误提升成 canonical “current affiliation”。

但真实功能价值必须等 PDF evidence workflow population 后才能验证。

---

## P1 — 浏览器分页/交互尚未人工确认

源码与 ASGI tests 已确认：

- sticky pager 存在；
- direct page input 存在；
- Paperazzi ID 存在；
- `IDENTITY UNRESOLVED` 文案存在；
- multi-candidate review API 返回候选。

但 Phase 5.5 report 中：

```text
PAGINATION_UX = FAIL
```

原因仅是**没有真实浏览器人工 sign-off**，不是 synthetic test failure。

用户需要最终确认：

- Papers/Authors 翻页；
- direct jump；
- last page；
- back navigation；
- long-page sticky pager；
- multi-candidate review 按钮；
- Different people；
- same-paper merge disabled；
- paper 2468 打开的是否为正文而非 SI。

---

## P2 — citation graph 仍为空

Phase 4 resolver 已实现，但真实库当前：

```text
accepted reference inputs = 0
direct CITES edges = 0
```

这是因为严格 evidence gate 没有接受真实 reference entries，而不是 resolver 没代码。

在 correspondence 修复之后，需要重新推进 reviewed PDF reference extraction，才能让 citation graph 有真实数据。

不能为了生成图而把 CANDIDATE reference 当成 ACCEPTED。

---

## P2 — README 有一处运行环境描述过时

README 仍写 CI 测试 Python 3.11/3.13。

当前事实是：

```text
Python 3.13 only
pyproject: >=3.13,<3.14
```

下一轮可做一个很小的文档修正，避免误导。

---

## 7. 已解决、不要重复修的问题

下一个聊天窗口不应重新把以下问题当成未处理：

### Zotero safety

已建立 read-only URI / snapshot / query-only 路径。禁止写 Zotero。

### 全作者记录

所有论文作者都保存到 `paper_creator_mentions`；FIRST/CORRESPONDING 是 additive role，不是 author filter。

### SI 被当正文

已建立 DocumentRole + primary selection；SUPPLEMENTARY 不能支持 paper-level authorship/reference truth。

### 错误证据无法追踪

已建立 provenance/retraction ledger。

### reviewed rebuild 与旧 accepted attempt 同时 current

已修：接受新 rebuild 时先 retract 旧 current accepted attempt；不接受新 attempt 则旧数据保持。

### 通讯作者第二个 email 被句号吞掉

已修 terminal punctuation email extraction regression。

### `Marc Illa` 对 `marc.illasubina@...` 的 local-part 映射

已增加 conservative compact-name/local-part mapping synthetic regression；但总体 correspondence benchmark 仍说明 resolver 远未完善。

### Identity Review 只有展示没有操作

已支持：

```text
Link mention
Not same person (mention -> author)
Create separate identity
Merge canonical identities in either direction
Different people (canonical pair)
```

### 相似姓名 pair 每次重复出现

已支持 canonical `Different people` decision，后续 refresh 会排除该 unordered pair。

### 相似 review 只显示一个 candidate

已改为一个 source identity 页面显示多个候选。

### SQLite ResourceWarning

Web engine 已在进程退出时 dispose；Python 3.13 synthetic CI 不再出现 Paperazzi 自身 unclosed SQLite warning。

---

## 8. 当前 Identity Review 设计

### 8.1 unresolved source mention

```text
source PaperCreatorMention
    ↓
multiple candidate Canonical Authors
```

人工操作：

```text
Link
Not same person
Create separate identity
```

### 8.2 possible duplicate canonical identities

```text
Canonical Author A
    ↓
several similar Canonical Authors
```

页面应显示：

- all name variants；
- recent publications；
- coauthors；
- external IDs；
- similarity hint；
- same-paper conflict。

人工操作：

```text
Merge A -> B
Merge B -> A
Different people
```

相似度永远只是 review hint。

---

## 9. 100-PDF 远程分析样本

为了让下一个远程 AI 不依赖用户本机 PDF，Phase 5.5 已提交 100 个真实 primary PDF 样本：

```text
tests/fixtures/phase5_5_correspondence_pdf_sample_100/
```

manifest：

```text
tests/fixtures/phase5_5_correspondence_pdf_sample_100/MANIFEST.json
```

样本：

```text
PDF files = 100
total size = 241.3 MiB
total pages = 1389
SHA-256 mismatches = 0
unreadable PDFs = 0
random seed = 20260817
```

这批文件的主要用途是：

> 下一聊天窗口直接分析不同出版社 front matter / author marker / correspondence block 的版式，设计更可靠的 deterministic extraction 和 regression tests。

不要把这 100 篇本身当成完整统计 population。

---

## 10. 建议下一聊天窗口的工作顺序

### Step 1 — 先修 correspondence evidence model，而不是立即扩大 regex

首先明确语义层：

```text
EMAIL evidence
CORRESPONDENCE marker evidence
AUTHOR-MARKER association
SOURCE AUTHOR ROLE assertion
CANONICAL AUTHOR projection
```

重点讨论是否增加 source-mention-level corresponding assertion，使 unresolved identity 不阻断论文角色记录。

### Step 2 — 用 100-PDF sample 分版式分析失败模式

优先研究：

- ACS；
- RSC；
- Elsevier；
- Springer/Nature；
- Wiley；
- arXiv/preprint；
- LaTeX `Electronic mail:`；
- `Corresponding author:`；
- star/dagger/superscript；
- grouped multi-email；
- 多通讯作者。

不要先写“大一统 fuzzy regex”。

应形成小的 publisher/layout strategy + shared evidence model。

### Step 3 — 对 benchmark failures 写最小 regression tests

至少覆盖：

```text
Paper 389 style: ordinary Electronic mail must not imply correspondence
Paper 1683 style: *, **, *** exact mapping without extra author
Paper 2169 style: two corresponding authors
Paper 1608 style: two corresponding authors
```

### Step 4 — 重跑 80-paper ground-truth benchmark

门槛保持：

```text
FP = 0
precision = 1.0
recall >= 0.90
```

不允许为了 recall 放松 false-positive gate。

### Step 5 — benchmark 通过后才设计 full population

全库 population 必须：

- primary/eligible PDFs only；
- extraction run/attempt lineage；
- review status；
- idempotent；
- retractable；
- copy-first；
- before/after coverage report。

### Step 6 — 同时开始小批真实 Identity Review

从 500 个 `SIMILAR_AUTHOR_IDENTITY` 中抽样，用户确认：

```text
SAME_PERSON
DIFFERENT_PERSON
UNCERTAIN
```

目的是首次建立真实多 spelling canonical identities，并验证 `AuthorNameVariant` 在真实数据上的工作流。

### Step 7 — 浏览器人工验收

完成分页和 identity review UX sign-off。

### Step 8 — correspondence 稳定后再进入 Phase 6 enrichment

Phase 6 不应在 correspondence target set 大量错误/缺失时大规模启动。

后续 enrichment 应继续沿用：

```text
EnrichmentRun
  -> sourced assertions
  -> provenance links
  -> current profile projection
```

错误 person/source 必须可整批 retract。

---

## 11. 下一窗口必须保持的安全边界

1. **永远不写 Zotero。**
2. 真实 write-path 测试优先对 Paperazzi DB backup copy 操作。
3. 不修改 Anaconda/base；仅使用 micromamba `Paperazzi`。
4. Python 3.13 only。
5. 不因姓名相似自动 merge。
6. 不因存在 email 自动判为通讯作者。
7. 不因 unresolved identity 删除 source author。
8. 不把 CANDIDATE evidence 当成 accepted truth。
9. 不通过删除历史“修正”错误；使用 retraction/supersession + projection recompute。
10. 不为了测试指标伪造 accepted reference / name variant / correspondence truth。

---

## 12. 下一窗口建议首先读取的文件

按顺序：

```text
1. docs/NEXT_CHAT_HANDOFF.md
2. docs/phase5/runs/20260817-170014-phase5_5-identity-correspondence/PHASE5_5_VALIDATION_REPORT.md
3. docs/architecture/AUTHOR_RECORDING_AND_ENRICHMENT_SCOPE.md
4. docs/architecture/AUTHOR_IDENTITY_REVIEW.md
5. docs/architecture/PROVENANCE_AND_RETRACTION.md
6. docs/phase4/PHASE4_CLOSEOUT.md
7. DESIGN.md
8. tests/fixtures/phase5_5_correspondence_pdf_sample_100/MANIFEST.json
```

主要代码入口：

```text
src/paperazzi/zotero_sqlite/
src/paperazzi/local_evidence/pdf.py
src/paperazzi/database/
src/paperazzi/identity/authorship_evidence.py
src/paperazzi/identity/manual_review.py
src/paperazzi/identity/similar_names.py
src/paperazzi/provenance/
src/paperazzi/web/
scripts/rebuild_document_evidence.py
scripts/build_correspondence_benchmark.py
scripts/score_correspondence_benchmark.py
scripts/manage_provenance.py
```

---

## 13. 当前状态的一句话总结

> Paperazzi 的 Zotero ingestion、独立 persistence、保守作者 identity、provenance/retraction、backend/UI 骨架已经基本建立；当前真正阻塞下一阶段的是**真实 PDF 中通讯作者识别的 evidence model 与 recall/precision**，以及尚未经过真实人工归并的姓名 variant workflow。下一轮应以 80-paper ground truth 和已提交的 100-PDF 样本为中心修 correspondence，而不是继续扩大未经验证的全库自动化。
