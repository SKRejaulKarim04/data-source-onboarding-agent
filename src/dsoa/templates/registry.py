"""Template registry.

Two things live here, and keeping them together is deliberate:

* **Dialect profiles** — the forty lines that actually differ between Postgres,
  MySQL, and SQL Server. Written once, reviewed once, reused by every generation.
* **The versioned registry** — which template renders which ``template_key``,
  at which version.

Versioning matters more than it looks. An artifact generated in March against
template v1.0.0 must remain explicable in October when the template is at
v1.4.0. Recording the version on the artifact is what makes "why does this
connector look different from that one" an answerable question rather than an
argument.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..agent.spec import AuthMethod, SourceType
from ..connectors.exceptions import ConfigurationError


@dataclass(frozen=True)
class DialectProfile:
    """Everything that varies between one SQL dialect and another."""

    label: str
    driver: str
    default_port: int
    version_query: str
    #: ``(keyword, python-expression)`` pairs rendered into ``_connect_args``.
    #: Expressions are template text, not values — they reference ``self.config``
    #: so the generated connector stays configurable at runtime.
    connect_args: tuple[tuple[str, str], ...]
    url_query: dict[str, str] = field(default_factory=dict)
    #: Package needed to actually connect. Rendered into requirements in Phase 5.
    driver_package: str = ""


import json
from pathlib import Path

_sources_path = Path(__file__).parent.parent / "sources.json"
with open(_sources_path) as _f:
    _sources_data = json.load(_f)

DIALECTS: dict[SourceType, DialectProfile] = {}
for source_name, data in _sources_data.items():
    if data.get("is_sql") and "dialect" in data:
        dialect_data = data["dialect"]
        # Convert list of lists to tuple of tuples for connect_args
        connect_args = tuple(tuple(x) for x in dialect_data.get("connect_args", []))
        dialect = DialectProfile(
            label=dialect_data["label"],
            driver=dialect_data["driver"],
            default_port=dialect_data["default_port"],
            version_query=dialect_data["version_query"],
            connect_args=connect_args,
            url_query=dialect_data.get("url_query", {}),
            driver_package=dialect_data.get("driver_package", ""),
        )
        # SourceType members are dynamically created, we can access them by name
        source_enum = getattr(SourceType, source_name.upper())
        DIALECTS[source_enum] = dialect


@dataclass(frozen=True)
class TemplateEntry:
    """One registered, versioned template."""

    key: str
    template_name: str
    version: str
    source_type: SourceType
    auth_method: AuthMethod
    description: str

    @property
    def dialect(self) -> DialectProfile | None:
        return DIALECTS.get(self.source_type)


def _sql_entries() -> list[TemplateEntry]:
    sql_entries = [
        TemplateEntry(
            key=f"{source_type.value}:{AuthMethod.USERNAME_PASSWORD.value}",
            template_name="sql_connector.py.j2",
            version="1.0.0",
            source_type=source_type,
            auth_method=AuthMethod.USERNAME_PASSWORD,
            description=f"{DIALECTS[source_type].label} read connector",
        )
        for source_type in DIALECTS
    ]
    rest_entries = [
        TemplateEntry(
            key=f"{SourceType.REST_API.value}:{AuthMethod.NONE.value}",
            template_name="rest_api_connector.py.j2",
            version="1.0.0",
            source_type=SourceType.REST_API,
            auth_method=AuthMethod.NONE,
            description="REST API read connector with no authentication",
        )
    ]
    return sql_entries + rest_entries


class TemplateRegistry:
    """Lookup from ``SourceSpec.template_key`` to a versioned template."""

    def __init__(self, entries: list[TemplateEntry] | None = None) -> None:
        self._entries: dict[str, TemplateEntry] = {
            entry.key: entry for entry in (entries if entries is not None else _sql_entries())
        }

    def get(self, key: str) -> TemplateEntry:
        """Resolve a template key.

        Raises:
            ConfigurationError: with the supported keys listed, because "no
                template found" without the alternatives is a useless error.
        """
        try:
            return self._entries[key]
        except KeyError:
            raise ConfigurationError(
                f"No template registered for {key!r}",
                supported=sorted(self._entries),
            ) from None

    def supports(self, key: str) -> bool:
        return key in self._entries

    def template_keys(self) -> tuple[str, ...]:
        """Every registered key, sorted."""
        return tuple(sorted(self._entries))

    def register(self, entry: TemplateEntry) -> None:
        """Add or replace an entry. Phase 6 exposes this through the UI."""
        self._entries[entry.key] = entry
