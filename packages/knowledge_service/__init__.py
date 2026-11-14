"""知识服务（B 子系统 PoC）：只读适配现有索引并产出 knowledge-card。

对外稳定接口：`KnowledgeService.probe()` / `.search()` / `.retrieve()`。
"""
from __future__ import annotations

from .adapter import (
    AdapterError,
    INDEX_DB_NAME,
    LANE_CATEGORIES,
    ProbeResult,
    list_candidates,
    list_scan_files,
    probe,
    query_terms,
)
from .evidence import EVIDENCE_EXTENSIONS, EvidenceError, scan_file
from .service import (
    FALLBACK_MAX_FILE_BYTES,
    FALLBACK_MAX_FILES,
    SCOPE_BY_STAGE,
    KnowledgeService,
    KnowledgeServiceError,
    discover_kb_root,
)

__all__ = [
    "AdapterError",
    "EVIDENCE_EXTENSIONS",
    "EvidenceError",
    "FALLBACK_MAX_FILE_BYTES",
    "FALLBACK_MAX_FILES",
    "INDEX_DB_NAME",
    "KnowledgeService",
    "KnowledgeServiceError",
    "LANE_CATEGORIES",
    "ProbeResult",
    "SCOPE_BY_STAGE",
    "discover_kb_root",
    "list_candidates",
    "list_scan_files",
    "probe",
    "query_terms",
    "scan_file",
]
