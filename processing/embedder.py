from __future__ import annotations

from pathlib import Path
from typing import Iterable

import numpy as np
try:
    import torch
    from dotenv import load_dotenv
    from sentence_transformers import SentenceTransformer
    from transformers import modeling_utils
    from transformers.utils import loading_report
except ImportError as exc:
    raise ImportError(
        "Embedding dependencies are missing. Install dependencies with "
        "`pip install -r requirements.txt`."
    ) from exc


def _is_only_known_minilm_warning(loading_info: object) -> bool:
    unexpected_keys = getattr(loading_info, "unexpected_keys", set())
    missing_keys = getattr(loading_info, "missing_keys", set())
    mismatched_keys = getattr(loading_info, "mismatched_keys", set())
    error_msgs = getattr(loading_info, "error_msgs", [])
    conversion_errors = getattr(loading_info, "conversion_errors", {})
    return (
        unexpected_keys == {"embeddings.position_ids"}
        and not missing_keys
        and not mismatched_keys
        and not error_msgs
        and not conversion_errors
    )


class TextEmbedder:
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> None:
        load_dotenv(Path(__file__).resolve().parent.parent / ".env")
        self.model_name = model_name
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        original_modeling_utils_report = modeling_utils.log_state_dict_report
        original_loading_report = loading_report.log_state_dict_report

        def patched_log_state_dict_report(
            model,
            pretrained_model_name_or_path: str,
            ignore_mismatched_sizes: bool,
            loading_info,
            logger=None,
        ) -> None:
            if _is_only_known_minilm_warning(loading_info):
                return
            original_loading_report(
                model,
                pretrained_model_name_or_path,
                ignore_mismatched_sizes,
                loading_info,
                logger=logger,
            )

        modeling_utils.log_state_dict_report = patched_log_state_dict_report
        loading_report.log_state_dict_report = patched_log_state_dict_report
        try:
            self.model = SentenceTransformer(model_name, device=self.device)
        finally:
            modeling_utils.log_state_dict_report = original_modeling_utils_report
            loading_report.log_state_dict_report = original_loading_report

    def get_embedding_dimension(self) -> int:
        return int(self.model.get_embedding_dimension())

    def embed_texts(self, texts: Iterable[str], batch_size: int = 32) -> np.ndarray:
        text_list = list(texts)
        if not text_list:
            return np.empty((0, self.get_embedding_dimension()), dtype=np.float32)

        embeddings = self.model.encode(
            text_list,
            batch_size=batch_size,
            convert_to_numpy=True,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        return embeddings.astype(np.float32)
