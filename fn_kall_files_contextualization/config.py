from __future__ import annotations


class AnnotationConfig:
    debug: bool = False
    run_all: bool = False
    doc_limit: int = -1
    doc_type_meta_col: str = "application/pdf"
    pnid_doc_type: str = "pdf"
    assets_data_set_external_id = "src:kall:assets"
    files_data_set_external_id = "src:kall:limber"
    match_threshold: float = 0.9
