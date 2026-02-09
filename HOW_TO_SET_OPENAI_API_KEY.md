# How to Set OPENAI_API_KEY

## Quick Steps

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
GROQ_API_KEY=your_groq_key_here
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Other settings...
FRONTEND_URL=http://localhost:3000
BACKEND_URL=http://localhost:8000
```

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

