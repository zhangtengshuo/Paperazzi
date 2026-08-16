# Paperazzi Zotero SQLite Probe Report

- **Generated:** `2026-08-16T13:56:04+00:00`
- **Label:** `zotero-open`
- **Source:** `/mnt/d/zotero/zotero.sqlite`
- **Analysis DB:** `/home/shuo/develop/Paperazzi/probe-output/20260816-215601-zotero-open/zotero_snapshot.sqlite`
- **Snapshot created:** `True`
- **Read mode:** `mode=ro + PRAGMA query_only=ON`
- **Platform:** `Linux-6.18.33.2-microsoft-standard-WSL2-x86_64-with-glibc2.39`
- **Python / SQLite:** `3.13.9` / `3.51.0`

## 1. Source database state

- Size: `133648384` bytes
- mtime (UTC): `2026-08-13T15:47:43+00:00`

| sidecar | exists | size_bytes | mtime |
| --- | --- | --- | --- |
| -wal | False |  |  |
| -shm | False |  |  |
| -journal | True | 1572864 | 2026-08-13T15:47:43+00:00 |

## 2. SQLite pragmas

| pragma | value |
| --- | --- |
| user_version | 0 |
| application_id | 0 |
| schema_version | 1 |
| data_version | 1 |
| journal_mode | "delete" |
| page_count | 32629 |
| page_size | 4096 |
| freelist_count | 0 |
| foreign_keys | 0 |
| query_only | 1 |
| quick_check | ["ok"] |

## 3. Schema identity

- Schema fingerprint SHA-256: `7740b572c59e3caa976528b24edf074382add503730a5898aec732de9c8ecd10`
- Tables/views discovered: `61`

### Key object counts

| object | rows |
| --- | --- |
| items | 5711 |
| itemTypes | 40 |
| itemData | 35959 |
| itemDataValues | 20816 |
| fields | 123 |
| fieldsCombined | 123 |
| creators | 7619 |
| itemCreators | 12518 |
| creatorTypes | 37 |
| itemAttachments | 2628 |
| collections | 121 |
| collectionItems | 3119 |
| tags | 727 |
| itemTags | 3326 |
| deletedItems | 51 |
| libraries | 2 |
| version | 13 |
| fulltextItems | 2413 |

### Key object columns

- **items** — `itemID:INTEGER, itemTypeID:INT, dateAdded:TIMESTAMP, dateModified:TIMESTAMP, clientDateModified:TIMESTAMP, libraryID:INT, key:TEXT, version:INT, synced:INT`
- **itemTypes** — `itemTypeID:INTEGER, typeName:TEXT, templateItemTypeID:INT, display:INT`
- **itemData** — `itemID:INT, fieldID:INT, valueID:?`
- **itemDataValues** — `valueID:INTEGER, value:?`
- **fields** — `fieldID:INTEGER, fieldName:TEXT, fieldFormatID:INT`
- **fieldsCombined** — `fieldID:INT, fieldName:TEXT, label:TEXT, fieldFormatID:INT, custom:INT`
- **creators** — `creatorID:INTEGER, firstName:TEXT, lastName:TEXT, fieldMode:INT`
- **itemCreators** — `itemID:INT, creatorID:INT, creatorTypeID:INT, orderIndex:INT`
- **creatorTypes** — `creatorTypeID:INTEGER, creatorType:TEXT`
- **itemAttachments** — `itemID:INTEGER, parentItemID:INT, linkMode:INT, contentType:TEXT, charsetID:INT, path:TEXT, syncState:INT, storageModTime:INT, storageHash:TEXT, lastProcessedModificationTime:INT, lastRead:INT`
- **collections** — `collectionID:INTEGER, collectionName:TEXT, parentCollectionID:INT, clientDateModified:TIMESTAMP, libraryID:INT, key:TEXT, version:INT, synced:INT`
- **collectionItems** — `collectionID:INT, itemID:INT, orderIndex:INT`
- **tags** — `tagID:INTEGER, name:TEXT`
- **itemTags** — `itemID:INT, tagID:INT, type:INT`
- **deletedItems** — `itemID:INTEGER, dateDeleted:?`
- **libraries** — `libraryID:INTEGER, type:TEXT, editable:INT, filesEditable:INT, version:INT, storageVersion:INT, lastSync:INT, archived:INT, isAdmin:INT`
- **version** — `schema:TEXT, version:INT`
- **fulltextItems** — `itemID:INTEGER, indexedPages:INT, totalPages:INT, indexedChars:INT, totalChars:INT, version:INT, synced:INT`

## 4. Zotero reference data

### version

