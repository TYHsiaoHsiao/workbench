"""知识服务（B 子系统 PoC）：只读适配现有索引并产出 knowledge-card。

对外稳定接口：`KnowledgeService.probe()` / `.search()` / `.retrieve()`；
M22 起可经 :func:`search_index_card` 使用按契约重建的本地索引（index/）。
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
from .index_builder import (
    INDEX_DIR_NAME,
    INDEX_SCHEMA,
    KnowledgeIndexError,
    build_index,
    default_index_dir,
    index_info,
    index_ready,
    read_meta,
    search_index,
    split_chunks,
    verify_index,
)
from .index_service import KnowledgeIndexServiceError, search_index_card
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
    "INDEX_DIR_NAME",
    "INDEX_SCHEMA",
    "KnowledgeIndexError",
    "KnowledgeIndexServiceError",
    "KnowledgeService",
    "KnowledgeServiceError",
    "LANE_CATEGORIES",
    "ProbeResult",
    "SCOPE_BY_STAGE",
    "build_index",
    "default_index_dir",
    "discover_kb_root",
    "index_info",
    "index_ready",
    "list_candidates",
    "list_scan_files",
    "probe",
    "query_terms",
    "read_meta",
    "scan_file",
    "search_index",
    "search_index_card",
    "split_chunks",
    "verify_index",
]
