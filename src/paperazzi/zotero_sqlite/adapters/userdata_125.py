from __future__ import annotations

import sqlite3


class Userdata125Adapter:
    """Validated adapter for the schema observed in the user's Phase 1 probe.

    Observed on 2026-08-16:
      version.userdata = 125
      version.globalSchema = 42
      schema fingerprint =
      7740b572c59e3caa976528b24edf074382add503730a5898aec732de9c8ecd10

    The adapter validates only the contract it actually uses. Optional Zotero tables
    (notes, annotations, full-text internals, feeds, etc.) are deliberately not part
    of this contract.
    """

    name = "userdata125-global42"
    observed_fingerprint = "7740b572c59e3caa976528b24edf074382add503730a5898aec732de9c8ecd10"

    required_columns: dict[str, set[str]] = {
        "items": {
            "itemID",
            "itemTypeID",
            "dateAdded",
            "dateModified",
            "clientDateModified",
            "libraryID",
            "key",
            "version",
            "synced",
        },
        "itemTypes": {"itemTypeID", "typeName"},
        "itemData": {"itemID", "fieldID", "valueID"},
        "itemDataValues": {"valueID", "value"},
        "fieldsCombined": {"fieldID", "fieldName"},
        "creators": {"creatorID", "firstName", "lastName", "fieldMode"},
        "itemCreators": {"itemID", "creatorID", "creatorTypeID", "orderIndex"},
        "creatorTypes": {"creatorTypeID", "creatorType"},
        "collections": {
            "collectionID",
            "collectionName",
            "parentCollectionID",
            "libraryID",
            "key",
        },
        "collectionItems": {"collectionID", "itemID", "orderIndex"},
        "tags": {"tagID", "name"},
        "itemTags": {"itemID", "tagID", "type"},
        "itemAttachments": {
            "itemID",
            "parentItemID",
            "linkMode",
            "contentType",
            "path",
            "syncState",
            "storageModTime",
            "storageHash",
        },
        "deletedItems": {"itemID"},
        "libraries": {
            "libraryID",
            "type",
            "editable",
            "filesEditable",
            "version",
            "storageVersion",
            "lastSync",
            "archived",
            "isAdmin",
        },
        "version": {"schema", "version"},
    }

    def validate(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
        ).fetchall()
        present = {str(row[0]) for row in rows}
        missing_tables = sorted(set(self.required_columns) - present)
        if missing_tables:
            raise RuntimeError(
                "Zotero schema contract mismatch; missing tables/views: "
                + ", ".join(missing_tables)
            )

        problems: list[str] = []
        for table, required in self.required_columns.items():
            columns = {
                str(row[1])
                for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()
            }
            missing = sorted(required - columns)
            if missing:
                problems.append(f"{table}: missing {', '.join(missing)}")

        if problems:
            raise RuntimeError(
                "Zotero schema contract mismatch; " + "; ".join(problems)
            )

    @staticmethod
    def bibliographic_items_sql(include_deleted: bool) -> str:
        deleted_filter = "" if include_deleted else "AND di.itemID IS NULL"
        return f"""
            SELECT
                i.itemID,
                i.libraryID,
                i.key,
                it.typeName AS itemType,
                i.version AS zoteroVersion,
                i.synced,
                i.dateAdded,
                i.dateModified,
                i.clientDateModified,
                CASE WHEN di.itemID IS NULL THEN 0 ELSE 1 END AS deleted
            FROM items AS i
            JOIN itemTypes AS it ON it.itemTypeID = i.itemTypeID
            LEFT JOIN deletedItems AS di ON di.itemID = i.itemID
            WHERE it.typeName NOT IN ('attachment', 'note', 'annotation')
              {deleted_filter}
            ORDER BY i.libraryID, i.itemID
        """

    fields_sql = """
        SELECT d.itemID, f.fieldName, v.value
        FROM itemData AS d
        JOIN itemDataValues AS v ON v.valueID = d.valueID
        JOIN fieldsCombined AS f ON f.fieldID = d.fieldID
        JOIN items AS i ON i.itemID = d.itemID
        JOIN itemTypes AS it ON it.itemTypeID = i.itemTypeID
        WHERE it.typeName NOT IN ('attachment', 'note', 'annotation')
        ORDER BY d.itemID, f.fieldName
    """

    creators_sql = """
        SELECT
            ic.itemID,
            ic.orderIndex,
            ic.creatorID,
            ct.creatorType,
            c.firstName,
            c.lastName,
            c.fieldMode
        FROM itemCreators AS ic
        JOIN creators AS c ON c.creatorID = ic.creatorID
        JOIN creatorTypes AS ct ON ct.creatorTypeID = ic.creatorTypeID
        JOIN items AS i ON i.itemID = ic.itemID
        JOIN itemTypes AS it ON it.itemTypeID = i.itemTypeID
        WHERE it.typeName NOT IN ('attachment', 'note', 'annotation')
        ORDER BY ic.itemID, ic.orderIndex
    """

    collections_sql = """
        SELECT
            ci.itemID,
            ci.orderIndex,
            c.collectionID,
            c.key AS collectionKey,
            c.collectionName,
            c.parentCollectionID,
            pc.key AS parentCollectionKey
        FROM collectionItems AS ci
        JOIN collections AS c ON c.collectionID = ci.collectionID
        LEFT JOIN collections AS pc ON pc.collectionID = c.parentCollectionID
        ORDER BY ci.itemID, ci.orderIndex, c.collectionID
    """

    # Complete collection catalog, intentionally independent of collectionItems.
    # Zotero userdata 125 exposes no collection sibling-order column, so runtime UI
    # ordering is a deterministic name.casefold()/key fallback.
    collection_catalog_sql = """
        SELECT
            c.libraryID,
            c.collectionID,
            c.key AS collectionKey,
            c.collectionName,
            c.parentCollectionID,
            pc.key AS parentCollectionKey,
            pc.collectionName AS parentCollectionName
        FROM collections AS c
        LEFT JOIN collections AS pc
          ON pc.collectionID = c.parentCollectionID
         AND pc.libraryID = c.libraryID
        ORDER BY c.libraryID, lower(c.collectionName), c.key
    """

    tags_sql = """
        SELECT it.itemID, it.type AS tagType, t.tagID, t.name
        FROM itemTags AS it
        JOIN tags AS t ON t.tagID = it.tagID
        ORDER BY it.itemID, lower(t.name), t.tagID
    """

    attachments_sql = """
        SELECT
            a.parentItemID,
            ai.itemID,
            ai.libraryID,
            ai.key,
            a.linkMode,
            a.contentType,
            a.path,
            a.syncState,
            a.storageModTime,
            a.storageHash
        FROM itemAttachments AS a
        JOIN items AS ai ON ai.itemID = a.itemID
        LEFT JOIN deletedItems AS adi ON adi.itemID = ai.itemID
        WHERE a.parentItemID IS NOT NULL
          AND adi.itemID IS NULL
        ORDER BY a.parentItemID, ai.itemID
    """

    deleted_attachments_sql = """
        SELECT COUNT(*)
        FROM itemAttachments AS a
        JOIN items AS ai ON ai.itemID = a.itemID
        JOIN deletedItems AS adi ON adi.itemID = ai.itemID
        WHERE a.parentItemID IS NOT NULL
    """

    libraries_sql = """
        SELECT libraryID, type, editable, filesEditable, version, storageVersion,
               lastSync, archived, isAdmin
        FROM libraries
        ORDER BY libraryID
    """
