# How to Set API Keys for Frontline Agent Embeddings

## Overview

The Frontline Agent uses **embeddings** for semantic search. The system supports:
- **OpenRouter** (tried first if `OPENROUTER_API_KEY` is set) - **Recommended** ⭐
- **DeepSeek** (tried second if `DEEPSEEK_API_KEY` is set)
- **Groq** (tried third if `GROQ_API_KEY` is set)
- **OpenAI** (fallback if others don't support embeddings)

**Priority Order**: OpenRouter → DeepSeek → Groq → OpenAI

**Note**: OpenRouter provides access to multiple models including DeepSeek models. If the specified model doesn't support embeddings, the system will automatically try alternative embedding models.

## Option 1: Use OpenRouter (Recommended) ⭐

OpenRouter provides access to multiple models including DeepSeek, and is very cost-effective.

### Steps:
1. Get your OpenRouter API key from [OpenRouter Platform](https://openrouter.ai/)
2. Add to your `.env` file:
   ```env
   OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   OPENROUTER_EMBEDDING_MODEL=deepseek/deepseek-r1-0528:free
   ```
3. Restart Django server

**Note**: If `deepseek/deepseek-r1-0528:free` doesn't support embeddings, the system will automatically try alternative embedding models like `text-embedding-3-large`.

## Option 2: Use DeepSeek Directly

DeepSeek provides excellent embeddings and is cost-effective.

### Steps:
1. Get your DeepSeek API key from [DeepSeek Platform](https://platform.deepseek.com/)
2. Add to your `.env` file:
   ```env
   DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   DEEPSEEK_EMBEDDING_MODEL=deepseek/deepseek-r1-0528
   ```
3. Restart Django server

**Note**: If `deepseek/deepseek-r1-0528` doesn't support embeddings, the system will automatically use `deepseek-embedding-v3`.

## Option 3: Use Groq (with OpenAI fallback)

If you already have `GROQ_API_KEY` set, the system will automatically try Groq first, then fall back to OpenAI for embeddings.

### Steps:
1. Make sure `GROQ_API_KEY` is in your `.env` file
2. Add `OPENAI_API_KEY` as a fallback (required for embeddings)
3. Restart Django server

## Option 4: Use OpenAI Only

### 1. Get Your OpenAI API Key

If you don't have an OpenAI API key yet:

1. Go to [OpenAI Platform](https://platform.openai.com/)
2. Sign up or log in
3. Navigate to **API Keys** section: https://platform.openai.com/api-keys
4. Click **"Create new secret key"**
5. Give it a name (e.g., "Frontline Agent Embeddings")
6. Copy the key immediately (you won't be able to see it again!)

### 2. Add to .env File

1. **Locate your `.env` file** in the project root (same folder as `manage.py`)
   - Path: `C:\Study\Others\Projectsss\AIEmploees\AIEmployee\.env`

2. **Open the `.env` file** in a text editor

3. **Add this line** (replace `your-api-key-here` with your actual key):
   ```env
   OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```

4. **Save the file**

### 3. Restart Django Server

After adding the key, restart your Django development server:

```bash
# Stop the current server (Ctrl+C)
# Then start it again
python manage.py runserver
```

## Example .env File

Your `.env` file should look something like this:

```env
# Database Configuration
DB_NAME=your_database
DB_HOST=localhost
DB_USER=your_user
DB_PASSWORD=your_password

# API Keys
# OpenRouter is used for embeddings (semantic search) - Recommended ⭐
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
OPENROUTER_EMBEDDING_MODEL=deepseek/deepseek-r1-0528:free

# DeepSeek is used for embeddings (semantic search) - Alternative
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
DEEPSEEK_EMBEDDING_MODEL=deepseek/deepseek-r1-0528

# Groq is used for LLM tasks (Q&A, etc.)
GROQ_API_KEY=your_groq_key_here

# OpenAI is used for embeddings (semantic search) - Fallback
# Note: Only needed if OpenRouter/DeepSeek/Groq don't work
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Other settings...
FRONTEND_URL=http://localhost:3000
BACKEND_URL=http://localhost:8000
```

## How It Works

1. **System tries OpenRouter first** (if `OPENROUTER_API_KEY` is set) - Highest Priority
2. **If OpenRouter fails**, tries DeepSeek (if `DEEPSEEK_API_KEY` is set)
3. **If DeepSeek fails**, tries Groq (if `GROQ_API_KEY` is set)
4. **If Groq doesn't support embeddings**, falls back to OpenAI
5. **OpenAI handles embeddings** as final fallback

This means:
- ✅ OpenRouter is preferred for embeddings (access to multiple models, cost-effective)
- ✅ DeepSeek is a great alternative (high quality, cost-effective)
- ✅ Groq can be used for fast LLM inference (Q&A, ticket automation, etc.)
- ✅ OpenAI is available as fallback
- ✅ System works automatically with the available keys

## Verify It's Working

1. **Upload a document** in the Frontline Agent dashboard
2. **Check the logs** - you should see:
   ```
   Generated embedding for document [title] (dimension: 3072)
   ```
   Instead of:
   ```
   Embedding service not available, skipping embedding generation
   ```

3. **Ask a question** - semantic search should now work!

## Alternative: Set in Windows Environment Variables

If you prefer to set it system-wide (not recommended for development):

### Windows PowerShell:
```powershell
[System.Environment]::SetEnvironmentVariable('OPENAI_API_KEY', 'sk-proj-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx', 'User')
```

### Windows Command Prompt:
```cmd
setx OPENAI_API_KEY "sk-proj-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

**Note**: You'll need to restart your terminal/Django server after setting it this way.

## Troubleshooting

### "Embedding service not available"
- Check that `OPENAI_API_KEY` is in your `.env` file
- Make sure there are no extra spaces or quotes around the key
- Restart Django server after adding the key
- Check that `python-dotenv` is installed: `pip install python-dotenv`

### "Invalid API Key"
- Make sure you copied the entire key (starts with `sk-`)
- Check for any extra spaces or line breaks
- Verify the key is active in your OpenAI account

### Still Not Working?
1. Check Django logs for error messages
2. Verify the `.env` file is in the project root (same folder as `manage.py`)
3. Make sure `python-dotenv` is installed: `pip install python-dotenv`
4. Try setting it directly in code temporarily to test:
   ```python
   # In embedding_service.py (temporary test only!)
   self.openai_client = OpenAI(api_key='sk-proj-your-key-here')
   ```

## Security Notes

⚠️ **Important**:
- Never commit your `.env` file to Git (it should be in `.gitignore`)
- Never share your API key publicly
- Keep your API key secure
- Rotate keys if they're exposed

## Cost Information

OpenAI embeddings are very affordable:
- **text-embedding-3-large**: ~$0.00013 per 1K tokens
- Average document: ~500-2000 tokens
- Cost per document: ~$0.0001 - $0.0003 (less than 1 cent per 1000 documents!)

