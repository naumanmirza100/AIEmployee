"""
Base Agent Class for AI Project Manager
All AI agents inherit from this base class
"""

try:
    from groq import Groq
except ImportError:
    raise ImportError("groq library not installed. Run: pip install --upgrade groq")

from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class BaseAgent:
    """
    Base class for all AI agents in the Project Manager system.
    Provides common functionality like Groq API integration and logging.
    """
    
    def __init__(self, model=None):
        """
        Initialize the base agent with Groq API client.
        
        Args:
            model (str): Groq model to use. Defaults to settings.GROQ_MODEL
        """
        self.api_key = getattr(settings, 'GROQ_API_KEY', None)
        if not self.api_key:
            raise ValueError("GROQ_API_KEY not found in environment variables. Please set it in .env file.")
        
        try:
            # Simple initialization - just pass api_key
            # Some versions of groq may have issues with extra arguments
            self.client = Groq(api_key=self.api_key)
        except TypeError as e:
            error_msg = str(e)
            if 'proxies' in error_msg or 'unexpected keyword' in error_msg:
                # This usually means the groq library version is incompatible
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
        
        self.model = model or getattr(settings, 'GROQ_MODEL', 'llama-3.1-8b-instant')
        self.agent_name = self.__class__.__name__
        # Store last token usage from Groq API calls (if available)
        # Shape: {"prompt_tokens": int, "completion_tokens": int, "total_tokens": int}
        self.last_llm_usage = None
    
    def _call_llm(self, prompt, system_prompt=None, temperature=0.7, max_tokens=1024):
        """
        Make a call to the Groq LLM API.
        
        Args:
            prompt (str): User prompt/question
            system_prompt (str): System prompt for context
            temperature (float): Sampling temperature (0-1)
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
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            # Capture token usage information if the client provides it
            usage_info = getattr(response, "usage", None)
            usage_dict = None
            if usage_info is not None:
                try:
                    # usage might be a dict-like or an object with attributes
                    prompt_tokens = getattr(usage_info, "prompt_tokens", None)
                    completion_tokens = getattr(usage_info, "completion_tokens", None)
                    total_tokens = getattr(usage_info, "total_tokens", None)
                    # If it's a plain dict, getattr will return None; fall back to dict access
                    if isinstance(usage_info, dict):
                        prompt_tokens = usage_info.get("prompt_tokens", prompt_tokens)
                        completion_tokens = usage_info.get("completion_tokens", completion_tokens)
                        total_tokens = usage_info.get("total_tokens", total_tokens)
                    usage_dict = {
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "total_tokens": total_tokens,
                    }
                except Exception:
                    usage_dict = None
            
            self.last_llm_usage = usage_dict
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"Error in {self.agent_name} LLM call: {str(e)}")
            raise
    
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

