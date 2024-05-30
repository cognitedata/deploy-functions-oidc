from __future__ import annotations


class AnnotationConfig:
    debug: bool = False
    run_all: bool = False
    doc_limit: int = -1
    doc_type_meta_col: str = "application/pdf"
    pnid_doc_type: str = "pdf"
    match_threshold: float = 0.9

    def __init__(self, function_input: dict):
        self.assets_data_set_external_id = function_input["assets_data_set_external_id"]
        self.files_data_set_external_id = function_input["files_data_set_external_id"]
        self.batch_size = function_input["batch_size"]
