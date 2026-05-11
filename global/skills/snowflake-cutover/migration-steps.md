# Migration Steps — Snowflake Cutover

## Step 1: Discover current Snowflake connection code

Search the project for:
```
grep -r "snowflake.connector.connect" --include="*.py"
grep -r "SNOWFLAKE_ACCOUNT\|SNOWFLAKE_USER" --include="*.py"
grep -r "class.*Connection.*Manager\|class.*Snowflake.*Service" --include="*.py"
grep -r "class.*Settings\|BaseSettings" --include="*.py"
```

Identify:
- [ ] Where connections are established
- [ ] How credentials are configured (Settings class? env vars? config file?)
- [ ] **Whether a central Settings/config class manages Snowflake credentials** (e.g., Pydantic `BaseSettings`, dataclass, or similar). This is critical — if one exists, the adapter MUST read from it, not bypass it with `from_env()`.
- [ ] All call sites that pass settings/credentials to connection code
- [ ] Test files that mock connection parameters

## Step 2: Check if artemis-python-tools is already a dependency

```
grep -r "artemis.python.tools\|artemis_python_tools" pyproject.toml setup.py requirements*.txt
```

If not present, install with `--no-deps` to avoid transitive dependency conflicts:
```
pip install --no-deps "artemis-python-tools @ git+https://github.com/Artemis-xyz/artemis-python-tools.git"
```

Add to build command (Railway, Dockerfile, etc.) — NOT to pyproject.toml deps
(artemis-python-tools pins fastapi==0.115.12 which conflicts with most projects).

## Step 3: Create credentials adapter

**Important:** If the project has a central Settings/config class that already manages Snowflake
credentials, the adapter MUST accept that Settings object and map its fields to
`SnowflakeCredentials`. Do NOT bypass existing settings management with `from_env()` — that
would create a parallel config path and break the project's single source of truth for secrets.

Create a new file (e.g., `<project>/snowflake/credentials.py`).

### Pattern A: Project has a central Settings class (preferred)

Use this when Step 1 found a Settings class (Pydantic BaseSettings, dataclass, etc.)
that already holds Snowflake fields. The adapter takes Settings as input and maps fields
to `SnowflakeCredentials`:

```python
"""Snowflake credentials adapter using artemis-python-tools."""
from __future__ import annotations

import logging

from artemis_python_tools.snowflake_query_plan_visualizer.connection import (
    SnowflakeCredentials,
    get_connection as _apt_get_connection,
)

logger = logging.getLogger(__name__)


def get_snowflake_credentials(settings) -> SnowflakeCredentials:
    """Build SnowflakeCredentials from the project's Settings object.

    Preserves the project's existing settings/secrets management as the
    single source of truth. Supports raw PEM content in settings for
    deployments where key files aren't on disk.
    """
    creds = SnowflakeCredentials(
        account=settings.snowflake_account or "",
        user=settings.snowflake_user or "",
        password=settings.snowflake_password,
        private_key_file=settings.snowflake_private_key_file,
        private_key_passphrase=settings.snowflake_private_key_passphrase,
        warehouse=settings.snowflake_warehouse,
        database=settings.snowflake_database,
        role=settings.snowflake_role,
        authenticator=settings.snowflake_authenticator,
    )

    # Handle raw PEM content (e.g., Railway env var with full key)
    pem_content = getattr(settings, "snowflake_private_key", None)
    if pem_content:
        from cryptography.hazmat.primitives import serialization

        private_key = serialization.load_pem_private_key(
            pem_content.encode(),
            password=(
                settings.snowflake_private_key_passphrase.encode()
                if settings.snowflake_private_key_passphrase
                else None
            ),
        )
        creds.private_key = private_key.private_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        creds.private_key_file = None

    return creds


def create_snowflake_connection(settings):
    """Create a Snowflake connection using centralized credentials."""
    creds = get_snowflake_credentials(settings)
    logger.info("Connecting to Snowflake (account=%s, user=%s)", creds.account, creds.user)
    return _apt_get_connection(creds)
```

Adapt the field names (`settings.snowflake_account`, etc.) to match the project's actual
Settings class attributes. If the Settings class uses `validation_alias` (Pydantic v2) to
map `SYSTEM_SNOWFLAKE_*` env vars to Python field names, map from the Python attribute names.

### Pattern B: No central Settings class (simple projects)

Use this only when the project reads env vars directly with no Settings abstraction:

```python
"""Snowflake credentials adapter using artemis-python-tools."""
from __future__ import annotations

import logging
import os

from artemis_python_tools.snowflake_query_plan_visualizer.connection import (
    SnowflakeCredentials,
    get_connection as _apt_get_connection,
)

logger = logging.getLogger(__name__)


def get_snowflake_credentials() -> SnowflakeCredentials:
    """Create SnowflakeCredentials from SYSTEM_SNOWFLAKE_* env vars.

    Supports SYSTEM_SNOWFLAKE_PRIVATE_KEY (raw PEM content in env var)
    for deployments where key files aren't on disk.
    """
    pem_content = os.environ.get("SYSTEM_SNOWFLAKE_PRIVATE_KEY")

    if pem_content:
        from cryptography.hazmat.primitives import serialization

        passphrase = os.environ.get("SYSTEM_SNOWFLAKE_PRIVATE_KEY_PASSPHRASE")
        private_key = serialization.load_pem_private_key(
            pem_content.encode(),
            password=passphrase.encode() if passphrase else None,
        )
        der_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        creds = SnowflakeCredentials.from_env()
        creds.private_key = der_bytes
        creds.private_key_file = None
        return creds

    return SnowflakeCredentials.from_env()


def create_snowflake_connection():
    """Create a Snowflake connection using centralized credentials."""
    creds = get_snowflake_credentials()
    logger.info("Connecting to Snowflake (account=%s, user=%s)", creds.account, creds.user)
    return _apt_get_connection(creds)
```

