"""
MCP data server for the AVS AI Data Agent.

Exposes three read-only tools (list_sources, get_schema, run_query) over MCP
(streamable-http) against any SQL databases declared in sources.yaml. Multi-engine
via SQLAlchemy. Credentials are pulled from Key Vault at runtime using the
container's managed identity. Requests to /mcp are validated as Microsoft Entra
tokens from your Foundry agent.

Environment variables:
  KEY_VAULT_URL          required. https://<vault>.vault.azure.net/
  SQL_USER               fallback DB username if a source omits one (default: agentreader)
  HOST / PORT            listen address (default 0.0.0.0:8000)
  TENANT_ID              Entra tenant used to validate tokens
  ALLOWED_AUDIENCES      comma-separated allowed token audiences (your app registration).
                         If EMPTY, audience validation is DISABLED -- tokens are still
                         checked for signature and issuer, but not for what they were
                         issued for. Set this.
  ALLOWED_CALLERS        comma-separated allowed caller app ids (azp) = your Foundry agent.
                         If EMPTY, the endpoint FAILS CLOSED (503) unless DISCOVERY_MODE
                         is explicitly enabled.
  DISCOVERY_MODE         true/false (default false). Temporarily skips ONLY the caller
                         allow-list so the caller's azp can be logged and copied into
                         ALLOWED_CALLERS. Signature and issuer are still verified (and the
                         audience too, if ALLOWED_AUDIENCES is set). Never leave this on:
                         ingress is internet-facing.
  SQL_TRUST_SERVER_CERT  true/false (default true). Trusts self-signed SQL certificates,
                         which AVS workload VMs typically use. Set false once your
                         databases present a trusted certificate.
  SECRET_TTL_SECONDS     how long Key Vault secrets are cached (default 3600), so a
                         rotated password is picked up without restarting the container.
"""
import fnmatch
import os
import re
import threading
import time

import jwt
import uvicorn
import yaml
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from dotenv import load_dotenv
from jwt import PyJWKClient
from mcp.server.fastmcp import FastMCP
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import URL
from starlette.responses import JSONResponse

load_dotenv()
KEY_VAULT_URL = os.environ["KEY_VAULT_URL"]
SQL_USER = os.getenv("SQL_USER", "agentreader")

# ---- Entra token validation (all env-driven; nothing baked in) --------------
TENANT_ID = os.getenv("TENANT_ID", "")
ALLOWED_AUDIENCES = [a for a in os.getenv("ALLOWED_AUDIENCES", "").split(",") if a]
ALLOWED_CALLERS = {c for c in os.getenv("ALLOWED_CALLERS", "").split(",") if c}
# Discovery must be an explicit, deliberate choice. An unset allow-list must never
# silently mean "allow everyone" on an internet-facing endpoint.
DISCOVERY_MODE = os.getenv("DISCOVERY_MODE", "").strip().lower() in ("1", "true", "yes")
ALLOWED_ISSUERS = {
    f"https://login.microsoftonline.com/{TENANT_ID}/v2.0",
    f"https://sts.windows.net/{TENANT_ID}/",
} if TENANT_ID else set()
_jwks = PyJWKClient(f"https://login.microsoftonline.com/{TENANT_ID}/discovery/v2.0/keys") if TENANT_ID else None

# ---- Source catalog ---------------------------------------------------------
with open("sources.yaml") as f:
    SOURCES = yaml.safe_load(f)["sources"]

_kv = SecretClient(vault_url=KEY_VAULT_URL, credential=DefaultAzureCredential())

# Secrets are cached so every query does not hit Key Vault, but an unbounded cache means
# a rotated password is never picked up until the container is restarted. Cache with a TTL
# so rotation converges on its own.
SECRET_TTL_SECONDS = int(os.getenv("SECRET_TTL_SECONDS", "3600"))
_secret_cache: dict[str, tuple[float, str]] = {}


def _secret(name: str) -> str:
    hit = _secret_cache.get(name)
    now = time.monotonic()
    if hit and (now - hit[0]) < SECRET_TTL_SECONDS:
        return hit[1]
    value = _kv.get_secret(name).value
    _secret_cache[name] = (now, value)
    return value


# TrustServerCertificate=yes encrypts the connection but does NOT authenticate the server.
# AVS workload VMs usually present self-signed SQL certificates, so it is the pragmatic
# default here; set SQL_TRUST_SERVER_CERT=false once your databases use a trusted cert.
_TRUST_SERVER_CERT = os.getenv("SQL_TRUST_SERVER_CERT", "true").strip().lower() in ("1", "true", "yes")

