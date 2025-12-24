"""
Marketing Base Agent Class
Uses Groq API for Q&A and OpenAI API (optional) for advanced tasks
Separate from core BaseAgent to avoid disrupting existing system
"""

try:
    from groq import Groq
except ImportError:
    raise ImportError("groq library not installed. Run: pip install --upgrade groq")

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None  # Optional - only needed for document writing

from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class MarketingBaseAgent:
    """
    Base class for all Marketing AI agents.
    Uses Groq API for Q&A and OpenAI API (optional) for advanced tasks.
    
    Model Selection:
    - Reasoning/Q&A: Groq (llama-3.1-8b-instant or other Groq models)
    - Document Writing: OpenAI GPT-4.1 (optional, if API key provided)
    - Embeddings (RAG): OpenAI text-embedding-3-large (optional, if API key provided)
    """
    
    def __init__(self, model=None, use_embeddings=False):
        """
        Initialize the marketing base agent with Groq (for Q&A) and OpenAI (for advanced tasks).
        
        Args:
            model (str): Groq model to use. Defaults to settings.GROQ_MODEL for Q&A
            use_embeddings (bool): Whether this agent needs embeddings capability
        """
        # Groq API (for Q&A)
        self.groq_api_key = getattr(settings, 'GROQ_API_KEY', None)
        if not self.groq_api_key:
            raise ValueError("GROQ_API_KEY not found in environment variables. Please set it in .env file.")
        
        try:
            # Initialize Groq client (same pattern as core BaseAgent)
            self.groq_client = Groq(api_key=self.groq_api_key)
        except TypeError as e:
            error_msg = str(e)
            if 'proxies' in error_msg or 'unexpected keyword' in error_msg:
                logger.error(f"Groq client initialization error: {e}")
                logger.error("This is usually caused by an outdated groq library version.")
                logger.error("Please run: pip install --upgrade groq")
                raise ValueError(
                    f"Groq client initialization failed. "
                    f"This is likely due to an incompatible groq library version. "
                    f"Please update it: pip install --upgrade groq. "
                    f"Original error: {e}"
                )
            else:
                raise
        except Exception as e:
            logger.error(f"Unexpected error initializing Groq client: {e}")
            raise ValueError(f"Failed to initialize Groq client: {e}")
        
        # OpenAI API (Optional - for document writing and advanced tasks)
        self.openai_api_key = getattr(settings, 'OPENAI_API_KEY', None)
        if OpenAI and self.openai_api_key:
            try:
                self.openai_client = OpenAI(api_key=self.openai_api_key)
            except Exception as e:
                logger.warning(f"OpenAI client initialization failed: {e}. Will use Groq only.")
                self.openai_client = None
        else:
            self.openai_client = None
        
        # Model selection based on use case
        if use_embeddings:
            # For embeddings, we'll use a separate method
            self.embedding_model = getattr(settings, 'OPENAI_EMBEDDING_MODEL', 'text-embedding-3-large')
            self.model = None  # Embeddings don't use chat model
        else:
            # Default to Groq model for Q&A
            default_model = getattr(settings, 'GROQ_MODEL', 'llama-3.1-8b-instant')
            self.model = model or default_model
            self.embedding_model = None
        
        self.agent_name = self.__class__.__name__
    
    def _call_llm(self, prompt, system_prompt=None, temperature=0.7, max_tokens=2000, model=None):
        """
        Make a call to the LLM API (Groq for Q&A, OpenAI for advanced tasks).
        
        Args:
            prompt (str): User prompt/question
            system_prompt (str): System prompt for context
            temperature (float): Sampling temperature (0-2)
            max_tokens (int): Maximum tokens in response
            model (str): Override model for this call
            
        Returns:
            str: LLM response text
        """
        # If OpenAI is available and GPT model specified, use it; otherwise use Groq
        if self.openai_client and model and 'gpt' in model.lower():
            return self._call_openai(prompt, system_prompt, temperature, max_tokens, model)
        else:
            # Default to Groq for Q&A
            return self._call_groq_qa(prompt, system_prompt, temperature, max_tokens)
    
    def _call_openai(self, prompt, system_prompt=None, temperature=0.7, max_tokens=2000, model=None):
        """
        Make a call to the OpenAI LLM API (for document writing and advanced tasks).
        
        Args:
            prompt (str): User prompt/question
            system_prompt (str): System prompt for context
            temperature (float): Sampling temperature (0-2)
            max_tokens (int): Maximum tokens in response
            model (str): Override model for this call
            
        Returns:
            str: LLM response text
        """
        if not self.openai_client:
            raise ValueError("OpenAI client not available. Please set OPENAI_API_KEY in .env file.")
        
        try:
            messages = []
            
            if system_prompt:
                messages.append({
                    "role": "system",
                    "content": system_prompt
                })
            
            messages.append({
                "role": "user",
                "content": prompt
            })
            
            # Use specified model or default
            model_to_use = model or getattr(settings, 'OPENAI_MODEL', 'gpt-4.1')
            
            response = self.openai_client.chat.completions.create(
                model=model_to_use,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"Error in {self.agent_name} OpenAI LLM call: {str(e)}")
            raise
    
    def _get_embeddings(self, text, model=None):
        """
        Get embeddings for text using OpenAI embeddings API.
        
        Args:
            text (str or list): Text(s) to embed
            model (str): Embedding model to use
            
        Returns:
            list: Embedding vectors
        """
        if not self.openai_client:
            raise ValueError("OpenAI client not available for embeddings. Please set OPENAI_API_KEY in .env file.")
        
        try:
            model_to_use = model or self.embedding_model or 'text-embedding-3-large'
            
            # Handle both single text and list of texts
            if isinstance(text, str):
                text = [text]
            
            response = self.openai_client.embeddings.create(
                model=model_to_use,
                input=text
            )
            
            # Return embeddings as list of vectors
            if len(text) == 1:
                return response.data[0].embedding
            else:
                return [item.embedding for item in response.data]
            
        except Exception as e:
            logger.error(f"Error in {self.agent_name} OpenAI embeddings call: {str(e)}")
            raise
    
    def _call_llm_for_reasoning(self, prompt, system_prompt=None, temperature=0.3, max_tokens=2000):
        """
        Call LLM optimized for reasoning and Q&A tasks.
        Uses Groq API for Q&A.
        
        Args:
            prompt (str): User prompt/question
            system_prompt (str): System prompt for context
            temperature (float): Lower temperature for more focused reasoning
            max_tokens (int): Maximum tokens in response
            
        Returns:
            str: LLM response text
        """
        # Use Groq for Q&A
        return self._call_groq_qa(prompt, system_prompt, temperature, max_tokens)
    
    def _call_groq_qa(self, prompt, system_prompt=None, temperature=0.3, max_tokens=2000):
        """
        Call Groq API for Q&A tasks.
        
        Args:
            prompt (str): User prompt/question
            system_prompt (str): System prompt for context
            temperature (float): Sampling temperature
            max_tokens (int): Maximum tokens in response
            
        Returns:
            str: LLM response text
        """
        try:
            messages = []
            
            if system_prompt:
                messages.append({
                    "role": "system",
                    "content": system_prompt
                })
            
            messages.append({
                "role": "user",
                "content": prompt
            })
            
            response = self.groq_client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"Error in {self.agent_name} Groq Q&A call: {str(e)}")
            raise
    
    def _call_llm_for_writing(self, prompt, system_prompt=None, temperature=0.7, max_tokens=4000):
        """
        Call LLM optimized for document writing tasks.
        Uses GPT-4 Turbo for better writing quality.
        
        Args:
            prompt (str): Writing prompt
            system_prompt (str): System prompt for context
            temperature (float): Higher temperature for more creative writing
            max_tokens (int): Maximum tokens in response (higher for documents)
            
        Returns:
            str: LLM response text
        """
        # Use GPT-4 Turbo for writing (or gpt-4.1 if available)
        writing_model = getattr(settings, 'OPENAI_WRITING_MODEL', 'gpt-4.1')
        return self._call_llm(prompt, system_prompt, temperature, max_tokens, model=writing_model)
    
    def log_action(self, action, details=None):
        """
        Log agent actions for debugging and monitoring.
        
        Args:
            action (str): Action description
            details (dict): Additional details
        """
        logger.info(f"{self.agent_name}: {action}")
        if details:
            logger.debug(f"{self.agent_name} details: {details}")
    
    def validate_input(self, **kwargs):
        """
        Validate input parameters. Override in subclasses.
        
        Args:
            **kwargs: Input parameters to validate
            
        Returns:
            bool: True if valid, False otherwise
        """
        return True
    
    def process(self, **kwargs):
        """
        Main processing method. Must be implemented by subclasses.
        
        Args:
            **kwargs: Agent-specific parameters
            
        Returns:
            dict: Processing results
        """
        raise NotImplementedError("Subclasses must implement process() method")