## Step 4: Refactor connection code

Replace all `_build_connection_params()` / `_configure_authentication()` methods
with calls to `create_snowflake_connection()`.

**If using Pattern A** (Settings class), pass the settings instance through:

Before:
```python
conn_params = self._build_connection_params()
self.conn = snowflake.connector.connect(**conn_params)
```

After:
```python
from <project>.snowflake.credentials import create_snowflake_connection
self.conn = create_snowflake_connection(self._settings)
```

If a caller doesn't already have a settings reference, import the project's settings
getter (e.g., `get_settings()`) rather than constructing a new Settings instance.

**If using Pattern B** (no Settings class):

```python
from <project>.snowflake.credentials import create_snowflake_connection
self.conn = create_snowflake_connection()
```

### What to remove

- Remove `_build_connection_params()`, `_configure_authentication()`, and similar methods
  that constructed `snowflake.connector.connect()` kwargs manually
- Remove local credential validation logic (e.g., "if no password and no key, raise error")
  — artemis-python-tools handles this at connection time
- If the project has a SecretsManager or similar that validated Snowflake credentials
  separately, simplify it to delegate to artemis-python-tools

## Step 5: Rename env vars

| Old Name | New Name |
|----------|----------|
| `SNOWFLAKE_ACCOUNT` | `SYSTEM_SNOWFLAKE_ACCOUNT` |
| `SNOWFLAKE_USER` | `SYSTEM_SNOWFLAKE_USER` |
| `SNOWFLAKE_PASSWORD` | `SYSTEM_SNOWFLAKE_PASSWORD` |
| `SNOWFLAKE_WAREHOUSE` | `SYSTEM_SNOWFLAKE_WAREHOUSE` |
| `SNOWFLAKE_ROLE` | `SYSTEM_SNOWFLAKE_ROLE` |
| `SNOWFLAKE_DATABASE` | `SYSTEM_SNOWFLAKE_DATABASE` |
| `SNOWFLAKE_SCHEMA` | `SYSTEM_SNOWFLAKE_SCHEMA` |
| `SNOWFLAKE_AUTHENTICATOR` | `SYSTEM_SNOWFLAKE_AUTHENTICATOR` |
| *(new)* | `SYSTEM_SNOWFLAKE_PRIVATE_KEY` |
| *(new)* | `SYSTEM_SNOWFLAKE_PRIVATE_KEY_FILE` |
| *(new)* | `SYSTEM_SNOWFLAKE_PRIVATE_KEY_PASSPHRASE` |

**If using Pattern A (Settings class):** Update the Settings class field aliases or
`validation_alias` values to read from the new `SYSTEM_SNOWFLAKE_*` env var names.
For Pydantic v2 `BaseSettings`, use `validation_alias` on each field:
```python
snowflake_account: Optional[str] = Field(
    default=None,
    validation_alias="system_snowflake_account",
)
```
Also add new fields for RSA key support (`snowflake_private_key`,
`snowflake_private_key_file`, `snowflake_private_key_passphrase`) with appropriate
defaults for CI/dev environments where these won't be set.

## Step 6: Update tests

- Mock `create_snowflake_connection` instead of `snowflake.connector.connect`
- Remove tests that validated specific auth methods (now handled by artemis-python-tools)
- Keep tests for connect/disconnect lifecycle, error handling

## Step 7: Deploy

1. Add new `SYSTEM_SNOWFLAKE_*` env vars to deployment platform BEFORE deploying code
2. Deploy code changes
3. Verify: health check, Snowflake operations work
4. Remove old `SNOWFLAKE_*` env vars

## Snowflake Service Account Setup

For RSA key-pair auth, the service account needs:
```sql
ALTER USER SERVICE_<PROJECT> SET RSA_PUBLIC_KEY='<public key content>';
GRANT ROLE <ROLE> TO USER SERVICE_<PROJECT>;
ALTER USER SERVICE_<PROJECT> SET DEFAULT_WAREHOUSE = '<WAREHOUSE>';
```

## Verification

```bash
# Local dev (externalbrowser)
export SYSTEM_SNOWFLAKE_ACCOUNT=<account>
export SYSTEM_SNOWFLAKE_USER=<email>
export SYSTEM_SNOWFLAKE_AUTHENTICATOR=externalbrowser
export SYSTEM_SNOWFLAKE_WAREHOUSE=<warehouse>

# Local dev (key-pair)
export SYSTEM_SNOWFLAKE_ACCOUNT=<account>
export SYSTEM_SNOWFLAKE_USER=SERVICE_<PROJECT>
export SYSTEM_SNOWFLAKE_PRIVATE_KEY_FILE=/path/to/rsa_key.p8
export SYSTEM_SNOWFLAKE_WAREHOUSE=<warehouse>
export SYSTEM_SNOWFLAKE_ROLE=<role>
```
