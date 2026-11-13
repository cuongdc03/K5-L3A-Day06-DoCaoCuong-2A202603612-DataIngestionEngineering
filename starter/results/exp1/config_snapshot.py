"""Single place for every parameter that must stay identical across strategies.

Changing any value here after looking at benchmark results is a protocol change and
must be written in the experiment log.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # repository root
STARTER = ROOT / "starter"
MANIFEST = ROOT / "data" / "manifest.json"
PDF = ROOT / "data" / "raw" / "introduction-intellectual-property.pdf"
BENCHMARK = ROOT / "data" / "benchmark.json"
RESULTS = STARTER / "results"

SOURCE_NAME = "introduction-intellectual-property.pdf"
DOCUMENT_ID = "openstax-intro-ip"

# Embedding (same for all strategies). Local model, no API cost.
MODEL_PATH = STARTER / "models" / "google" / "embeddinggemma-2"
MODEL_NAME = "google/embeddinggemma-2 (local, sentence-transformers)"
DIMENSIONS = 768
DOC_PROMPT = "title: none | text: "                 # from config_sentence_transformers.json
QUERY_PROMPT = "task: search result | query: "      # idem
MAX_SEQ_LENGTH = 512
BATCH_SIZE = 16

# Chunking. Fixed before running any benchmark question.
STRATEGIES = {
    "A": {"chunker": "fixed_size", "size": 500, "overlap": 50, "filter": False},
    "B": {"chunker": "by_paragraph", "max_size": 1200, "filter": False},
    # C re-uses the chunks/vectors of B and only adds the metadata filter at query time.
    "C": {"chunker": "by_paragraph", "max_size": 1200, "filter": True, "index_of": "B"},
}
TOP_K = 3
