"""Review queue database and prioritization layer for flagged ICMR STW units."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .priority import ReviewPriorityClassifier
from .schemas import (
    ReviewItemSchema,
    ReviewPriority,
    ReviewQueueSummary,
    ReviewReason,
    ReviewRiskCategory,
    ReviewStatus,
)

DEFAULT_DB_PATH = Path("data/knowledge/knowledge.db")


class ReviewQueue:
    """Manages the persistent human-review backlog in SQLite."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = db_path or DEFAULT_DB_PATH
        self._init_db()
        self.sync_from_knowledge_units()

    def _connect(self, allow_create: bool = False) -> sqlite3.Connection:
        if not self.db_path.exists() and not allow_create:
            raise FileNotFoundError(f"Knowledge database not found at {self.db_path.resolve()}")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Create knowledge_units, review_items and review_audit_log tables if they do not exist, and apply migrations."""
        with self._connect(allow_create=True) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS knowledge_units (
                    unit_id             TEXT PRIMARY KEY,
                    document_id         TEXT NOT NULL,
                    specialty           TEXT NOT NULL DEFAULT 'Cardiology',
                    condition           TEXT NOT NULL,
                    section             TEXT NOT NULL,
                    page_number         INTEGER NOT NULL,
                    entity_type         TEXT NOT NULL,
                    healthcare_tier     TEXT,
                    content             TEXT NOT NULL,
                    metadata_json       TEXT NOT NULL DEFAULT '{}',
                    review_status       TEXT NOT NULL DEFAULT 'extracted',
                    requires_manual_review INTEGER NOT NULL DEFAULT 0,
                    review_notes        TEXT,
                    version_id          TEXT NOT NULL DEFAULT 'v1.0',
                    source_reference_json TEXT NOT NULL DEFAULT '{}',
                    original_source_text TEXT NOT NULL DEFAULT '',
                    indexed_at          TEXT NOT NULL DEFAULT ''
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS review_items (
                    review_item_id TEXT PRIMARY KEY,
                    knowledge_unit_id TEXT NOT NULL UNIQUE,
                    document_id TEXT NOT NULL,
                    version_id TEXT NOT NULL DEFAULT 'v1.0',
                    specialty TEXT NOT NULL DEFAULT 'Cardiology',
                    condition TEXT NOT NULL,
                    page_number INTEGER NOT NULL,
                    section TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    original_source_text TEXT NOT NULL,
                    normalized_value TEXT,
                    corrected_structured_value TEXT,
                    correction_text TEXT,
                    review_reason TEXT NOT NULL,
                    rejection_reason TEXT,
                    review_priority TEXT NOT NULL,
                    risk_category TEXT NOT NULL DEFAULT 'STANDARD',
                    review_status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT,
                    review_notes TEXT,
                    reviewer_id TEXT,
                    reviewer_name TEXT,
                    reviewed_at TEXT,
                    approval_timestamp TEXT,
                    second_reviewer_id TEXT,
                    second_reviewer_name TEXT,
                    second_reviewed_at TEXT,
                    second_reviewer_notes TEXT,
                    requires_two_stage_approval INTEGER DEFAULT 0,
                    flowchart_context_json TEXT,
                    table_context_json TEXT,
                    source_reference_json TEXT
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS review_audit_log (
                    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    review_item_id TEXT NOT NULL,
                    knowledge_unit_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    old_status TEXT,
                    new_status TEXT,
                    reviewer_id TEXT NOT NULL,
                    reviewer_name TEXT,
                    notes TEXT,
                    corrected_value TEXT,
                    timestamp TEXT NOT NULL
                )
            """)

            # Apply incremental migrations for pre-existing tables
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(review_items)")
            item_cols = {row[1] for row in cursor.fetchall()}

            migrations = {
                "version_id": "TEXT NOT NULL DEFAULT 'v1.0'",
                "specialty": "TEXT NOT NULL DEFAULT 'Cardiology'",
                "normalized_value": "TEXT",
                "correction_text": "TEXT",
                "rejection_reason": "TEXT",
                "risk_category": "TEXT NOT NULL DEFAULT 'STANDARD'",
                "updated_at": "TEXT",
                "reviewer_name": "TEXT",
                "approval_timestamp": "TEXT",
                "second_reviewer_id": "TEXT",
                "second_reviewer_name": "TEXT",
                "second_reviewed_at": "TEXT",
                "second_reviewer_notes": "TEXT",
                "requires_two_stage_approval": "INTEGER DEFAULT 0",
                "flowchart_context_json": "TEXT",
                "table_context_json": "TEXT",
            }
            for col_name, col_type in migrations.items():
                if col_name not in item_cols:
                    conn.execute(f"ALTER TABLE review_items ADD COLUMN {col_name} {col_type}")

            cursor.execute("PRAGMA table_info(review_audit_log)")
            audit_cols = {row[1] for row in cursor.fetchall()}
            audit_migrations = {
                "old_status": "TEXT",
                "new_status": "TEXT",
                "reviewer_name": "TEXT",
            }
            for col_name, col_type in audit_migrations.items():
                if col_name not in audit_cols:
                    conn.execute(f"ALTER TABLE review_audit_log ADD COLUMN {col_name} {col_type}")

            # Normalize risk category for existing items while keeping two-stage approval clean
            conn.execute("""
                UPDATE review_items
                SET risk_category = CASE
                    WHEN review_priority = 'HIGH' THEN 'HIGH'
                    WHEN review_priority = 'MEDIUM' THEN 'MEDIUM'
                    ELSE 'LOW'
                END
                WHERE risk_category = 'STANDARD'
            """)

            conn.commit()

    @staticmethod
    def _determine_reason(entity_type: str, notes: Optional[str], content: str) -> ReviewReason:
        """Categorize clinical reason for flagging."""
        notes_lower = (notes or "").lower()
        content_lower = content.lower()

        if entity_type == "flowchart_node" or "flowchart" in notes_lower:
            return ReviewReason.FLOWCHART_AMBIGUITY
        elif entity_type == "table_row" or "table" in notes_lower:
            return ReviewReason.TABLE_EXTRACTION
        elif entity_type == "medication" and ("dose" in notes_lower or "none" in content_lower):
            return ReviewReason.INCOMPLETE_DOSAGE
        elif "ocr" in notes_lower or "extraction" in notes_lower:
            return ReviewReason.OCR_OR_EXTRACTION_ERROR
        elif "version" in notes_lower:
            return ReviewReason.VERSION_CONFLICT
        elif "ambiguity" in notes_lower:
            return ReviewReason.SOURCE_AMBIGUITY
        return ReviewReason.OTHER

    @staticmethod
    def _determine_priority(entity_type: str, section: str, content: str, notes: Optional[str] = None) -> ReviewPriority:
        """Assign clinical review priority using the ReviewPriorityClassifier."""
        return ReviewPriorityClassifier.classify(entity_type=entity_type, section=section, content=content, notes=notes)

    @staticmethod
    def _determine_risk_category(priority: ReviewPriority, entity_type: str, section: str, content: str) -> str:
        """Determine clinical risk category. High priority or critical clinical items become HIGH risk."""
        sec_lower = section.lower()
        cnt_lower = content.lower()
        is_critical = (
            priority == ReviewPriority.HIGH
            or entity_type in ["medication", "contraindication"]
            or any(w in sec_lower or w in cnt_lower for w in [
                "thrombolysis", "dosage", "contraindication", "emergency", "pediatric", "shock", "arrest", "fibrinolysis"
            ])
        )
        if is_critical:
            return ReviewRiskCategory.HIGH.value
        elif priority == ReviewPriority.MEDIUM:
            return ReviewRiskCategory.MEDIUM.value
        return ReviewRiskCategory.LOW.value

    def sync_from_knowledge_units(self) -> int:
        """Populate review_items from knowledge_units flagged with requires_manual_review = 1."""
        now = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        synced_count = 0

        with self._connect(allow_create=True) as conn:
            cursor = conn.cursor()
            table_check = cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='knowledge_units'").fetchone()
            if not table_check:
                return 0

            rows = cursor.execute("""
                SELECT unit_id, document_id, version_id, specialty, condition, page_number, section,
                       entity_type, content, review_notes, source_reference_json
                FROM knowledge_units
                WHERE requires_manual_review = 1
            """).fetchall()

            for r in rows:
                uid = r["unit_id"]
                existing = cursor.execute("SELECT review_item_id FROM review_items WHERE knowledge_unit_id = ?", (uid,)).fetchone()
                if existing:
                    continue

                reason = self._determine_reason(r["entity_type"], r["review_notes"], r["content"])
                priority = self._determine_priority(r["entity_type"], r["section"], r["content"], r["review_notes"])
                risk = self._determine_risk_category(priority, r["entity_type"], r["section"], r["content"])
                requires_two_stage = 1 if risk == ReviewRiskCategory.HIGH.value else 0

                sr = json.loads(r["source_reference_json"]) if r["source_reference_json"] else {}
                orig_text = sr.get("source_text_reference", r["content"])
                specialty_val = r["specialty"] if "specialty" in r.keys() else "Cardiology"
                ver_val = r["version_id"] if "version_id" in r.keys() and r["version_id"] else "v1.0"

                flowchart_ctx = None
                table_ctx = None
                if r["entity_type"] == "flowchart_node":
                    flowchart_ctx = json.dumps({
                        "node_id": sr.get("node_id", uid),
                        "preceding_nodes": sr.get("preceding_nodes", []),
                        "next_nodes": sr.get("next_nodes", []),
                        "decision_criterion": sr.get("decision_criterion"),
                        "action": r["content"],
                        "flags": ["REQUIRES_HUMAN_VERIFICATION"],
                    })
                elif r["entity_type"] == "table_row":
                    table_ctx = json.dumps({
                        "row_index": sr.get("row_index", 0),
                        "columns": sr.get("columns", []),
                        "raw_row": r["content"],
                        "flags": ["CHECK_CELL_ALIGNMENT"],
                    })

                cursor.execute("""
                    INSERT INTO review_items (
                        review_item_id, knowledge_unit_id, document_id, version_id, specialty, condition,
                        page_number, section, entity_type, content, original_source_text,
                        corrected_structured_value, review_reason, review_priority, risk_category,
                        review_status, created_at, updated_at, review_notes, reviewer_id,
                        reviewed_at, requires_two_stage_approval, flowchart_context_json,
                        table_context_json, source_reference_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    f"REV-{uid}",
                    uid,
                    r["document_id"],
                    ver_val,
                    specialty_val,
                    r["condition"],
                    r["page_number"],
                    r["section"],
                    r["entity_type"],
                    r["content"],
                    orig_text,
                    None,
                    reason.value,
                    priority.value,
                    risk,
                    ReviewStatus.NEEDS_REVIEW.value,
                    now,
                    now,
                    r["review_notes"],
                    None,
                    None,
                    requires_two_stage,
                    flowchart_ctx,
                    table_ctx,
                    r["source_reference_json"],
                ))
                synced_count += 1
            conn.commit()

        return synced_count

    def get_review_items(
        self,
        status: Optional[Union[ReviewStatus, str]] = None,
        priority: Optional[Union[ReviewPriority, str]] = None,
        risk_category: Optional[str] = None,
        reason: Optional[Union[ReviewReason, str]] = None,
        specialty: Optional[str] = None,
        condition: Optional[str] = None,
        document_id: Optional[str] = None,
        version_id: Optional[str] = None,
        entity_type: Optional[str] = None,
        reviewer_id: Optional[str] = None,
        search: Optional[str] = None,
        sort_by: str = "priority",
        sort_order: str = "asc",
        limit: int = 50,
        offset: int = 0,
    ) -> List[ReviewItemSchema]:
        """Fetch filtered, searched, and sorted review items."""
        clauses = []
        params: List[Any] = []

        if status:
            st_val = status.value if isinstance(status, ReviewStatus) else str(status)
            if st_val in ["PENDING", "NEEDS_REVIEW"]:
                clauses.append("review_status IN ('PENDING', 'NEEDS_REVIEW')")
            else:
                clauses.append("review_status = ?")
                params.append(st_val)

        if priority:
            pr_val = priority.value if isinstance(priority, ReviewPriority) else str(priority)
            clauses.append("review_priority = ?")
            params.append(pr_val)

        if risk_category:
            clauses.append("risk_category = ?")
            params.append(risk_category)

        if reason:
            rs_val = reason.value if isinstance(reason, ReviewReason) else str(reason)
            clauses.append("review_reason = ?")
            params.append(rs_val)

        if specialty:
            clauses.append("specialty = ?")
            params.append(specialty)

        if condition:
            clauses.append("condition LIKE ?")
            params.append(f"%{condition}%")

        if document_id:
            clauses.append("document_id = ?")
            params.append(document_id)

        if version_id:
            clauses.append("version_id = ?")
            params.append(version_id)

        if entity_type:
            clauses.append("entity_type = ?")
            params.append(entity_type)

        if reviewer_id:
            clauses.append("(reviewer_id = ? OR second_reviewer_id = ?)")
            params.extend([reviewer_id, reviewer_id])

        if search:
            search_clause = """
                (condition LIKE ? OR content LIKE ? OR original_source_text LIKE ?
                 OR document_id LIKE ? OR section LIKE ?)
            """
            s_param = f"%{search.strip()}%"
            clauses.append(search_clause)
            params.extend([s_param, s_param, s_param, s_param, s_param])

        where_str = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        # Determine sorting SQL
        order_dir = "DESC" if sort_order.lower() == "desc" else "ASC"
        if sort_by == "risk":
            order_clause = f"""
                CASE risk_category
                    WHEN 'HIGH' THEN 1
                    WHEN 'MEDIUM' THEN 2
                    WHEN 'LOW' THEN 3
                    ELSE 4
                END {order_dir}, created_at ASC
            """
        elif sort_by == "priority":
            order_clause = f"""
                CASE review_priority
                    WHEN 'HIGH' THEN 1
                    WHEN 'MEDIUM' THEN 2
                    WHEN 'LOW' THEN 3
                    ELSE 4
                END {order_dir}, document_id, page_number
            """
        elif sort_by in ["oldest", "date"]:
            order_clause = f"created_at {order_dir}"
        elif sort_by == "specialty":
            order_clause = f"specialty {order_dir}, document_id, page_number"
        elif sort_by == "document":
            order_clause = f"document_id {order_dir}, page_number"
        elif sort_by == "page":
            order_clause = f"page_number {order_dir}"
        elif sort_by == "status":
            order_clause = f"review_status {order_dir}, created_at ASC"
        else:
            order_clause = f"""
                CASE review_priority
                    WHEN 'HIGH' THEN 1
                    WHEN 'MEDIUM' THEN 2
                    WHEN 'LOW' THEN 3
                    ELSE 4
                END ASC, document_id, page_number
            """

        query = f"""
            SELECT * FROM review_items
            {where_str}
            ORDER BY {order_clause}
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()

        return [self._row_to_schema(r) for r in rows]

    def get_item_by_id(self, item_id: str) -> Optional[ReviewItemSchema]:
        """Fetch single review item by review_item_id or knowledge_unit_id."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM review_items WHERE review_item_id = ? OR knowledge_unit_id = ?",
                (item_id, item_id),
            ).fetchone()
            if not row:
                return None
            return self._row_to_schema(row)

    def get_item(self, item_id: str) -> Optional[ReviewItemSchema]:
        """Alias for get_item_by_id."""
        return self.get_item_by_id(item_id)

    def upsert_review_item(
        self,
        unit_id: str,
        document_id: str,
        condition: str,
        section: str,
        page_number: int,
        entity_type: str,
        content: str,
        original_source_text: str,
        review_reason: Union[ReviewReason, str],
        review_priority: Union[ReviewPriority, str] = ReviewPriority.MEDIUM,
        risk_category: Union[ReviewRiskCategory, str] = ReviewRiskCategory.STANDARD,
        specialty: str = "Cardiology",
        version_id: str = "v1.0",
        requires_two_stage_approval: bool = False,
        review_status: Union[ReviewStatus, str] = ReviewStatus.PENDING,
        reviewer_id: Optional[str] = None,
        review_notes: Optional[str] = None,
        flowchart_context: Optional[str] = None,
        table_context: Optional[str] = None,
    ) -> ReviewItemSchema:
        """Insert or update a unit in review queue, supporting programmatic ingestion and tests."""
        now = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        reason_val = review_reason.value if hasattr(review_reason, "value") else str(review_reason)
        priority_val = review_priority.value if hasattr(review_priority, "value") else str(review_priority)
        risk_val = risk_category.value if hasattr(risk_category, "value") else str(risk_category)
        status_val = review_status.value if hasattr(review_status, "value") else str(review_status)

        with self._connect(allow_create=True) as conn:
            table_check = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='knowledge_units'").fetchone()
            if table_check:
                unit_exists = conn.execute("SELECT unit_id FROM knowledge_units WHERE unit_id = ?", (unit_id,)).fetchone()
                if not unit_exists:
                    conn.execute("""
                        INSERT INTO knowledge_units (
                            unit_id, document_id, specialty, condition, section, page_number,
                            entity_type, content, original_source_text, requires_manual_review
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                    """, (unit_id, document_id, specialty, condition, section, page_number, entity_type, content, original_source_text))

            cursor = conn.cursor()
            existing = cursor.execute("SELECT review_item_id FROM review_items WHERE review_item_id = ? OR knowledge_unit_id = ?", (unit_id, unit_id)).fetchone()
            rev_item_id = existing[0] if existing else unit_id

            fc_json = flowchart_context if (flowchart_context is None or isinstance(flowchart_context, str)) else json.dumps(flowchart_context)
            tc_json = table_context if (table_context is None or isinstance(table_context, str)) else json.dumps(table_context)

            cursor.execute("""
                INSERT INTO review_items (
                    review_item_id, knowledge_unit_id, document_id, specialty, condition,
                    section, page_number, entity_type, content, original_source_text,
                    review_reason, review_priority, risk_category, review_status,
                    requires_two_stage_approval, reviewer_id, review_notes,
                    flowchart_context_json, table_context_json, version_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(review_item_id) DO UPDATE SET
                    review_reason = excluded.review_reason,
                    review_priority = excluded.review_priority,
                    risk_category = excluded.risk_category,
                    review_status = excluded.review_status,
                    requires_two_stage_approval = excluded.requires_two_stage_approval,
                    reviewer_id = excluded.reviewer_id,
                    review_notes = excluded.review_notes,
                    updated_at = excluded.updated_at
            """, (
                rev_item_id, unit_id, document_id, specialty, condition,
                section, page_number, entity_type, content, original_source_text,
                reason_val, priority_val, risk_val, status_val,
                1 if requires_two_stage_approval else 0, reviewer_id, review_notes,
                fc_json, tc_json, version_id, now, now
            ))
            conn.commit()

        item = self.get_item_by_id(rev_item_id)
        assert item is not None
        return item

    def _row_to_schema(self, r: sqlite3.Row) -> ReviewItemSchema:
        sr = json.loads(r["source_reference_json"]) if r["source_reference_json"] else {}
        fc = json.loads(r["flowchart_context_json"]) if "flowchart_context_json" in r.keys() and r["flowchart_context_json"] else None
        tc = json.loads(r["table_context_json"]) if "table_context_json" in r.keys() and r["table_context_json"] else None
        spec = r["specialty"] if "specialty" in r.keys() else "Cardiology"
        ver = r["version_id"] if "version_id" in r.keys() and r["version_id"] else "v1.0"
        risk = r["risk_category"] if "risk_category" in r.keys() and r["risk_category"] else "STANDARD"
        two_stage = bool(r["requires_two_stage_approval"]) if "requires_two_stage_approval" in r.keys() else False

        raw_status = r["review_status"]
        try:
            status_enum = ReviewStatus(raw_status)
        except ValueError:
            status_enum = ReviewStatus.PENDING

        return ReviewItemSchema(
            review_item_id=r["review_item_id"],
            knowledge_unit_id=r["knowledge_unit_id"],
            document_id=r["document_id"],
            version_id=ver,
            specialty=spec,
            condition=r["condition"],
            page_number=r["page_number"],
            section=r["section"],
            entity_type=r["entity_type"],
            content=r["content"],
            original_source_text=r["original_source_text"],
            normalized_value=r["normalized_value"] if "normalized_value" in r.keys() else None,
            corrected_structured_value=r["corrected_structured_value"],
            correction_text=r["correction_text"] if "correction_text" in r.keys() else r["corrected_structured_value"],
            review_reason=ReviewReason(r["review_reason"]),
            rejection_reason=r["rejection_reason"] if "rejection_reason" in r.keys() else None,
            review_priority=ReviewPriority(r["review_priority"]),
            risk_category=risk,
            review_status=status_enum,
            created_at=r["created_at"],
            updated_at=r["updated_at"] if "updated_at" in r.keys() else r["created_at"],
            review_notes=r["review_notes"],
            reviewer_id=r["reviewer_id"],
            reviewer_name=r["reviewer_name"] if "reviewer_name" in r.keys() else None,
            reviewed_at=r["reviewed_at"],
            approval_timestamp=r["approval_timestamp"] if "approval_timestamp" in r.keys() else None,
            second_reviewer_id=r["second_reviewer_id"] if "second_reviewer_id" in r.keys() else None,
            second_reviewer_name=r["second_reviewer_name"] if "second_reviewer_name" in r.keys() else None,
            second_reviewed_at=r["second_reviewed_at"] if "second_reviewed_at" in r.keys() else None,
            second_reviewer_notes=r["second_reviewer_notes"] if "second_reviewer_notes" in r.keys() else None,
            requires_two_stage_approval=two_stage,
            flowchart_context=fc,
            table_context=tc,
            source_reference=sr,
        )

    def get_summary(self) -> ReviewQueueSummary:
        """Calculate review queue dashboard summary statistics across all lifecycle states."""
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM review_items").fetchone()[0]
            pending = conn.execute("SELECT COUNT(*) FROM review_items WHERE review_status IN ('PENDING', 'NEEDS_REVIEW')").fetchone()[0]
            in_review = conn.execute("SELECT COUNT(*) FROM review_items WHERE review_status = 'IN_REVIEW'").fetchone()[0]
            approved = conn.execute("SELECT COUNT(*) FROM review_items WHERE review_status = 'APPROVED'").fetchone()[0]
            eligible = conn.execute("SELECT COUNT(*) FROM review_items WHERE review_status = 'ELIGIBLE_FOR_PRODUCTION'").fetchone()[0]
            promoted = conn.execute("SELECT COUNT(*) FROM review_items WHERE review_status IN ('PROMOTED', 'PRODUCTION_INDEX')").fetchone()[0]
            rejected = conn.execute("SELECT COUNT(*) FROM review_items WHERE review_status = 'REJECTED'").fetchone()[0]
            needs_corr = conn.execute("SELECT COUNT(*) FROM review_items WHERE review_status = 'NEEDS_CORRECTION'").fetchone()[0]

            high_p = conn.execute("SELECT COUNT(*) FROM review_items WHERE review_priority = 'HIGH' AND review_status IN ('PENDING', 'NEEDS_REVIEW', 'IN_REVIEW')").fetchone()[0]
            med_p = conn.execute("SELECT COUNT(*) FROM review_items WHERE review_priority = 'MEDIUM' AND review_status IN ('PENDING', 'NEEDS_REVIEW', 'IN_REVIEW')").fetchone()[0]
            low_p = conn.execute("SELECT COUNT(*) FROM review_items WHERE review_priority = 'LOW' AND review_status IN ('PENDING', 'NEEDS_REVIEW', 'IN_REVIEW')").fetchone()[0]

            docs_rows = conn.execute("SELECT document_id, COUNT(*) as c FROM review_items GROUP BY document_id").fetchall()
            reasons_rows = conn.execute("SELECT review_reason, COUNT(*) as c FROM review_items GROUP BY review_reason").fetchall()
            specialty_rows = conn.execute("SELECT specialty, COUNT(*) as c FROM review_items GROUP BY specialty").fetchall()
            risk_rows = conn.execute("SELECT risk_category, COUNT(*) as c FROM review_items GROUP BY risk_category").fetchall()
            priority_rows = conn.execute("SELECT review_priority, COUNT(*) as c FROM review_items GROUP BY review_priority").fetchall()

        return ReviewQueueSummary(
            total_items=total,
            pending=pending,
            in_review=in_review,
            approved=approved,
            eligible_for_production=eligible,
            promoted=promoted,
            rejected=rejected,
            needs_correction=needs_corr,
            high_priority_pending=high_p,
            medium_priority_pending=med_p,
            low_priority_pending=low_p,
            by_document={r["document_id"]: r["c"] for r in docs_rows},
            by_reason={r["review_reason"]: r["c"] for r in reasons_rows},
            by_specialty={r["specialty"]: r["c"] for r in specialty_rows},
            by_risk={r["risk_category"]: r["c"] for r in risk_rows},
            by_priority={r["review_priority"]: r["c"] for r in priority_rows},
        )