_DIALECTS = {
    "mssql": ("mssql+pyodbc", {"driver": "ODBC Driver 18 for SQL Server",
                                "Encrypt": "yes",
                                "TrustServerCertificate": "yes" if _TRUST_SERVER_CERT else "no"}),
    "postgresql": ("postgresql+psycopg2", {}),
    "mysql": ("mysql+pymysql", {}),
    "oracle": ("oracle+oracledb", {}),
}


_engines: dict[str, tuple[str, object]] = {}
_engines_lock = threading.Lock()


def _engine(source: str):
    """Return a pooled Engine for a source, rebuilt whenever its secret changes.

    The engine cannot be cached on the source name alone: the password is baked into the
    URL, so a permanently cached engine keeps using the password it was first built with
    and a rotation never converges. Keying the cache on the current secret value means the
    next call after a rotation rebuilds the engine and disposes the stale one.

    The lock stops concurrent callers from each building an engine after a rotation and
    silently overwriting -- and leaking -- one another's.
    """
    if source not in SOURCES:
        raise ValueError(f"Unknown source '{source}'. Options: {', '.join(SOURCES)}")
    s = SOURCES[source]
    drivername, defaults = _DIALECTS[s["type"]]
    auth = s.get("auth", {})
    current = _secret(auth["secret"]) if auth.get("secret") else ""
    cached = _engines.get(source)
    if cached and cached[0] == current:
        return cached[1]
    with _engines_lock:
        cached = _engines.get(source)
        if cached and cached[0] == current:
            return cached[1]
        engine = _build_engine(s, auth, drivername, defaults, current)
        if cached:
            cached[1].dispose()
        _engines[source] = (current, engine)
        return engine


def _build_engine(s: dict, auth: dict, drivername: str, defaults: dict, current: str):
    """Construct a fresh Engine for one source.

    Per-source `connection.options` are merged over the dialect defaults, so a
    PostgreSQL / MySQL / Oracle source can carry its own TLS parameters (e.g. sslmode)
    instead of silently falling back to the driver's defaults.
    """
    query = {**defaults, **(s["connection"].get("options") or {})}
    url = URL.create(
        drivername,
        username=auth.get("username", SQL_USER),
        password=current or None,
        host=s["connection"]["host"],
        port=s["connection"].get("port"),
        database=s["connection"]["database"],
        query=query,
    )
    # pool_recycle keeps pooled connections from outliving a password rotation forever.
    return create_engine(url, pool_pre_ping=True, pool_recycle=SECRET_TTL_SECONDS)


def _gov(source: str) -> dict:
    return SOURCES[source].get("governance", {}) or {}


def _schema_allowed(source: str, schema: str) -> bool:
    allow = _gov(source).get("allow_schemas")
    return schema in allow if allow else True


def _table_denied(source: str, fq_table: str) -> bool:
    return any(fnmatch.fnmatch(fq_table.lower(), p.lower())
               for p in _gov(source).get("deny_tables", []))


