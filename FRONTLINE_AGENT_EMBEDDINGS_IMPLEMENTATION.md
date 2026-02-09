# Frontline Agent - Embedding-Based Semantic Search Implementation

## Overview

This document describes the implementation of embedding-based semantic search for the Frontline Agent. This enhancement allows the agent to understand the meaning of questions and find relevant documents even when exact keywords don't match.

## What Was Implemented

### 1. **Database Schema Changes**
- Added `embedding` field (JSONField) to `Document` model to store vector embeddings
- Added `embedding_model` field (CharField) to track which model was used to generate embeddings
- Migration: `Frontline_agent/migrations/0004_add_embedding_fields.py`

### 2. **Embedding Service** (`core/Fronline_agent/embedding_service.py`)
- **EmbeddingService Class**: Handles all embedding-related operations
  - `generate_embedding(text)`: Generates embedding for a single text using OpenAI API
  - `generate_embeddings_batch(texts)`: Generates embeddings for multiple texts
  - `cosine_similarity(vec1, vec2)`: Calculates cosine similarity between two vectors
  - `find_similar_documents(query_embedding, document_embeddings, top_k, threshold)`: Finds most similar documents
- Uses OpenAI's `text-embedding-3-large` model by default
- Falls back to basic cosine similarity calculation if NumPy is not available
- Handles text truncation for very long documents (max 30,000 characters)

### 3. **Document Upload Enhancement** (`api/views/frontline_agent.py`)
- Automatically generates embeddings when documents are uploaded
- Creates searchable text from: `title + description + document_content`
- Stores embedding in database as JSON array
- Gracefully handles errors - continues without embedding if generation fails

### 4. **Semantic Search Implementation** (`core/Fronline_agent/services.py`)
- Updated `_search_documents()` method to use semantic search
- **Search Strategy**:
  1. **Primary**: Semantic search using embeddings (if available)
     - Generates query embedding
     - Compares with all document embeddings using cosine similarity
     - Returns top-k most similar documents (similarity threshold: 0.5)
  2. **Fallback**: Keyword-based search (if semantic search fails or no embeddings available)
     - Uses Django ORM `icontains` for text matching
- Results include similarity scores and search method used

### 5. **Management Command** (`Frontline_agent/management/commands/generate_embeddings.py`)
- Utility to generate embeddings for existing documents
- Usage:
  ```bash
  # Generate embeddings for all documents without embeddings
  python manage.py generate_embeddings
  
  # Generate for specific company
  python manage.py generate_embeddings --company-id 1
  
  # Regenerate all embeddings
  python manage.py generate_embeddings --all
  
  # Limit number of documents
  python manage.py generate_embeddings --limit 10
  ```

## How It Works

### Document Upload Flow:
1. User uploads a document
2. Document processor extracts text content
3. Embedding service generates embedding from: `title + description + content`
4. Embedding is stored in database as JSON array
5. Document is marked as indexed

### Search Flow:
1. User asks a question
2. System generates embedding for the question
3. Compares question embedding with all document embeddings using cosine similarity
4. Returns documents with similarity score ≥ 0.5, sorted by relevance
5. If no semantic matches found, falls back to keyword search

### Example:
- **Question**: "How do I reset my password?"
- **Document 1**: Contains "password reset procedure" → High similarity (0.85)
- **Document 2**: Contains "account recovery" → Medium similarity (0.72)
- **Document 3**: Contains "login issues" → Lower similarity (0.58)
- **Document 4**: Contains "billing information" → Low similarity (0.35) → Excluded

## Benefits

1. **Semantic Understanding**: Finds relevant documents even when exact keywords don't match
2. **Better Relevance**: Results ranked by semantic similarity, not just keyword presence
3. **Synonym Handling**: Understands that "password reset" and "account recovery" are related
4. **Graceful Degradation**: Falls back to keyword search if embeddings unavailable
5. **Backward Compatible**: Existing documents continue to work with keyword search

## Requirements

- **OpenAI API Key**: Must be set in environment variable `OPENAI_API_KEY`
- **OpenAI Python Library**: `pip install openai`
- **NumPy (Optional)**: `pip install numpy` - for faster cosine similarity calculation

## Configuration

Default embedding model: `text-embedding-3-large`

To change the model, set in Django settings:
```python
OPENAI_EMBEDDING_MODEL = 'text-embedding-ada-002'  # or other model
```

## Migration Steps

1. **Run Migration**:
   ```bash
   python manage.py migrate Frontline_agent
   ```

2. **Generate Embeddings for Existing Documents**:
   ```bash
   python manage.py generate_embeddings
   ```

3. **Verify**:
   - Upload a new document and check that embedding is generated
   - Ask a question and verify semantic search is working

## Performance Considerations

- **Embedding Generation**: ~1-2 seconds per document (depends on OpenAI API)
- **Search Speed**: Fast for small-medium document sets (<1000 documents)
- **Storage**: Each embedding is ~3072 floats (for text-embedding-3-large) = ~12KB per document
- **API Costs**: OpenAI charges per token for embedding generation

## Limitations

1. **API Dependency**: Requires OpenAI API key and internet connection
2. **Cost**: Each embedding generation costs money (very small amount per document)
3. **Large Documents**: Text is truncated to 30,000 characters for embedding
4. **Search Threshold**: Documents with similarity < 0.5 are excluded

## Future Enhancements

1. **Chunking**: Split large documents into chunks and embed each chunk separately
2. **Hybrid Search**: Combine semantic and keyword search scores
3. **Caching**: Cache query embeddings for frequently asked questions
4. **Batch Processing**: Process embeddings asynchronously for better performance
5. **Alternative Embeddings**: Support for other embedding providers (HuggingFace, Cohere, etc.)

## Troubleshooting

### Embeddings Not Generated
- Check `OPENAI_API_KEY` is set correctly
- Verify OpenAI library is installed: `pip install openai`
- Check logs for error messages

### Search Not Working
- Verify documents have embeddings: Check `embedding` field is not null
- Run `python manage.py generate_embeddings` to generate missing embeddings
- Check similarity threshold (default 0.5) - may need adjustment

### Performance Issues
- Consider using batch embedding generation for multiple documents
- Implement caching for frequently accessed embeddings
- Use async processing for large document sets

