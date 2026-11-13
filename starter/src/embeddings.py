"""Local EmbeddingGemma 2 through sentence-transformers. Real vectors only: any failure
raises; there is no mock or random fallback."""
from . import config


class MyEmbedder:
    def __init__(self, model_name: str = config.MODEL_NAME) -> None:
        import torch
        from sentence_transformers import SentenceTransformer

        if not config.MODEL_PATH.exists():
            raise FileNotFoundError(f"embedding model not found at {config.MODEL_PATH}")
        self.model_name = model_name
        self.device = "mps" if torch.backends.mps.is_available() else "cpu"   # recorded in logs
        self.model = SentenceTransformer(str(config.MODEL_PATH), device=self.device)
        self.model.max_seq_length = config.MAX_SEQ_LENGTH
        self.dimensions = self.model.get_sentence_embedding_dimension()
        if self.dimensions != config.DIMENSIONS:
            raise RuntimeError(f"model dim {self.dimensions} != configured {config.DIMENSIONS}")

    def token_counts(self, texts: list[str]) -> list[int]:
        tok = self.model.tokenizer
        return [len(ids) for ids in tok(texts, add_special_tokens=True)["input_ids"]]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.model.encode(texts, prompt=config.DOC_PROMPT, normalize_embeddings=True,
                                 batch_size=config.BATCH_SIZE, show_progress_bar=False).tolist()

    def embed_query(self, question: str) -> list[float]:
        return self.model.encode([question], prompt=config.QUERY_PROMPT, normalize_embeddings=True,
                                 show_progress_bar=False)[0].tolist()
