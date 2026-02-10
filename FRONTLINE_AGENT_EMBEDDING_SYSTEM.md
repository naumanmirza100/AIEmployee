# Frontline Agent Embedding System

## Overview

The Frontline Agent uses **semantic search** powered by embeddings to find relevant information from uploaded documents. This provides much better search results than traditional keyword matching.

## How It Works

### 1. Document Upload & Embedding Generation

When a document is uploaded:

1. **Text Extraction**: The document is processed to extract text content (PDF, DOCX, TXT, etc.)
2. **Embedding Generation**: 
   - The system creates a searchable text combining: `title + description + extracted_content`
   - An embedding vector is generated using OpenAI's embedding API
   - The embedding is a high-dimensional vector (e.g., 3072 dimensions for `text-embedding-3-large`)
3. **Storage**: The embedding is stored in the database in the `Document.embedding` field (JSONField)

**Example:**
```python
# Document uploaded: "Company Policy.pdf"
# Extracted text: "Our company policy states that..."
# Embedding generated: [0.123, -0.456, 0.789, ...] (3072 numbers)
# Stored in: Document.embedding = [0.123, -0.456, 0.789, ...]
```

### 2. User Query & Semantic Search

When a user asks a question:

1. **Query Embedding**: The user's question is converted to an embedding vector
2. **Similarity Search**: 
   - The query embedding is compared with all document embeddings using **cosine similarity**
   - Documents with similarity score ≥ 0.7 are considered relevant
   - Results are sorted by similarity score (highest first)
3. **Results**: Top matching documents are returned with their similarity scores

**Example:**
```
User asks: "What is the refund policy?"
→ Query embedding: [0.234, -0.567, 0.890, ...]
→ Compare with document embeddings:
  - Document A (Refund Policy): similarity = 0.92 ✓
  - Document B (Shipping Info): similarity = 0.45 ✗
  - Document C (Terms of Service): similarity = 0.78 ✓
→ Return: Document A and Document C (sorted by similarity)
```

## Database Schema

### Document Model Fields

```python
class Document(models.Model):
    # ... other fields ...
    embedding = models.JSONField(null=True, blank=True)  # Vector embedding stored as list
    embedding_model = models.CharField(max_length=100, null=True)  # e.g., "text-embedding-3-large"
    document_content = models.TextField()  # Extracted text for keyword fallback
    is_indexed = models.BooleanField(default=False)  # Whether document is searchable
    processed = models.BooleanField(default=False)  # Whether processing completed
```

## Search Flow

```
User Question
    ↓
get_answer() → search_knowledge() → _search_documents()
    ↓
1. Generate query embedding
    ↓
2. Load all document embeddings from database
    ↓
3. Calculate cosine similarity for each document
    ↓
4. Filter: similarity ≥ 0.7
    ↓
5. Sort by similarity (descending)
    ↓
6. Return top N results
```

## Configuration

### Required Environment Variable

```env
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### Settings

- **Embedding Model**: `text-embedding-3-large` (default)
- **Similarity Threshold**: `0.7` (minimum score for relevance)
- **Max Results**: `5` (default, configurable)

## Fallback Behavior

If embeddings are not available:

1. **No API Key**: Falls back to keyword search
2. **Quota Exceeded**: Falls back to keyword search
3. **No Document Embeddings**: Falls back to keyword search for that document
4. **Embedding Generation Fails**: Falls back to keyword search

**Keyword Search** uses:
- `title__icontains=query`
- `description__icontains=query`
- `document_content__icontains=query`

## Performance

### Embedding Generation
- **Cost**: ~$0.00013 per 1K tokens (very affordable)
- **Speed**: ~1-2 seconds per document
- **Dimension**: 3072 (text-embedding-3-large)

### Search Performance
- **Query Embedding**: ~0.5-1 second
- **Similarity Calculation**: ~0.1-0.5 seconds (depends on number of documents)
- **Total**: ~1-2 seconds for semantic search

## Benefits

✅ **Semantic Understanding**: Finds documents even if exact keywords don't match  
✅ **Better Relevance**: Results ranked by semantic similarity, not just keyword matches  
✅ **Context-Aware**: Understands meaning, not just words  
✅ **Multilingual**: Works with any language (if supported by embedding model)

## Example Use Cases

1. **User asks**: "How do I return a product?"  
   **Finds**: Documents about "returns", "refunds", "product returns", even if exact phrase isn't in document

2. **User asks**: "What's the cancellation policy?"  
   **Finds**: Documents about "cancellations", "termination", "ending service", etc.

3. **User asks**: "Can I get my money back?"  
   **Finds**: Documents about "refunds", "reimbursements", "money back guarantee", etc.

## Troubleshooting

### Embeddings Not Generated

**Check:**
1. Is `OPENAI_API_KEY` set in `.env`?
2. Is the API key valid?
3. Check Django logs for error messages
4. Is there quota/billing set up in OpenAI account?

**Logs to look for:**
```
✓ Embedding generated and will be stored in database (dimension: 3072)
✗ Embedding generation failed for document: [title]
```

### Search Not Using Embeddings

**Check:**
1. Do documents have embeddings? Check `Document.embedding` field
2. Are documents marked as `processed=True` and `is_indexed=True`?
3. Check logs: "Using semantic search" vs "Using keyword-based search"

**Logs to look for:**
```
Using semantic search (embeddings) for query
Query embedding generated successfully (dimension: 3072)
Semantic search found 3 documents
```

### Low Quality Results

**Solutions:**
1. Adjust similarity threshold (currently 0.7)
2. Ensure documents have good quality text extraction
3. Add more relevant documents to knowledge base
4. Check that embeddings were generated successfully

## Code Locations

- **Embedding Service**: `core/Fronline_agent/embedding_service.py`
- **Document Upload**: `api/views/frontline_agent.py` (upload_document function)
- **Search Logic**: `core/Fronline_agent/services.py` (_search_documents method)
- **Document Model**: `Frontline_agent/models.py` (Document class)

## Next Steps

1. ✅ Embeddings are generated when documents are uploaded
2. ✅ Embeddings are stored in the database
3. ✅ Query embeddings are generated for user questions
4. ✅ Semantic search compares query with document embeddings
5. ✅ Results are sorted by similarity score
6. ✅ Fallback to keyword search if embeddings unavailable

**Everything is set up and working!** 🎉