```json
[
  {
    "schema": "globalSchema",
    "version": 42
  },
  {
    "schema": "system",
    "version": 32
  },
  {
    "schema": "userdata",
    "version": 125
  },
  {
    "schema": "triggers",
    "version": 18
  },
  {
    "schema": "compatibility",
    "version": 7
  },
  {
    "schema": "translators",
    "version": 1783437194
  },
  {
    "schema": "delete",
    "version": 74
  },
  {
    "schema": "styles",
    "version": 1783437194
  },
  {
    "schema": "fulltext_2",
    "version": 38
  },
  {
    "schema": "repository",
    "version": 1784133974
  },
  {
    "schema": "lastcheck",
    "version": 1784133976
  },
  {
    "schema": "fulltext_1",
    "version": 12953
  },
  {
    "schema": "lastsync",
    "version": 1786636064
  }
]
```

### libraries

```json
[
  {
    "libraryID": 1,
    "type": "user",
    "editable": 1,
    "filesEditable": 1,
    "version": 12953,
    "storageVersion": 12953,
    "lastSync": 1786636063,
    "archived": 0,
    "isAdmin": 0
  },
  {
    "libraryID": 2,
    "type": "group",
    "editable": 1,
    "filesEditable": 1,
    "version": 38,
    "storageVersion": 0,
    "lastSync": 1786636037,
    "archived": 0,
    "isAdmin": 1
  }
]
```

### itemTypes

```json
[
  {
    "itemTypeID": 1,
    "typeName": "annotation",
    "templateItemTypeID": null,
    "display": 1
  },
  {
    "itemTypeID": 2,
    "typeName": "artwork",
    "templateItemTypeID": null,
    "display": 1
  },
  {
    "itemTypeID": 3,
    "typeName": "attachment",
    "templateItemTypeID": null,
    "display": 1
  },
  {
    "itemTypeID": 4,
    "typeName": "audioRecording",
    "templateItemTypeID": null,
    "display": 1
  },
  {
    "itemTypeID": 5,
    "typeName": "bill",
    "templateItemTypeID": null,
    "display": 1
  },
  {
    "itemTypeID": 6,
    "typeName": "blogPost",
    "templateItemTypeID": null,
    "display": 1
  },
  {
    "itemTypeID": 7,
    "typeName": "book",
    "templateItemTypeID": null,
    "display": 1
  },
  {
    "itemTypeID": 8,
    "typeName": "bookSection",
    "templateItemTypeID": null,
    "display": 1
  },
  {
    "itemTypeID": 9,
    "typeName": "case",
    "templateItemTypeID": null,
    "display": 1
  },
  {
    "itemTypeID": 10,
    "typeName": "computerProgram",
    "templateItemTypeID": null,
    "display": 1
  },
  {
    "itemTypeID": 11,
    "typeName": "conferencePaper",
    "templateItemTypeID": null,
    "display": 1
  },
  {
    "itemTypeID": 12,
    "typeName": "dataset",
    "templateItemTypeID": null,
    "display": 1
  },
  {
    "itemTypeID": 13,
    "typeName": "dictionaryEntry",
    "templateItemTypeID": null,
    "display": 1
  },
  {
    "itemTypeID": 14,
    "typeName": "document",
    "templateItemTypeID": null,
    "display": 1
  },
  {
    "itemTypeID": 15,
    "typeName": "email",
    "templateItemTypeID": null,
    "display": 1
  },
  {
    "itemTypeID": 16,
    "typeName": "encyclopediaArticle",
    "templateItemTypeID": null,
    "display": 1
  },
  {
    "itemTypeID": 17,
    "typeName": "film",
    "templateItemTypeID": null,
    "display": 1
  },
  {
    "itemTypeID": 18,
    "typeName": "forumPost",
    "templateItemTypeID": null,
    "display": 1
  },
  {
    "itemTypeID": 19,
    "typeName": "hearing",
    "templateItemTypeID": null,
    "display": 1
  },
  {
    "itemTypeID": 20,
    "typeName": "instantMessage",
    "templateItemTypeID": null,
    "display": 1
  },
  {
    "itemTypeID": 21,
    "typeName": "interview",
    "templateItemTypeID": null,
    "display": 1
  },
  {
    "itemTypeID": 22,
    "typeName": "journalArticle",
    "templateItemTypeID": null,
    "display": 1
  },
  {
    "itemTypeID": 23,
    "typeName": "letter",
    "templateItemTypeID": null,
    "display": 1
  },
  {
    "itemTypeID": 24,
    "typeName": "magazineArticle",
    "templateItemTypeID": null,
    "display": 1
  },
  {
    "itemTypeID": 25,
    "typeName": "manuscript",
    "templateItemTypeID": null,
    "display": 1
  },
  {
    "itemTypeID": 26,
    "typeName": "map",
    "templateItemTypeID": null,
    "display": 1
  },
  {
    "itemTypeID": 27,
    "typeName": "newspaperArticle",
    "templateItemTypeID": null,
    "display": 1
  },
  {
    "itemTypeID": 28,
    "typeName": "note",
    "templateItemTypeID": null,
    "display": 1
  },
  {
    "itemTypeID": 29,
    "typeName": "patent",
    "templateItemTypeID": null,
    "display": 1
  },
  {
    "itemTypeID": 30,
    "typeName": "podcast",
    "templateItemTypeID": null,
    "display": 1
  },
  {
    "itemTypeID": 31,
    "typeName": "preprint",
    "templateItemTypeID": null,
    "display": 1
  },
  {
    "itemTypeID": 32,
    "typeName": "presentation",
    "templateItemTypeID": null,
    "display": 1
  },
  {
    "itemTypeID": 33,
    "typeName": "radioBroadcast",
    "templateItemTypeID": null,
    "display": 1
  },
  {
    "itemTypeID": 34,
    "typeName": "report",
    "templateItemTypeID": null,
    "display": 1
  },
  {
    "itemTypeID": 35,
    "typeName": "standard",
    "templateItemTypeID": null,
    "display": 1
  },
  {
    "itemTypeID": 36,
    "typeName": "statute",
    "templateItemTypeID": null,
    "display": 1
  },
  {
    "itemTypeID": 37,
    "typeName": "thesis",
    "templateItemTypeID": null,
    "display": 1
  },
  {
    "itemTypeID": 38,
    "typeName": "tvBroadcast",
    "templateItemTypeID": null,
    "display": 1
  },
  {
    "itemTypeID": 39,
    "typeName": "videoRecording",
    "templateItemTypeID": null,
    "display": 1
  },
  {
    "itemTypeID": 40,
    "typeName": "webpage",
    "templateItemTypeID": null,
    "display": 1
  }
]
```

