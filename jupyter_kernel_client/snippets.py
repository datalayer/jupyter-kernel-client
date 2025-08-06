# Copyright (c) 2023-2024 Datalayer, Inc.
#
# BSD 3-Clause License

"""Kernel language dependent code snippets."""

import warnings
from dataclasses import dataclass


@dataclass(frozen=True)
class LanguageSnippets:
    """Per kernel language snippets."""

    list_variables: str
    """Snippet to list kernel variables.

    Its execution must return an output of 'application/json' mimetype with
    a list of variables definition according to the schema:

    {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "name": {"title": "Variable name", "type": "string"},
                "type": {
                    "title": "Variable type",
                    "type": "array",
                    "prefixItems": [
                        {"title": "Type module", "oneOf": [{"type": "string"}, {"type": "null"}]},
                        {"title": "Type name", "type": "string"}
                    ]
                },
                "size": {
                    "title": "Variable size in bytes.",
                    "oneOf": [{"type": "number"}, {"type": "null"}]
                }
            },
            "required": ["name", "type", "size"]
        }
    }
    """
    get_variable: str
    """Snippet to get a kernel variable value.

    The snippet will be formatted with the variables:
    - ``name``: Variable name

    Its execution must return the variable value.
    """
    set_variable: str
    """Snippet to set a kernel variable value.

    The snippet will be formatted with the variables:
    - ``name``: Variable name
    - ``value``: b64 encoded string
    """
    get_variable_mimetypes: str
    """Snippet to get a kernel variable available mimetypes.

    The snippet will be formatted with the variables:
    - ``name``: Variable name
    - ``mimetype``: Wanted mimetype for the variable; default ``None``, i.e. unspecified format.

    Its execution must return a ``data`` dictionary and a ``metadata`` dictionary where the keys
    of the ``data`` dictionary correspond to the available mimetypes.
    """


class SnippetsRegistry:
    """Registry for kernel language dependent code snippets."""

    def __init__(self):
        self._snippets: dict[str, LanguageSnippets] = {}

    @property
    def available_languages(self) -> frozenset[str]:
        """List the available languages."""
        return frozenset(self._snippets)

    def register(self, language: str, snippets: LanguageSnippets) -> None:
        """Register snippets for a new language.

        Args:
            language: Language name (as known by the Jupyter kernel)
            snippets: Language snippets
        """
        if language in self._snippets:
            warnings.warn(f"Snippets for language {language} will be overridden.", stacklevel=2)
        self._snippets[language] = snippets

    def get_list_variables(self, language: str) -> str:
        """Get list variables snippet for the given language.

        Args:
            language: the targeted programming language
        Returns:
            The list variables snippet
        Raises:
            ValueError: if no snippet is defined for ``language``
        """
        if language not in self._snippets:
            raise ValueError(f"No snippet for language '{language}'.")

        return self._snippets[language].list_variables

    def get_get_variable(self, language: str) -> str:
        """Get get variable snippet for the given language.

        Args:
            language: the targeted programming language
        Returns:
            The get variable snippet
        Raises:
            ValueError: if no snippet is defined for ``language``
        """
        if language not in self._snippets:
            raise ValueError(f"No snippet for language '{language}'.")

        return self._snippets[language].get_variable

    def get_set_variable(self, language: str) -> str:
        """Get set variable snippet for the given language.

        Args:
            language: the targeted programming language
        Returns:
            The get variable snippet
        Raises:
            ValueError: if no snippet is defined for ``language``
        """
        if language not in self._snippets:
            raise ValueError(f"No snippet for language '{language}'.")

        return self._snippets[language].set_variable

    def get_get_variable_mimetypes(self, language: str) -> str:
        """Get get variable mimetypes snippet for the given language.

        Args:
            language: the targeted programming language
        Returns:
            The get variable mimetypes snippet
        Raises:
            ValueError: if no snippet is defined for ``language``
        """
        if language not in self._snippets:
            raise ValueError(f"No snippet for language '{language}'.")

        return self._snippets[language].get_variable_mimetypes


PYTHON_SNIPPETS = LanguageSnippets(
    list_variables="""def ___list_variables():
    from IPython.display import display
    import json
    from types import BuiltinFunctionType, BuiltinMethodType, FunctionType, MethodType, MethodWrapperType, ModuleType, TracebackType

    _FORBIDDEN_TYPES = [type, BuiltinFunctionType, BuiltinMethodType, FunctionType, MethodType, MethodWrapperType, ModuleType, TracebackType]
    try:
        from IPython.core.autocall import ExitAutocall
        _FORBIDDEN_TYPES.append(ExitAutocall)
    except ImportError:
        pass
    _exclude = tuple(_FORBIDDEN_TYPES)

    _all = frozenset(globals())
    _vars = []
    for _n in _all:
        _v = globals()[_n]

        if not (
            _n.startswith('_') or
            isinstance(_v, _exclude) or
            # Special IPython variables
            (_n == 'In' and isinstance(_v, list)) or
            (_n == 'Out' and isinstance(_v, dict))
        ):
            try:
                variable_type = type(_v)
                _vars.append(
                    {
                        "name": _n,
                        "type": (
                            getattr(variable_type, "__module__", None),
                            variable_type.__qualname__
                        ),
                        "size": None,
                    }
                )
            except BaseException as e:
                print(e)

    display({"application/json": _vars}, raw=True)

___list_variables()
""",  # noqa E501
    get_variable="""from jupyter_mimetypes import get_variable as ___get_variable
___get_variable("{name}", None, globals_dict=globals())
""",
    set_variable="""from jupyter_mimetypes import set_variable as ___set_variable

___data = {data!r}
___metadata = {metadata!r}
___set_variable(name="{name}", data=___data, metadata=___metadata, globals_dict=globals())
del(___data)
del(___metadata)
""",
    get_variable_mimetypes="""def ___get_variable_mimetypes(name, mimetype):
    from IPython.display import display

    variable = globals()[name]
    include = None if mimetype is None else [mimetype]
    display(variable, include=include)
___get_variable_mimetypes("{name}", "{mimetype}" if "{mimetype}" != "None" else None)
""",
)

SNIPPETS_REGISTRY = SnippetsRegistry()
SNIPPETS_REGISTRY.register("python", PYTHON_SNIPPETS)
