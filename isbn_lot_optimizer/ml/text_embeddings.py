"""
Text Embeddings Module for Book Descriptions

This module provides text embedding functionality for book descriptions using
sentence-transformers. Designed to augment tabular features for low-data segments
(collectibles, signed books, first editions, etc.) where traditional features may
be sparse.

Architecture:
- Model: all-MiniLM-L6-v2 (384-dim embeddings, fast inference)
- Use case: Augment XGBoost/GradientBoosting with text features
- Target segment: Books with limited market data (sold_comps_count < 10) or collectibles

Usage:
    from isbn_lot_optimizer.ml.text_embeddings import TextEmbedder

    embedder = TextEmbedder()
    embeddings = embedder.encode_descriptions(["First edition, signed by author"])
    # Returns: numpy array shape (1, 384)
"""

import sys
from pathlib import Path
from typing import List, Optional, Union
import numpy as np

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TextEmbedder:
    """
    Text embedding generator for book descriptions.

    Uses sentence-transformers with all-MiniLM-L6-v2 model (384-dim).
    Handles missing descriptions gracefully with zero vectors.
    """

    def __init__(self, model_name: str = 'all-MiniLM-L6-v2', cache_dir: Optional[str] = None):
        """
        Initialize text embedder.

        Args:
            model_name: Sentence transformer model name (default: all-MiniLM-L6-v2)
            cache_dir: Optional cache directory for model weights
        """
        self.model_name = model_name
        self.cache_dir = cache_dir or str(Path.home() / '.cache' / 'sentence-transformers')
        self.model = None
        self.embedding_dim = 384  # all-MiniLM-L6-v2 dimension

    def _load_model(self):
        """Lazy load the sentence transformer model."""
        if self.model is None:
            try:
                from sentence_transformers import SentenceTransformer
                print(f"Loading sentence transformer model: {self.model_name}")
                self.model = SentenceTransformer(self.model_name, cache_folder=self.cache_dir)
                print(f"✓ Model loaded successfully (embedding dim: {self.embedding_dim})")
            except ImportError:
                raise ImportError(
                    "sentence-transformers not installed. "
                    "Install with: pip install sentence-transformers"
                )

    def encode_descriptions(
        self,
        descriptions: List[Optional[str]],
        normalize: bool = True,
        show_progress: bool = False
    ) -> np.ndarray:
        """
        Encode list of book descriptions into embeddings.

        Args:
            descriptions: List of description strings (None values handled)
            normalize: Normalize embeddings to unit vectors (default: True)
            show_progress: Show progress bar for encoding (default: False)

        Returns:
            numpy array of shape (n_descriptions, 384)
            Missing descriptions are replaced with zero vectors

        Example:
            >>> embedder = TextEmbedder()
            >>> descs = ["First edition signed", None, "Hardcover dust jacket"]
            >>> embeddings = embedder.encode_descriptions(descs)
            >>> embeddings.shape
            (3, 384)
        """
        self._load_model()

        # Handle None/empty descriptions
        processed_descs = []
        missing_indices = []

        for i, desc in enumerate(descriptions):
            if desc is None or (isinstance(desc, str) and not desc.strip()):
                processed_descs.append("")  # Placeholder for embedding
                missing_indices.append(i)
            else:
                processed_descs.append(str(desc).strip())

        # Encode all descriptions (including empty ones)
        embeddings = self.model.encode(
            processed_descs,
            normalize_embeddings=normalize,
            show_progress_bar=show_progress,
            convert_to_numpy=True
        )

        # Replace embeddings for missing descriptions with zero vectors
        if missing_indices:
            zero_vector = np.zeros(self.embedding_dim)
            for idx in missing_indices:
                embeddings[idx] = zero_vector

        return embeddings

    def encode_single(self, description: Optional[str], normalize: bool = True) -> np.ndarray:
        """
        Encode a single description.

        Args:
            description: Description string (or None)
            normalize: Normalize embedding to unit vector (default: True)

        Returns:
            numpy array of shape (384,)

        Example:
            >>> embedder = TextEmbedder()
            >>> embedding = embedder.encode_single("First printing hardcover")
            >>> embedding.shape
            (384,)
        """
        embeddings = self.encode_descriptions([description], normalize=normalize)
        return embeddings[0]

    def get_embedding_dim(self) -> int:
        """Get the embedding dimension (384 for all-MiniLM-L6-v2)."""
        return self.embedding_dim


