"""The ``SourceSpec`` contract.

This module is the seam of the whole system. Everything upstream (natural
language, the LLM, the clarification loop) exists to produce a ``SourceSpec``;
everything downstream (templates, validation, docs, artifacts) consumes one.
Neither side knows about the other.

Two models, deliberately:

* :class:`SpecDraft` — what the model emits. Every field optional. A draft is
  allowed to be incomplete, because "incomplete" is exactly the signal the
  clarification loop needs.
* :class:`SourceSpec` — strict and complete. Constructing one is the proof that
  extraction succeeded. Phase 3 templates accept nothing else.

Keeping them separate means a half-understood prompt can never leak into code
generation as a set of plausible-looking defaults.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# --- Enumerations -----------------------------------------------------------


import json
from pathlib import Path

_sources_path = Path(__file__).parent.parent / "sources.json"
with open(_sources_path) as _f:
    _sources_data = json.load(_f)

SourceType = StrEnum("SourceType", {k.upper(): k for k in _sources_data.keys()})

def _is_sql(self) -> bool:
    return _sources_data[self.value].get("is_sql", True)

def _default_port(self) -> int | None:
    return _sources_data[self.value].get("default_port")

SourceType.is_sql = property(_is_sql)
SourceType.default_port = property(_default_port)


class AuthMethod(StrEnum):
    """Authentication methods, spanning both SQL and REST."""

    USERNAME_PASSWORD = "username_password"  # noqa: S105 - method name, not a secret
    API_KEY_HEADER = "api_key_header"
    BEARER_TOKEN = "bearer_token"  # noqa: S105 - method name, not a secret
    BASIC = "basic"
    OAUTH2_CLIENT_CREDENTIALS = "oauth2_client_credentials"
    NONE = "none"

    @property
    def valid_for_sql(self) -> bool:
        return self is AuthMethod.USERNAME_PASSWORD

    @property
    def secret_fields(self) -> tuple[str, ...]:
        """Which secrets this method needs, as env var suffixes."""
        return {
            AuthMethod.USERNAME_PASSWORD: ("USERNAME", "PASSWORD"),
            AuthMethod.API_KEY_HEADER: ("API_KEY",),
            AuthMethod.BEARER_TOKEN: ("TOKEN",),
            AuthMethod.BASIC: ("USERNAME", "PASSWORD"),
            AuthMethod.OAUTH2_CLIENT_CREDENTIALS: ("CLIENT_ID", "CLIENT_SECRET"),
            AuthMethod.NONE: (),
        }[self]


class PaginationStyle(StrEnum):
    """How a REST source pages through results."""

    NONE = "none"
    OFFSET_LIMIT = "offset_limit"
    PAGE_NUMBER = "page_number"
    CURSOR = "cursor"
    LINK_HEADER = "link_header"


# --- Validators shared across models ----------------------------------------

_CONNECTOR_NAME = re.compile(r"^[A-Z][A-Za-z0-9]*Connector$")
_SLUG = re.compile(r"^[a-z][a-z0-9_]*$")
_ENV_PREFIX = re.compile(r"^[A-Z][A-Z0-9_]*_$")

#: Patterns that suggest the prompt is trying to steer the agent rather than
#: describe a data source. A spec field is data, never instruction.
_INJECTION_MARKERS = (
    "ignore previous",
    "ignore all previous",
    "disregard the above",
    "system prompt",
    "you are now",
    "new instructions",
    "</system>",
    "<|im_start|>",
)


def _reject_injection(value: str, field_name: str) -> str:
    lowered = value.lower()
    for marker in _INJECTION_MARKERS:
        if marker in lowered:
            raise ValueError(
                f"{field_name} contains instruction-like content ({marker!r}); "
                "spec fields describe a source, they do not direct the agent"
            )
    return value


def slugify(text: str) -> str:
    """Turn arbitrary text into a safe identifier fragment."""
    slug = re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")
    slug = re.sub(r"_+", "_", slug)
    if not slug:
        return "source"
    if slug[0].isdigit():
        slug = f"s_{slug}"
    return slug


# --- Target models ----------------------------------------------------------


class SqlTarget(BaseModel):
    """Where a SQL source lives."""

    model_config = ConfigDict(extra="forbid")

    host: str = Field(..., min_length=1, max_length=253)
    port: int = Field(..., ge=1, le=65535)
    database: str = Field(..., min_length=1, max_length=128)
    schema_name: str | None = Field(default=None, max_length=128)

    @field_validator("host")
    @classmethod
    def _clean_host(cls, value: str) -> str:
        value = value.strip()
        if "://" in value:
            raise ValueError("host must be a hostname, not a URL")
        if "@" in value or " " in value:
            raise ValueError("host must not contain credentials or whitespace")
        return value


class RestTarget(BaseModel):
    """Where a REST source lives and how it pages."""

    model_config = ConfigDict(extra="forbid")

    base_url: str = Field(..., min_length=1, max_length=2048)
    default_path: str = "/"
    pagination: PaginationStyle = PaginationStyle.NONE
    page_size: int | None = Field(default=None, ge=1, le=10_000)
    rate_limit_per_minute: int | None = Field(default=None, ge=1)

    @field_validator("base_url")
    @classmethod
    def _require_https_scheme(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if not value.startswith(("http://", "https://")):
            raise ValueError("base_url must include a scheme")
        if "@" in value.split("//", 1)[1].split("/", 1)[0]:
            raise ValueError("base_url must not embed credentials")
        return value

    @model_validator(mode="after")
    def _page_size_needs_pagination(self) -> Self:
        if self.page_size is not None and self.pagination is PaginationStyle.NONE:
            raise ValueError("page_size is meaningless when pagination is 'none'")
        return self


class AuthSpec(BaseModel):
    """How to authenticate, expressed as *names of environment variables*.

    No secret value is ever stored here. The spec records where a credential
    will be found at runtime, which is what lets the generated connector satisfy
    the no-hardcoded-credentials standard by construction.
    """

    model_config = ConfigDict(extra="forbid")

    method: AuthMethod
    env_prefix: str = Field(..., max_length=64)
    header_name: str | None = Field(default=None, max_length=64)
    token_url: str | None = Field(default=None, max_length=2048)
    scopes: tuple[str, ...] = ()

    @field_validator("env_prefix")
    @classmethod
    def _check_prefix(cls, value: str) -> str:
        value = value.strip().upper()
        if not value.endswith("_"):
            value += "_"
        if not _ENV_PREFIX.match(value):
            raise ValueError("env_prefix must be UPPER_SNAKE and end with an underscore")
        return value

    @model_validator(mode="after")
    def _method_requirements(self) -> Self:
        if self.method is AuthMethod.API_KEY_HEADER and not self.header_name:
            raise ValueError("api_key_header requires header_name")
        if self.method is AuthMethod.OAUTH2_CLIENT_CREDENTIALS and not self.token_url:
            raise ValueError("oauth2_client_credentials requires token_url")
        return self

    @property
    def secret_env_vars(self) -> tuple[str, ...]:
        """The exact variables the generated connector will read."""
        return tuple(f"{self.env_prefix}{suffix}" for suffix in self.method.secret_fields)


class ConnectorOptions(BaseModel):
    """Tuning knobs the template renders into the generated connector."""

    model_config = ConfigDict(extra="forbid")

    read_only: bool = True
    connect_timeout_seconds: int = Field(default=10, ge=1, le=300)
    query_timeout_seconds: int = Field(default=30, ge=1, le=3600)
    pool_size: int = Field(default=5, ge=1, le=100)
    max_retries: int = Field(default=3, ge=1, le=10)
    ssl_mode: str = "prefer"
    verify_tls: bool = True


# --- The specs --------------------------------------------------------------


class SourceSpec(BaseModel):
    """A complete, validated description of one data source.

    If you can build one of these, you know enough to generate a connector.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_type: SourceType
    connector_name: str
    slug: str
    description: str = Field(default="", max_length=500)
    sql_target: SqlTarget | None = None
    rest_target: RestTarget | None = None
    auth: AuthSpec
    options: ConnectorOptions = Field(default_factory=ConnectorOptions)
    tags: tuple[str, ...] = ()

    @field_validator("connector_name")
    @classmethod
    def _check_name(cls, value: str) -> str:
        if not _CONNECTOR_NAME.match(value):
            raise ValueError(
                "connector_name must be PascalCase ending in 'Connector', " f"got {value!r}"
            )
        return value

    @field_validator("slug")
    @classmethod
    def _check_slug(cls, value: str) -> str:
        if not _SLUG.match(value):
            raise ValueError(f"slug must be lower_snake_case, got {value!r}")
        return value

    @field_validator("description")
    @classmethod
    def _clean_description(cls, value: str) -> str:
        return _reject_injection(value, "description")

    @model_validator(mode="after")
    def _target_matches_source_type(self) -> Self:
        if self.source_type.is_sql:
            if self.sql_target is None:
                raise ValueError(f"{self.source_type} requires sql_target")
            if self.rest_target is not None:
                raise ValueError("sql source must not carry rest_target")
            if not self.auth.method.valid_for_sql:
                raise ValueError(f"{self.auth.method} is not a valid auth method for a SQL source")
        else:
            if self.rest_target is None:
                raise ValueError("rest_api requires rest_target")
            if self.sql_target is not None:
                raise ValueError("rest source must not carry sql_target")
        return self

    @property
    def module_name(self) -> str:
        """Filename the generated connector is written to."""
        return f"{self.slug}_connector.py"

    @property
    def template_key(self) -> str:
        """Registry lookup key for Phase 3."""
        return f"{self.source_type.value}:{self.auth.method.value}"


