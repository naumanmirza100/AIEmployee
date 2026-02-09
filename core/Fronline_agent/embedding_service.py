"""
Embedding Service for Frontline Agent
Handles generation and storage of document embeddings for semantic search
"""
import logging
import os
from typing import List, Optional, Dict
from django.conf import settings

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

logger = logging.getLogger(__name__)

if not NUMPY_AVAILABLE:
    logger.warning("NumPy not available. Cosine similarity will use basic implementation.")


class EmbeddingService:
    """
    Service for generating and managing embeddings for semantic search.
    Uses OpenAI embeddings API.
    """
    
    def __init__(self):
        """Initialize embedding service with OpenAI client"""
        try:
            from openai import OpenAI
            self.openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
            self.embedding_model = getattr(settings, 'OPENAI_EMBEDDING_MODEL', 'text-embedding-3-large')
            self.available = True
            logger.info(f"EmbeddingService initialized with model: {self.embedding_model}")
        except ImportError:
            logger.warning("OpenAI library not installed. Embeddings will not be available.")
            self.openai_client = None
            self.available = False
        except Exception as e:
            logger.error(f"Failed to initialize EmbeddingService: {e}")
            self.openai_client = None
            self.available = False
    
    def generate_embedding(self, text: str) -> Optional[List[float]]:
        """
        Generate embedding for a single text.
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector as list of floats, or None if unavailable
        """
        if not self.available or not self.openai_client:
            logger.warning("Embedding service not available")
            return None
        
        if not text or not text.strip():
            logger.warning("Empty text provided for embedding")
            return None
        
        try:
            # Truncate text if too long (OpenAI has token limits)
            # text-embedding-3-large supports up to 8192 tokens
            # Approximate: 1 token ≈ 4 characters, so max ~32,000 characters
            max_chars = 30000
            if len(text) > max_chars:
                logger.warning(f"Text too long ({len(text)} chars), truncating to {max_chars}")
                text = text[:max_chars]
            
            response = self.openai_client.embeddings.create(
                model=self.embedding_model,
                input=text
            )
            
            embedding = response.data[0].embedding
            logger.info(f"Generated embedding (dimension: {len(embedding)})")
            return embedding
            
        except Exception as e:
            # Handle specific OpenAI errors gracefully
            error_str = str(e)
            
            # Check for quota/rate limit errors
            if '429' in error_str or 'quota' in error_str.lower() or 'rate limit' in error_str.lower():
                logger.warning(
                    "OpenAI API quota exceeded or rate limited. "
                    "Document will use keyword search instead. "
                    "To enable semantic search, add billing to your OpenAI account: "
                    "https://platform.openai.com/account/billing"
                )
            elif '401' in error_str or 'invalid' in error_str.lower():
                logger.warning(
                    "OpenAI API key invalid or expired. "
                    "Document will use keyword search instead."
                )
            else:
                logger.error(f"Error generating embedding: {e}")
            
            return None
    
    def generate_embeddings_batch(self, texts: List[str]) -> List[Optional[List[float]]]:
        """
        Generate embeddings for multiple texts in batch.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors (or None for failed embeddings)
        """
        if not self.available or not self.openai_client:
            logger.warning("Embedding service not available")
            return [None] * len(texts)
        
        if not texts:
            return []
        
        try:
            # Filter out empty texts
            valid_texts = []
            valid_indices = []
            for i, text in enumerate(texts):
                if text and text.strip():
                    # Truncate if needed
                    max_chars = 30000
                    if len(text) > max_chars:
                        text = text[:max_chars]
                    valid_texts.append(text)
                    valid_indices.append(i)
            
            if not valid_texts:
                return [None] * len(texts)
            
            response = self.openai_client.embeddings.create(
                model=self.embedding_model,
                input=valid_texts
            )
            
            # Map embeddings back to original indices
            embeddings = [None] * len(texts)
            for idx, embedding_data in zip(valid_indices, response.data):
                embeddings[idx] = embedding_data.embedding
            
            logger.info(f"Generated {len(valid_texts)} embeddings in batch")
            return embeddings
            
        except Exception as e:
            logger.error(f"Error generating batch embeddings: {e}", exc_info=True)
            return [None] * len(texts)
    
    def cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """
        Calculate cosine similarity between two vectors.
        
        Args:
            vec1: First embedding vector
            vec2: Second embedding vector
            
        Returns:
            Cosine similarity score (0-1)
        """
        try:
            if NUMPY_AVAILABLE:
                vec1 = np.array(vec1)
                vec2 = np.array(vec2)
                
                dot_product = np.dot(vec1, vec2)
                norm1 = np.linalg.norm(vec1)
                norm2 = np.linalg.norm(vec2)
                
                if norm1 == 0 or norm2 == 0:
                    return 0.0
                
                similarity = dot_product / (norm1 * norm2)
                return float(similarity)
            else:
                # Fallback implementation without numpy
                if len(vec1) != len(vec2):
                    return 0.0
                
                dot_product = sum(a * b for a, b in zip(vec1, vec2))
                norm1 = sum(a * a for a in vec1) ** 0.5
                norm2 = sum(b * b for b in vec2) ** 0.5
                
                if norm1 == 0 or norm2 == 0:
                    return 0.0
                
                similarity = dot_product / (norm1 * norm2)
                return float(similarity)
            
        except Exception as e:
            logger.error(f"Error calculating cosine similarity: {e}")
            return 0.0
    
    def find_similar_documents(
        self, 
        query_embedding: List[float], 
        document_embeddings: List[Dict], 
        top_k: int = 5,
        similarity_threshold: float = 0.5
    ) -> List[Dict]:
        """
        Find most similar documents using cosine similarity.
        
        Args:
            query_embedding: Query embedding vector
            document_embeddings: List of dicts with 'embedding' and 'document_id' keys
            top_k: Number of top results to return
            similarity_threshold: Minimum similarity score (0-1)
            
        Returns:
            List of similar documents with similarity scores, sorted by score (descending)
        """
        if not query_embedding:
            return []
        
        results = []
        
        for doc_data in document_embeddings:
            doc_embedding = doc_data.get('embedding')
            if not doc_embedding:
                continue
            
            similarity = self.cosine_similarity(query_embedding, doc_embedding)
            
            if similarity >= similarity_threshold:
                results.append({
                    'document_id': doc_data.get('document_id'),
                    'similarity': similarity,
                    'metadata': doc_data.get('metadata', {})
                })
        
        # Sort by similarity (descending)
        results.sort(key=lambda x: x['similarity'], reverse=True)
        
        # Return top_k results
        return results[:top_k]
    
    def is_available(self) -> bool:
        """Check if embedding service is available"""
        return self.available

