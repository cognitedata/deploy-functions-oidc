from __future__ import annotations


class AnnotationConfig:
    debug: bool = False
    run_all: bool = False
    doc_limit: int = -1
    doc_type_meta_col: str = "application/pdf"
    pnid_doc_type: str = "pdf"
    asset_root_xids: list[str] = "0"
    match_threshold: float = 0.9