mcp = FastMCP("avs-data", host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", "8000")))


@mcp.tool()
def list_sources() -> str:
    """List the available data sources (databases) and what each contains."""
    return "\n".join(f"- {n}: {s.get('description','')} [{s['type']}]" for n, s in SOURCES.items())


@mcp.tool()
def get_schema(source: str) -> str:
    """Get the tables and columns for a data source. Call list_sources first for valid names."""
    insp = inspect(_engine(source))
    lines = []
    for schema in insp.get_schema_names():
        if not _schema_allowed(source, schema):
            continue
        for table in insp.get_table_names(schema=schema):
            fq = f"{schema}.{table}"
            if _table_denied(source, fq):
                continue
            cols = ", ".join(f"{c['name']} ({c['type']})" for c in insp.get_columns(table, schema=schema))
            lines.append(f"{fq}: {cols}")
    return "\n".join(lines) or "No tables."


_BLOCKED_WORDS = ("insert", "update", "delete", "drop", "alter", "truncate",
                  "exec", "execute", "merge", "create", "grant", "revoke", "into")

# \b anchors on word boundaries, so punctuation cannot be used to split a keyword away
# from a space-delimited match ("SELECT *INTO[t]FROM x" is valid T-SQL and would slip
# past a " into " substring test).
_BLOCKED = re.compile(r"\b(?:" + "|".join(_BLOCKED_WORDS) + r")\b", re.I)

_COMMENTS = re.compile(r"--[^\n]*|/\*.*?\*/", re.S)


def _normalize(sql: str, strip_comments: bool = True) -> str:
    """Whitespace-collapsed text used ONLY for the safety check.

    Collapsing whitespace stops a tab or a newline ("SELECT *\nINTO t FROM x") from
    carrying a write past the filter. The original SQL is what actually executes; this
    form is only inspected.

    run_query checks both forms. Stripping comments catches a keyword split by "/*x*/";
    keeping them catches the reverse trick of hiding a real keyword between comment
    markers that are themselves inside string literals.
    """
    text = sql.lower()
    if strip_comments:
        text = _COMMENTS.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


@mcp.tool()
def run_query(source: str, query: str) -> str:
    """Run ONE read-only SELECT against a named source and return up to the source's row cap.
    Use the SQL dialect of that source (shown by list_sources)."""
    q = query.strip().rstrip(";")
    low = _normalize(q)
    forms = (low, _normalize(q, strip_comments=False))
    if not (low.startswith("select") or low.startswith("with")):
        return "Error: only a single read-only SELECT (or WITH ... SELECT) is allowed."
    if ";" in q or any(_BLOCKED.search(f) for f in forms):
        return "Error: only a single read-only SELECT statement is allowed."
    max_rows = int(_gov(source).get("max_rows", 200))
    try:
        with _engine(source).connect() as conn:
            result = conn.exec_driver_sql(q)
            cols = list(result.keys())
            rows = result.fetchmany(max_rows)
    except Exception as e:
        return f"Query error: {e}\n\nTip: call get_schema('{source}') and use the exact table/column names."
    if not rows:
        return "No rows returned."
    return "\n".join([" | ".join(cols)] + [" | ".join(str(v) for v in r) for r in rows])


class AuthMiddleware:
    """Validate the Entra token on /mcp.
    Every request must carry a valid, signature-verified Entra token.
    DISCOVERY mode (ALLOWED_CALLERS empty + DISCOVERY_MODE=true): the token is still
    fully validated; only the caller allow-list check is skipped, and the caller's azp
    is logged so the operator can populate ALLOWED_CALLERS.
    ENFORCED mode: signature (JWKS) + audience + issuer + caller in the allow-list.
    If ALLOWED_CALLERS is empty and DISCOVERY_MODE is off, the endpoint fails closed."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("path", "").startswith("/mcp"):
            hdrs = dict(scope.get("headers") or [])
            auth = hdrs.get(b"authorization", b"").decode()
            token = auth[7:] if auth.lower().startswith("bearer ") else ""

            if not ALLOWED_CALLERS and not DISCOVERY_MODE:
                print("AUTH deny: ALLOWED_CALLERS is empty and DISCOVERY_MODE is off", flush=True)
                await JSONResponse(
                    {"error": "server_not_configured",
                     "detail": "Set ALLOWED_CALLERS to the calling application's azp. To learn "
                               "it, set DISCOVERY_MODE=true temporarily -- discovery still "
                               "requires a valid Entra token."},
                    status_code=503)(scope, receive, send)
                return

            reason = None
            claims = {}
            if not token:
                reason = "no bearer token"
            elif _jwks is None:
                reason = "server missing TENANT_ID"
            else:
                try:
                    key = _jwks.get_signing_key_from_jwt(token)
                    claims = jwt.decode(token, key.key, algorithms=["RS256"],
                                        audience=ALLOWED_AUDIENCES or None,
                                        options={"verify_aud": bool(ALLOWED_AUDIENCES)})
                    if ALLOWED_ISSUERS and claims.get("iss") not in ALLOWED_ISSUERS:
                        reason = f"bad issuer {claims.get('iss')}"
                    elif ALLOWED_CALLERS and (claims.get("azp") or claims.get("appid")) not in ALLOWED_CALLERS:
                        reason = "caller not allowed"
                except Exception as e:
                    reason = f"invalid token: {e}"
            if reason:
                print(f"AUTH deny: {reason}", flush=True)
                await JSONResponse({"error": "unauthorized"}, status_code=401)(scope, receive, send)
                return
            if not ALLOWED_CALLERS:
                # Token is already fully validated here; discovery only skips the allow-list.
                print(f"AUTH discovery: caller azp={claims.get('azp') or claims.get('appid')} "
                      f"aud={claims.get('aud')} -- set ALLOWED_CALLERS to this azp to lock the endpoint",
                      flush=True)
        await self.app(scope, receive, send)


if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    app = mcp.streamable_http_app()
    app.add_middleware(AuthMiddleware)
    uvicorn.run(app, host=host, port=port)
