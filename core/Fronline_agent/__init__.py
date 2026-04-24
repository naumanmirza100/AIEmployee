"""DEPRECATED legacy alias for ``core.Frontline_agent``.

The original directory was misspelled (missing 't'). All real code now lives
under ``core/Frontline_agent/`` — this module remaps itself in ``sys.modules``
onto that package so every existing import such as
``from core.Fronline_agent.services import KnowledgeService`` keeps working
without editing callers.

New code should import ``core.Frontline_agent`` directly. Expect a
``DeprecationWarning`` from this shim; grep for ``core.Fronline_agent`` to
find remaining call sites to migrate.
"""
import sys
import warnings

warnings.warn(
    "core.Fronline_agent is a deprecated alias — use core.Frontline_agent instead.",
    DeprecationWarning, stacklevel=2,
)

# Import the correctly-spelled package, then alias both the package and every
# submodule under the misspelled namespace so that `isinstance` / `is` checks
# stay consistent regardless of which spelling a caller imports from.
from core import Frontline_agent as _real  # noqa: E402
from core.Frontline_agent import (  # noqa: E402,F401
    database_service, embedding_service, frontline_agent, logging_config,
    prompt_safety, prompts, rules, services, urls, views,
)

_SUBMODULES = {
    'database_service': database_service,
    'embedding_service': embedding_service,
    'frontline_agent': frontline_agent,
    'logging_config': logging_config,
    'prompt_safety': prompt_safety,
    'prompts': prompts,
    'rules': rules,
    'services': services,
    'urls': urls,
    'views': views,
}
for _name, _mod in _SUBMODULES.items():
    sys.modules[f'core.Fronline_agent.{_name}'] = _mod

sys.modules[__name__] = _real
