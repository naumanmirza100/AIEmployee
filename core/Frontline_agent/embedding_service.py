"""
Embedding Service for Frontline Agent
Handles generation and storage of document embeddings for semantic search
Supports OpenRouter, DeepSeek, Groq, and OpenAI (via OpenAI-compatible endpoints)
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
    Supports OpenRouter, DeepSeek, Groq, and OpenAI (via OpenAI-compatible endpoints).
    Priority: OpenRouter > DeepSeek > Groq > OpenAI
    """
    
    def __init__(self):
        """Initialize embedding service with OpenRouter, DeepSeek, Groq, or OpenAI client"""
        self.provider = None  # 'openrouter', 'deepseek', 'groq', or 'openai'
        self.client = None
        self.embedding_model = None
        self.available = False
        
        # Check which provider to use
        embedding_provider = getattr(settings, 'EMBEDDING_PROVIDER', 'auto').lower()
        
        # Try OpenRouter first (if available and configured) - Highest Priority
        if embedding_provider in ('auto', 'openrouter'):
            if self._init_openrouter():
                self.provider = 'openrouter'
                self.available = True
                logger.info(f"EmbeddingService initialized with OpenRouter (model: {self.embedding_model})")
                return
        
        # Try DeepSeek second (if available and configured)
        if embedding_provider in ('auto', 'deepseek'):
            if self._init_deepseek():
                self.provider = 'deepseek'
                self.available = True
                logger.info(f"EmbeddingService initialized with DeepSeek (model: {self.embedding_model})")
                return
        
        # Try Groq third (if available and configured)
        if embedding_provider in ('auto', 'groq'):
            if self._init_groq():
                self.provider = 'groq'
                self.available = True
                logger.info(f"EmbeddingService initialized with Groq (model: {self.embedding_model})")
                return
        
        # Fallback to OpenAI
        if embedding_provider in ('auto', 'openai'):
            if self._init_openai():
                self.provider = 'openai'
                self.available = True
                logger.info(f"EmbeddingService initialized with OpenAI (model: {self.embedding_model})")
                return
        
        # No provider available
        logger.warning("EmbeddingService: No embedding provider available (OpenRouter, DeepSeek, Groq, or OpenAI). Embeddings will not work.")
        self.available = False
    
    def _init_openrouter(self) -> bool:
        """
        Initialize OpenRouter client for embeddings (using OpenAI-compatible endpoint).
        
        OpenRouter provides access to multiple models including DeepSeek via OpenAI-compatible API.
        Uses the model specified in OPENROUTER_EMBEDDING_MODEL or defaults to deepseek/deepseek-r1-0528:free.
        """
        try:
            openrouter_api_key = (
                os.getenv('OPENROUTER_API_KEY') or
                getattr(settings, 'OPENROUTER_API_KEY', None)
            )
            
            if not openrouter_api_key:
                return False
            
            # OpenRouter uses OpenAI-compatible API
            from openai import OpenAI
            self.client = OpenAI(
                api_key=openrouter_api_key,
                base_url="https://openrouter.ai/api/v1"
            )
            
            # Use the model specified by user, or default to DeepSeek model via OpenRouter
            user_model = getattr(settings, 'OPENROUTER_EMBEDDING_MODEL', 'deepseek/deepseek-r1-0528:free')
            self.embedding_model = user_model
            
            # Test if embeddings are available with the specified model
            try:
                test_response = self.client.embeddings.create(
                    model=self.embedding_model,
                    input="test"
                )
                # If successful, the model supports embeddings
                logger.info(f"OpenRouter embeddings endpoint is available with model: {self.embedding_model}")
                return True
            except Exception as test_error:
                # The specified model might not support embeddings
                # Try alternative embedding models available on OpenRouter
                logger.debug(f"Model {self.embedding_model} may not support embeddings: {test_error}")
                
                # Try OpenAI embedding models available on OpenRouter
                alternative_models = [
                    'text-embedding-3-large',
                    'text-embedding-3-small',
                    'text-embedding-ada-002'
                ]
                
                for alt_model in alternative_models:
                    try:
                        test_response = self.client.embeddings.create(
                            model=alt_model,
                            input="test"
                        )
                        self.embedding_model = alt_model
                        logger.info(f"Using OpenRouter embedding model: {alt_model} (original model {user_model} doesn't support embeddings)")
                        return True
                    except Exception:
                        continue
                
                logger.debug(f"OpenRouter embedding models not available")
                self.client = None
                return False
                
        except ImportError:
            logger.debug("OpenAI library not installed, cannot use OpenRouter embeddings")
            return False
        except Exception as e:
            logger.debug(f"Failed to initialize OpenRouter embeddings: {e}")
            return False
    
    def _init_deepseek(self) -> bool:
        """
        Initialize DeepSeek client for embeddings (using OpenAI-compatible endpoint).
        
        DeepSeek provides OpenAI-compatible API for embeddings.
        Uses the model specified in DEEPSEEK_EMBEDDING_MODEL or defaults to deepseek-embedding-v3.
        """
        try:
            deepseek_api_key = (
                os.getenv('DEEPSEEK_API_KEY') or
                getattr(settings, 'DEEPSEEK_API_KEY', None)
            )
            
            if not deepseek_api_key:
                return False
            
            # DeepSeek uses OpenAI-compatible API
            from openai import OpenAI
            self.client = OpenAI(
                api_key=deepseek_api_key,
                base_url="https://api.deepseek.com/v1"
            )
            
            # Use the model specified by user, or default to DeepSeek's embedding model
            # Note: deepseek-r1-0528 is a language model, not an embedding model
            # If it doesn't work, we'll try deepseek-embedding-v3
            user_model = getattr(settings, 'DEEPSEEK_EMBEDDING_MODEL', 'deepseek/deepseek-r1-0528')
            self.embedding_model = user_model
            
            # Test if embeddings are available with the specified model
            try:
                test_response = self.client.embeddings.create(
                    model=self.embedding_model,
                    input="test"
                )
                # If successful, the model supports embeddings
                logger.info(f"DeepSeek embeddings endpoint is available with model: {self.embedding_model}")
                return True
            except Exception as test_error:
                # The specified model might not support embeddings
                # Try DeepSeek's embedding model as fallback
                logger.debug(f"Model {self.embedding_model} may not support embeddings: {test_error}")
                
                # Try DeepSeek's embedding model
                embedding_model = 'deepseek-embedding-v3'
                try:
                    test_response = self.client.embeddings.create(
                        model=embedding_model,
                        input="test"
                    )
                    self.embedding_model = embedding_model
                    logger.info(f"Using DeepSeek embedding model: {embedding_model} (original model {user_model} doesn't support embeddings)")
                    return True
                except Exception as embedding_error:
                    logger.debug(f"DeepSeek embedding model also failed: {embedding_error}")
                    self.client = None
                    return False
                
        except ImportError:
            logger.debug("OpenAI library not installed, cannot use DeepSeek embeddings")
            return False
        except Exception as e:
            logger.debug(f"Failed to initialize DeepSeek embeddings: {e}")
            return False
    
    def _init_groq(self) -> bool:
        """
        Initialize Groq client for embeddings (using OpenAI-compatible endpoint).
        
        Note: Groq doesn't natively support embeddings API. This method tests if
        Groq's OpenAI-compatible endpoint supports embeddings. If not, it will
        return False and the service will fall back to OpenAI for embeddings.
        """
        try:
            groq_api_key = (
                os.getenv('GROQ_API_KEY') or 
                os.getenv('GROQ_REC_API_KEY') or
                getattr(settings, 'GROQ_API_KEY', None) or
                getattr(settings, 'GROQ_REC_API_KEY', None)
            )
            
            if not groq_api_key:
                return False
            
            # Groq uses OpenAI-compatible API, so we can use OpenAI client with Groq's base URL
            from openai import OpenAI
            self.client = OpenAI(
                api_key=groq_api_key,
                base_url="https://api.groq.com/openai/v1"
            )
            
            # Note: Groq doesn't natively support embeddings API.
            # We test if their OpenAI-compatible endpoint supports embeddings.
            # If not, we'll fall back to OpenAI automatically.
            
            # Try to use a lightweight embedding model
            self.embedding_model = getattr(settings, 'GROQ_EMBEDDING_MODEL', 'text-embedding-ada-002')
            
            # Test if embeddings are available by making a small test call
            try:
                test_response = self.client.embeddings.create(
                    model=self.embedding_model,
                    input="test"
                )
                # If successful, Groq supports embeddings (unlikely but possible)
                logger.info("Groq embeddings endpoint is available")
                return True
            except Exception as test_error:
                # Groq doesn't support embeddings (expected behavior)
                # This is normal - Groq focuses on LLM inference, not embeddings
                logger.debug(f"Groq embeddings not available (expected): {test_error}")
                logger.info("Groq doesn't support embeddings. Will use OpenAI for embeddings if available.")
                self.client = None
                return False
                
        except ImportError:
            logger.debug("OpenAI library not installed, cannot use Groq embeddings")
            return False
        except Exception as e:
            logger.debug(f"Failed to initialize Groq embeddings: {e}")
            return False
    
    def _init_openai(self) -> bool:
        """Initialize OpenAI client for embeddings"""
        try:
            openai_api_key = os.getenv('OPENAI_API_KEY') or getattr(settings, 'OPENAI_API_KEY', None)
            
            if not openai_api_key:
                return False
            
            from openai import OpenAI
            self.client = OpenAI(api_key=openai_api_key)
            self.embedding_model = getattr(settings, 'OPENAI_EMBEDDING_MODEL', 'text-embedding-3-large')
            return True
            
        except ImportError:
            logger.debug("OpenAI library not installed. Embeddings will not be available.")
            return False
        except Exception as e:
            logger.debug(f"Failed to initialize OpenAI embeddings: {e}")
            return False
    
    def generate_embedding(self, text: str) -> Optional[List[float]]:
        """
        Generate embedding for a single text.
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector as list of floats, or None if unavailable
        """
        if not self.available or not self.client:
            logger.warning("Embedding service not available")
            return None
        
        if not text or not text.strip():
            logger.warning("Empty text provided for embedding")
            return None
        
        try:
            # Truncate text if too long (token limits vary by model)
            # Approximate: 1 token ≈ 4 characters, so max ~32,000 characters for most models
            # NOTE: This truncation is ONLY for embedding generation. The full document content
            # is still stored in the database separately.
            original_length = len(text)
            max_chars = 30000
            if len(text) > max_chars:
                logger.info(f"Text too long ({original_length:,} chars) for embedding API, using first {max_chars:,} chars for embedding generation")
                logger.info(f"NOTE: Full document content ({original_length:,} chars) will still be stored in database")
                text = text[:max_chars]
            
            response = self.client.embeddings.create(
                model=self.embedding_model,
                input=text
            )
            
            embedding = response.data[0].embedding
            logger.info(f"Generated embedding using {self.provider} (dimension: {len(embedding)})")
            return embedding
            
        except Exception as e:
            # Handle specific API errors gracefully
            error_str = str(e)
            
            # Check for quota/rate limit errors
            if '429' in error_str or 'quota' in error_str.lower() or 'rate limit' in error_str.lower():
                provider_names = {'openrouter': 'OpenRouter', 'deepseek': 'DeepSeek', 'groq': 'Groq', 'openai': 'OpenAI'}
                provider_name = provider_names.get(self.provider, 'API')
                logger.warning(
                    f"{provider_name} API quota exceeded or rate limited. "
                    "Document will use keyword search instead."
                )
            elif '401' in error_str or 'invalid' in error_str.lower() or 'unauthorized' in error_str.lower():
                provider_names = {'openrouter': 'OpenRouter', 'deepseek': 'DeepSeek', 'groq': 'Groq', 'openai': 'OpenAI'}
                provider_name = provider_names.get(self.provider, 'API')
                logger.warning(
                    f"{provider_name} API key invalid or expired. "
                    "Document will use keyword search instead."
                )
            elif 'not found' in error_str.lower() or 'model' in error_str.lower():
                # Model not available (e.g., Groq doesn't support embeddings)
                logger.warning(
                    f"Embedding model not available with {self.provider}. "
                    "Falling back to keyword search."
                )
            else:
                logger.error(f"Error generating embedding with {self.provider}: {e}")
            
            return None
    
    def generate_embeddings_batch(self, texts: List[str]) -> List[Optional[List[float]]]:
        """
        Generate embeddings for multiple texts in batch.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors (or None for failed embeddings)
        """
        if not self.available or not self.client:
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
                    # Truncate if needed (only for embedding, full content stored separately)
                    original_length = len(text)
                    max_chars = 30000
                    if len(text) > max_chars:
                        logger.info(f"Text {i+1} too long ({original_length:,} chars) for embedding API, using first {max_chars:,} chars")
                        text = text[:max_chars]
                    valid_texts.append(text)
                    valid_indices.append(i)
            
            if not valid_texts:
                return [None] * len(texts)
            
            response = self.client.embeddings.create(
                model=self.embedding_model,
                input=valid_texts
            )
            
            # Map embeddings back to original indices
            embeddings = [None] * len(texts)
            for idx, embedding_data in zip(valid_indices, response.data):
                embeddings[idx] = embedding_data.embedding
            
            logger.info(f"Generated {len(valid_texts)} embeddings in batch using {self.provider}")
            return embeddings
            
        except Exception as e:
            logger.error(f"Error generating batch embeddings with {self.provider}: {e}", exc_info=True)
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

