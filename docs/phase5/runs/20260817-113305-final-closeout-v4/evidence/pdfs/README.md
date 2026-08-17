# Phase 5 PDF evidence fixtures

These files are small, named evidence fixtures for the findings recorded in
the [Phase 5 final validation report](../../PHASE5_FINAL_VALIDATION_REPORT.md).
They are copies of the local PDF files used by the Phase 4 validation database;
the Zotero database, Zotero storage, and Paperazzi database were not modified.

| Fixture | Paper/document | Purpose | Size | SHA-256 |
| --- | --- | --- | ---: | --- |
| `paper-2468-main-article.pdf` | paper `2468`, document `2325` | Main article for PDF selection comparison; its first page contains a `CC-BY` license marker. | 4,424,956 bytes | `c2da19a915bf94c74e428619ddef1c02f8261b6b6fd7b432ff3a2a18dd9b061a` |
| `paper-2468-supporting-information.pdf` | paper `2468`, document `2324` | Supporting Information that currently wins the first-document lookup and exposes the primary-PDF selection issue. | 14,341,800 bytes | `27b3e3864a013d532c370343bdb967473aefb5912dc4896329d02adc651db8d2` |
| `paper-2467-fermionic-correspondence.pdf` | paper `2467`, document `2323` | Corresponding-author parsing example containing the two author markers and correspondence email line. | 768,876 bytes | `1c1e2f7699c57b5b491c28e657438b2b049cd7041a1ec5f911d92acee1733e67` |

The main article is visibly marked `CC-BY` on its first page. The associated
Supporting Information does not repeat a license statement on its first page;
it is included here at the user's request as a diagnostic fixture. The
Fermionic PDF is visibly marked `arXiv`; no stronger redistribution claim is
made here. If this repository is distributed publicly, the repository owner
should confirm that the chosen visibility and redistribution rights cover all
three files.

These fixtures are intended for remote-AI and local parser analysis only. They
do not constitute a fix for any of the findings.
