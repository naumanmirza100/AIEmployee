"""
Base Agent Class for AI Agents
All AI agents inherit from this base class
Provides common functionality like Groq API integration and logging.
Compatible with Python 3.11+ (no Python 3.14-only features)
"""

try:
    from groq import Groq
except ImportError:
    Groq = None  # Allow graceful degradation if groq is not installed

from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class BaseAgent:
    """
    Base class for all AI agents in the system.
    Provides common functionality like Groq API integration and logging.
    
    FIX: Enhanced from minimal implementation to full-featured base class
    to support Frontline Agent and other agents that need _call_llm method.
    """
    
    def __init__(self, model=None, company_id=None):
        """
        Initialize the base agent with Groq API client.
        
        Args:
            model (str): Groq model to use. Defaults to settings.GROQ_MODEL
            company_id: Optional company ID for multi-tenant scenarios
        """
        self.company_id = company_id
        self.api_key = getattr(settings, 'GROQ_API_KEY', None)
        
        # Initialize Groq client if available and API key is set
        if Groq and self.api_key:
            try:
                # Simple initialization - just pass api_key
                # Compatible with Python 3.11+
                self.client = Groq(api_key=self.api_key)
            except TypeError as e:
                error_msg = str(e)
                if 'proxies' in error_msg or 'unexpected keyword' in error_msg:
                    logger.error(f"Groq client initialization error: {e}")
                    logger.error("This is usually caused by an outdated groq library version.")
                    logger.error("Please run: pip install --upgrade groq")
                    self.client = None
                else:
                    raise
            except Exception as e:
                logger.error(f"Unexpected error initializing Groq client: {e}")
                self.client = None
        else:
            self.client = None
            if not self.api_key:
                logger.warning("GROQ_API_KEY not found in settings. LLM features will be disabled.")
        
        self.model = model or getattr(settings, 'GROQ_MODEL', 'llama-3.1-8b-instant')
        self.agent_name = self.__class__.__name__
    
    def _call_llm(self, prompt, system_prompt=None, temperature=0.7, max_tokens=1024):
        """
        Make a call to the Groq LLM API.
        
        FIX: Added this method to support Frontline Agent and other agents
        that need LLM functionality.
        
        Args:
            prompt (str): User prompt/question
            system_prompt (str): System prompt for context
            temperature (float): Sampling temperature (0-1)
            max_tokens (int): Maximum tokens in response
            
        Returns:
            str: LLM response text
            
        Raises:
            ValueError: If Groq client is not available
        """
        if not self.client:
            raise ValueError("Groq client not available. Check GROQ_API_KEY in settings.")
        
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
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"Error in {self.agent_name} LLM call: {str(e)}")
            raise
    
    def log(self, message):
        """
        Log agent actions for debugging and monitoring.
        
        Args:
            message (str): Log message
        """
        logger.info(f"[{self.agent_name}] {message}")
    
    def log_action(self, action, details=None):
        """
        Log agent actions with optional details.
        
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