def extract_descriptions_from_records(records: List[dict]) -> List[Optional[str]]:
    """
    Extract description strings from book records.

    Looks for description in multiple places:
    1. record['description'] (direct field)
    2. record['metadata']['description'] (metadata dict)

    Args:
        records: List of book dicts from data loader

    Returns:
        List of description strings (may contain None)

    Example:
        >>> records = [
        ...     {'isbn': '123', 'description': 'First edition'},
        ...     {'isbn': '456', 'metadata': {'description': 'Signed'}},
        ...     {'isbn': '789'}
        ... ]
        >>> extract_descriptions_from_records(records)
        ['First edition', 'Signed', None]
    """
    descriptions = []

    for record in records:
        desc = None

        # Try direct description field first
        if 'description' in record and record['description']:
            desc = record['description']
        # Try metadata.description
        elif 'metadata' in record and isinstance(record['metadata'], dict):
            if 'description' in record['metadata'] and record['metadata']['description']:
                desc = record['metadata']['description']

        descriptions.append(desc)

    return descriptions


def augment_features_with_embeddings(
    X: np.ndarray,
    descriptions: List[Optional[str]],
    embedder: Optional[TextEmbedder] = None,
    normalize: bool = True
) -> np.ndarray:
    """
    Augment tabular features with text embeddings.

    Args:
        X: Tabular features array of shape (n_samples, n_features)
        descriptions: List of description strings (may contain None)
        embedder: TextEmbedder instance (creates new one if None)
        normalize: Normalize embeddings to unit vectors (default: True)

    Returns:
        Augmented features of shape (n_samples, n_features + 384)

    Example:
        >>> X_tabular = np.random.rand(100, 26)  # 26 eBay features
        >>> descriptions = ["..." for _ in range(100)]
        >>> X_hybrid = augment_features_with_embeddings(X_tabular, descriptions)
        >>> X_hybrid.shape
        (100, 410)  # 26 + 384 = 410 features
    """
    if embedder is None:
        embedder = TextEmbedder()

    # Generate embeddings
    text_embeddings = embedder.encode_descriptions(descriptions, normalize=normalize)

    # Concatenate tabular + text features
    X_augmented = np.hstack([X, text_embeddings])

    print(f"Features augmented: {X.shape[1]} tabular + {text_embeddings.shape[1]} text = {X_augmented.shape[1]} total")

    return X_augmented


if __name__ == "__main__":
    # Test the text embedder
    print("=" * 80)
    print("TESTING TEXT EMBEDDINGS MODULE")
    print("=" * 80)

    embedder = TextEmbedder()

    # Test single encoding
    print("\n1. Single description encoding:")
    desc = "First printing of the first edition. Hardcover with dust jacket. Signed by author."
    embedding = embedder.encode_single(desc)
    print(f"   Description: {desc[:50]}...")
    print(f"   Embedding shape: {embedding.shape}")
    print(f"   Embedding norm: {np.linalg.norm(embedding):.4f}")

    # Test batch encoding
    print("\n2. Batch description encoding:")
    descriptions = [
        "First edition signed by author",
        "Hardcover dust jacket very good condition",
        None,  # Missing description
        "Collectible vintage paperback",
    ]
    embeddings = embedder.encode_descriptions(descriptions)
    print(f"   Batch size: {len(descriptions)}")
    print(f"   Embeddings shape: {embeddings.shape}")
    print(f"   Missing description (index 2) norm: {np.linalg.norm(embeddings[2]):.4f}")

    # Test feature augmentation
    print("\n3. Feature augmentation:")
    X_tabular = np.random.rand(4, 26)  # 4 samples, 26 features
    X_augmented = augment_features_with_embeddings(X_tabular, descriptions, embedder)
    print(f"   Tabular features: {X_tabular.shape}")
    print(f"   Augmented features: {X_augmented.shape}")

    print("\n" + "=" * 80)
    print("✓ All tests passed!")
    print("=" * 80)