### creatorTypes

```json
[
  {
    "creatorTypeID": 1,
    "creatorType": "artist"
  },
  {
    "creatorTypeID": 2,
    "creatorType": "contributor"
  },
  {
    "creatorTypeID": 3,
    "creatorType": "performer"
  },
  {
    "creatorTypeID": 4,
    "creatorType": "originalCreator"
  },
  {
    "creatorTypeID": 5,
    "creatorType": "composer"
  },
  {
    "creatorTypeID": 6,
    "creatorType": "wordsBy"
  },
  {
    "creatorTypeID": 7,
    "creatorType": "translator"
  },
  {
    "creatorTypeID": 8,
    "creatorType": "sponsor"
  },
  {
    "creatorTypeID": 9,
    "creatorType": "cosponsor"
  },
  {
    "creatorTypeID": 10,
    "creatorType": "author"
  },
  {
    "creatorTypeID": 11,
    "creatorType": "commenter"
  },
  {
    "creatorTypeID": 12,
    "creatorType": "editor"
  },
  {
    "creatorTypeID": 13,
    "creatorType": "seriesEditor"
  },
  {
    "creatorTypeID": 14,
    "creatorType": "bookAuthor"
  },
  {
    "creatorTypeID": 15,
    "creatorType": "counsel"
  },
  {
    "creatorTypeID": 16,
    "creatorType": "programmer"
  },
  {
    "creatorTypeID": 17,
    "creatorType": "reviewedAuthor"
  },
  {
    "creatorTypeID": 18,
    "creatorType": "recipient"
  },
  {
    "creatorTypeID": 19,
    "creatorType": "director"
  },
  {
    "creatorTypeID": 20,
    "creatorType": "producer"
  },
  {
    "creatorTypeID": 21,
    "creatorType": "scriptwriter"
  },
  {
    "creatorTypeID": 22,
    "creatorType": "castMember"
  },
  {
    "creatorTypeID": 23,
    "creatorType": "host"
  },
  {
    "creatorTypeID": 24,
    "creatorType": "guest"
  },
  {
    "creatorTypeID": 25,
    "creatorType": "narrator"
  },
  {
    "creatorTypeID": 26,
    "creatorType": "interviewee"
  },
  {
    "creatorTypeID": 27,
    "creatorType": "interviewer"
  },
  {
    "creatorTypeID": 28,
    "creatorType": "cartographer"
  },
  {
    "creatorTypeID": 29,
    "creatorType": "inventor"
  },
  {
    "creatorTypeID": 30,
    "creatorType": "attorneyAgent"
  },
  {
    "creatorTypeID": 31,
    "creatorType": "podcaster"
  },
  {
    "creatorTypeID": 32,
    "creatorType": "executiveProducer"
  },
  {
    "creatorTypeID": 33,
    "creatorType": "seriesCreator"
  },
  {
    "creatorTypeID": 34,
    "creatorType": "presenter"
  },
  {
    "creatorTypeID": 35,
    "creatorType": "chair"
  },
  {
    "creatorTypeID": 36,
    "creatorType": "organizer"
  },
  {
    "creatorTypeID": 37,
    "creatorType": "creator"
  }
]
```

