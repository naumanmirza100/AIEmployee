"""HR Support Agent — service layer.

Lives under `core.HR_agent` to mirror the layout of `core.Frontline_agent`.
The HR Django app (``hr_agent``) holds the data model + Celery tasks + DRF
views; this package holds the AI agent class and shared services
(knowledge retrieval, prompts).
"""
__version__ = '0.1.0'