class SpecDraft(BaseModel):
    """A partially-understood source description.

    This is the LLM's output type. Everything is optional so the model is never
    forced to invent a value it did not read — the single most common failure
    mode in NL-to-structure extraction, and the one the clarification loop
    exists to catch.
    """

    model_config = ConfigDict(extra="ignore")

    source_type: SourceType | None = None
    connector_name: str | None = None
    slug: str | None = None
    description: str = ""
    host: str | None = None
    port: int | None = None
    database: str | None = None
    schema_name: str | None = None
    base_url: str | None = None
    default_path: str | None = None
    pagination: PaginationStyle | None = None
    page_size: int | None = None
    auth_method: AuthMethod | None = None
    env_prefix: str | None = None
    header_name: str | None = None
    token_url: str | None = None
    read_only: bool | None = None
    tags: tuple[str, ...] = ()

    #: Fields the model filled from convention rather than from the prompt.
    #: Surfaced in the UI so a reviewer can see what was assumed.
    assumed_fields: tuple[str, ...] = ()

    def required_fields(self) -> tuple[str, ...]:
        """Which fields must be present, given what is known so far."""
        if self.source_type is None:
            return ("source_type",)
        base = ("connector_name", "auth_method")
        if self.source_type.is_sql:
            return (*base, "host", "database")
        return (*base, "base_url")

    def missing_required(self) -> tuple[str, ...]:
        """Required fields still unset. Drives the clarification loop."""
        return tuple(name for name in self.required_fields() if getattr(self, name, None) is None)

    @property
    def is_complete(self) -> bool:
        return not self.missing_required()

    def merge(self, **updates: Any) -> SpecDraft:
        """Return a new draft with non-``None`` updates applied."""
        clean = {k: v for k, v in updates.items() if v is not None}
        return self.model_copy(update=clean)

    def apply_defaults(self) -> SpecDraft:
        """Fill conventional values, recording each one in ``assumed_fields``.

        Only ever called on fields that are safe to assume — a default port is
        a convention, a hostname is not. Anything genuinely unknowable stays
        ``None`` so the clarification loop still asks about it.
        """
        assumed = list(self.assumed_fields)
        updates: dict[str, Any] = {}

        if self.source_type is not None:
            if self.port is None and self.source_type.default_port:
                updates["port"] = self.source_type.default_port
                assumed.append("port")
            if self.auth_method is None and self.source_type.is_sql:
                updates["auth_method"] = AuthMethod.USERNAME_PASSWORD
                assumed.append("auth_method")
            if self.schema_name is None and self.source_type is SourceType.POSTGRESQL:
                updates["schema_name"] = "public"
                assumed.append("schema_name")

        base = self.slug or (self.database or self.connector_name or "")
        if self.slug is None and base:
            updates["slug"] = slugify(base)
            assumed.append("slug")

        if self.read_only is None:
            updates["read_only"] = True
            assumed.append("read_only")

        if self.env_prefix is None:
            slug = updates.get("slug") or self.slug
            if slug:
                updates["env_prefix"] = f"DSOA_{slug.upper()}_"
                assumed.append("env_prefix")

        updates["assumed_fields"] = tuple(dict.fromkeys(assumed))
        return self.model_copy(update=updates)

    def finalize(self, options: ConnectorOptions | None = None) -> SourceSpec:
        """Promote a complete draft to a strict :class:`SourceSpec`.

        Raises:
            ValueError: if required fields are missing or the combination is
                invalid. Callers should check :attr:`is_complete` first.
        """
        missing = self.missing_required()
        if missing:
            raise ValueError(f"Draft is incomplete; missing {', '.join(missing)}")

        assert self.source_type is not None
        assert self.auth_method is not None
        assert self.connector_name is not None

        filled = self.apply_defaults()
        opts = options or ConnectorOptions()
        if filled.read_only is not None:
            opts = opts.model_copy(update={"read_only": filled.read_only})

        sql_target = None
        rest_target = None
        if self.source_type.is_sql:
            sql_target = SqlTarget(
                host=filled.host or "",
                port=filled.port or self.source_type.default_port or 0,
                database=filled.database or "",
                schema_name=filled.schema_name,
            )
        else:
            rest_target = RestTarget(
                base_url=filled.base_url or "",
                default_path=filled.default_path or "/",
                pagination=filled.pagination or PaginationStyle.NONE,
                page_size=filled.page_size,
            )

        return SourceSpec(
            source_type=self.source_type,
            connector_name=self.connector_name,
            slug=filled.slug or slugify(self.connector_name),
            description=self.description,
            sql_target=sql_target,
            rest_target=rest_target,
            auth=AuthSpec(
                method=self.auth_method,
                env_prefix=filled.env_prefix or "DSOA_",
                header_name=filled.header_name,
                token_url=filled.token_url,
            ),
            options=opts,
            tags=self.tags,
        )