## 5. Aggregate statistics

### Items by type

| item_type | n |
| --- | --- |
| attachment | 2628 |
| journalArticle | 2430 |
| note | 427 |
| annotation | 101 |
| bookSection | 48 |
| book | 45 |
| preprint | 10 |
| conferencePaper | 8 |
| webpage | 7 |
| patent | 5 |
| computerProgram | 1 |
| thesis | 1 |

### Creator links by type

| creator_type | n |
| --- | --- |
| author | 12344 |
| editor | 85 |
| seriesEditor | 66 |
| inventor | 22 |
| bookAuthor | 1 |

### Attachments by mode/type

| linkMode | contentType | n |
| --- | --- | --- |
| 1 | application/pdf | 1238 |
| 0 | application/pdf | 1189 |
| 3 | text/html | 179 |
| 1 | text/html | 13 |
| 4 | image/png | 3 |
| 0 | application/x-Research-Info-Systems | 2 |
| 0 | image/png | 2 |
| 0 | application/epub+zip | 1 |
| 0 | application/octet-stream | 1 |

### Items by library

| libraryID | n |
| --- | --- |
| 1 | 5673 |
| 2 | 38 |

## 6. Content samples

### Recent bibliographic items

| itemID | key | type | title | creators | dateModified |
| --- | --- | --- | --- | --- | --- |
| 5698 | WJ24ZRL5 | journalArticle | On the Foundations of Combinatorial Theory I. Theory of Miibius Functions | Z Wahrseheinlichkeitstheorie [author] | 2026-08-03 03:43:24 |
| 5697 | ISXE3SQW | journalArticle | Theory of projections with nonorthogonal basis sets: Partitioning techniques and effective Hamiltonians | M. Soriano [author]; J. J. Palacios [author] | 2026-08-01 12:10:40 |
| 5699 | DPYWY6NC | journalArticle | Corresponding Orbitals and the Nonorthogonality Problem in Molecular Quantum Mechanics | Harry F. King [author]; Richard E. Stanton [author]; Hojing Kim [author]; Robert E. Wyatt [author]; Robert G. Parr [author] | 2026-08-01 12:10:32 |
| 5700 | 6WAAIXPY | journalArticle | The generalized Slater–Condon rules | Jacob Verbeek [author]; Joop H. Van Lenthe [author] | 2026-08-01 12:10:28 |
| 5701 | AYWJ9L7Q | journalArticle | Efficient and Flexible Computation of Many-Electron Wave Function Overlaps | Felix Plasser [author]; Matthias Ruckenbauer [author]; Sebastian Mai [author]; Markus Oppel [author]; Philipp Marquetand [author]; Leticia González [author] | 2026-08-01 12:10:26 |
| 5702 | SSWLIWPW | journalArticle | Symmetrical Windowing for Quantum States in Quasi-Classical Trajectory Simulations | Stephen J. Cotton [author]; William H. Miller [author] | 2026-08-01 12:10:22 |
| 5655 | 4VLY4CX3 | journalArticle | On the Theory of Relaxation Processes | A. G. Redfield [author] | 2026-08-01 08:08:10 |
| 5656 | AKYWUBHN | journalArticle | QuTiP-BoFiN: A bosonic and fermionic numerical hierarchical-equations-of-motion library with applications in light-harvesting, quantum control, and single-molecule electronics | Neill Lambert [author]; Tarun Raheja [author]; Simon Cross [author]; Paul Menczel [author]; Shahnawaz Ahmed [author]; Alexander Pitchford [author]; Daniel Burgarth [author]; Franco Nori [author] | 2026-08-01 08:08:06 |
| 5657 | CJJW9AMT | journalArticle | Semiclassical Description of Nonadiabatic Quantum Dynamics | Gerhard Stock [author]; Michael Thoss [author] | 2026-08-01 08:08:03 |
| 5658 | F2Y2ISIU | journalArticle | Multimode vibronic coupling effects in molecules | L. S. Cederbaum [author]; H. Köppel [author]; W. Domcke [author] | 2026-08-01 08:07:56 |

### PDF attachment samples

| itemID | key | linkMode | contentType | stored path | resolution | exists |
| --- | --- | --- | --- | --- | --- | --- |
| 5711 | ILQUL7WC | 0 | application/pdf | storage:Cotton和Miller - 2013 - Symmetrical Windowing for Quantum States in Quasi-Classical Trajectory Simulations.pdf | zotero-storage | True |
| 5710 | 3TNJIQ5H | 0 | application/pdf | storage:Plasser 等 - 2016 - Efficient and Flexible Computation of Many-Electron Wave Function Overlaps.pdf | zotero-storage | True |
| 5709 | AVQHTZD2 | 0 | application/pdf | storage:Verbeek和Van Lenthe - 1991 - The generalized Slater–Condon rules.pdf | zotero-storage | True |
| 5708 | F8BGV3IM | 0 | application/pdf | storage:King 等 - 1967 - Corresponding Orbitals and the Nonorthogonality Problem in Molecular Quantum Mechanics.pdf | zotero-storage | True |
| 5707 | MD8N7CDD | 0 | application/pdf | storage:Wahrseheinlichkeitstheorie - On the Foundations of Combinatorial Theory I. Theory of Miibius Functions.pdf | zotero-storage | True |
| 5706 | QRV8DDP9 | 0 | application/pdf | storage:Soriano和Palacios - 2014 - Theory of projections with nonorthogonal basis sets Partitioning techniques and effective Hamiltoni.pdf | zotero-storage | True |
| 5705 | CXYJUJA3 | 0 | application/pdf | storage:amos1961.pdf | zotero-storage | True |
| 5704 | AEFN24ZF | 0 | application/pdf | storage:S0025-5718-1973-0348991-3.pdf | zotero-storage | True |
| 5703 | 4IVZX4E2 | 0 | application/pdf | storage:shapley1953.pdf | zotero-storage | True |
| 5696 | 4WY8T4VS | 0 | application/pdf | storage:Vester和Olsen - 2024 - Assessing the Partial Hessian Approximation in QMMM-Based Vibrational Analysis.pdf | zotero-storage | True |
| 5695 | BA2AU68Z | 0 | application/pdf | storage:Bjornsson和Bühl - 2012 - Modeling Molecular Crystals by QMMM Self-Consistent Electrostatic Embedding for Geometry Optimizat.pdf | zotero-storage | True |
| 5694 | I2E3VQ6U | 0 | application/pdf | storage:Renaud和Grozema - 2015 - Intermolecular Vibrational Modes Speed Up Singlet Fission in Perylenediimide Crystals.pdf | zotero-storage | True |
| 5693 | SUJNEQ35 | 0 | application/pdf | storage:jz5023575_si_001.pdf | zotero-storage | True |
| 5692 | HKK53H24 | 0 | application/pdf | storage:jz5023575_si_001.pdf | zotero-storage | True |
| 5691 | YLD2IW9U | 0 | application/pdf | storage:Meyera)和Miller - 1979 - A classical analog for electronic degrees of freedom in nonadiabatic collision processes.pdf | zotero-storage | True |
| 5690 | CAH8YC9R | 0 | application/pdf | storage:Schuurman和Yarkony - 2007 - On the vibronic coupling approximation A generally applicable approach for determining fully quadra.pdf | zotero-storage | True |
| 5689 | 79RCEF92 | 0 | application/pdf | storage:Hu 等 - 2011 - Padé spectrum decompositions of quantum distribution functions and optimal hierarchical equations of.pdf | zotero-storage | True |
| 5688 | EDV76SYL | 0 | application/pdf | storage:Cotton和Miller - 2013 - Symmetrical windowing for quantum states in quasi-classical trajectory simulations Application to e.pdf | zotero-storage | True |
| 5687 | UWPSNA6J | 0 | application/pdf | storage:Cotton和Miller - 2016 - A new symmetrical quasi-classical model for electronically non-adiabatic processes Application to t.pdf | zotero-storage | True |
| 5686 | DL7XSTGF | 0 | application/pdf | storage:Cotton和Miller - 2019 - A symmetrical quasi-classical windowing model for the molecular dynamics treatment of non-adiabatic.pdf | zotero-storage | True |

## 7. Probe errors/warnings

No probe errors were recorded.

## What to return for Paperazzi implementation

Return **this Markdown report and `report.json`** to the developer/AI doing the next Paperazzi step.
Do **not** upload `zotero.sqlite` or `zotero_snapshot.sqlite` unless explicitly required.
