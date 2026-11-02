"""Write the API's description to `docs/openapi.json`, for generating SDKs and docs from it.

    python scripts/export_openapi.py [--stats]

FastAPI's own schema describes how the server is built. This one describes what a client
needs: where the server is, how to sign in, which errors come back, and stable names for
each operation. Routes no client should call (PayPal's webhook, the stand-in checkout)
are left out.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "api"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

# The stand-in checkout's routes only exist when it is on, and it is not part of the API.
os.environ["SALIX_PAYPAL_SIMULATOR"] = "false"
os.environ.setdefault("SALIX_PROVIDER_MODE", "mock")
os.environ.setdefault("SALIX_DATABASE_URL", "sqlite+aiosqlite:///:memory:")

import openapi_docs as docs  # noqa: E402
from salix.app import create_app  # noqa: E402

OUTPUT = ROOT / "docs" / "openapi.json"

SERVERS = [{"url": "http://localhost:8000", "description": "A local Salix server"}]

DESCRIPTION = (
    "Salix scores recorded B2B sales calls, writes a coaching plan for the weakest skills, "
    "and lets a salesperson practise against a buyer built from the deals they lost.\n\n"
    "Sign in with `POST /api/auth/login` or the Google flow to receive a session cookie. "
    "A deployment may also require a shared key in the `X-API-Key` header."
)

TAGS = {
    "auth": "Signing in and out, and confirming an email address.",
    "team": "The people on a team, and invitations to join it.",
    "calls": "Uploading recordings and reading their analysis.",
    "reps": "Salespeople and how they are doing.",
    "deals": "Deals and the risks found in their calls.",
    "playbook": "Winning moves taken from calls that closed.",
    "dojo": "Practising against a buyer built from lost deals.",
    "roleplay": "The closing test at the end of a coaching plan.",
    "reports": "Reports covering a sales cycle.",
    "billing": "Credit balance, packs and buying credits with PayPal or Braintree.",
    "search": "Searching everything in the archive.",
    "audio": "Call recordings.",
    "meta": "The dashboard summary, search, and whether the server is up.",
    "plays": "Winning moves taken from calls that closed.",
    "system": "Whether the server is up and ready.",
}

#: How somebody without a session gets one, and the health checks.
PUBLIC = {
    "/api/health",
    "/api/ready",
    "/api/auth/me",
    "/api/auth/google/start",
    "/api/auth/google/callback",
    "/api/auth/logout",
    "/api/auth/signup",
    "/api/auth/login",
    "/api/auth/password/forgot",
    "/api/auth/password/reset",
    "/api/auth/email/verify",
}
#: Public, but they act on the session when there is one, so a client must still send it.
SESSION_IF_ANY = {"/api/auth/me", "/api/auth/logout"}
#: The health checks answer without the deployment's key. Everything else needs it if set.
NO_KEY_NEEDED = {"/api/health", "/api/ready"}
#: PayPal is the caller of the first, and the rest are the stand-in checkout.
NOT_FOR_CLIENTS = re.compile(r"^/api/(billing/webhook|paypal-simulator)")

METHODS = {"get", "post", "put", "patch", "delete"}

ERROR_SCHEMA = {
    "type": "object",
    "title": "ApiError",
    "description": "What every failed request returns.",
    "required": ["detail"],
    "properties": {
        "detail": {"type": "string", "description": "What went wrong, written for a person to read."},
        "error": {"type": "string", "description": "A short machine-readable code, where there is one."},
        "retryable": {"type": "boolean", "description": "Whether trying again later could work."},
    },
}

ERRORS = {
    "401": "Not signed in, or the API key is wrong.",
    "404": "There is no such record, or it belongs to another team.",
    "429": "Too many requests. Wait for the time in the `Retry-After` header.",
}


def _error(description: str) -> dict:
    return {
        "description": description,
        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ApiError"}}},
    }


def _operation_id(method: str, path: str, used: set[str]) -> str:
    """`GET /api/calls/{call_id}` becomes `get_calls_call_id`: stable, and readable as a method."""
    words = re.sub(r"[{}]", "", path.removeprefix("/api/")).replace("/", "_").replace("-", "_").replace(".", "_")
    name = f"{method}_{words}".rstrip("_")
    while name in used:
        name += "_2"
    used.add(name)
    return name


def _rename_schemas(spec: dict) -> dict:
    text = json.dumps(spec)
    for old, new in docs.RENAMED_SCHEMAS.items():
        text = text.replace(f"#/components/schemas/{old}", f"#/components/schemas/{new}")
    spec = json.loads(text)
    schemas = spec["components"]["schemas"]
    for old, new in docs.RENAMED_SCHEMAS.items():
        schemas[new] = schemas.pop(old)
        schemas[new]["title"] = new
    return spec


def _drop_titles(node) -> None:
    """FastAPI titles every field after its own name, and APIMatic refuses the repeats.

    A field that happens to be called `title` holds an object here rather than a string,
    and example values are left alone.
    """
    if isinstance(node, dict):
        if isinstance(node.get("title"), str):
            del node["title"]
        for key, value in node.items():
            if key not in ("example", "examples", "default"):
                _drop_titles(value)
    elif isinstance(node, list):
        for value in node:
            _drop_titles(value)


def _inline_upload_forms(spec: dict) -> None:
    """Puts each multipart form on its operation.

    As a named schema its file field becomes a model attribute typed as a download, and
    the Python SDK generated from that fails on import.
    """
    schemas = spec["components"]["schemas"]
    for name in docs.RENAMED_SCHEMAS.values():
        form = schemas.pop(name)
        for item in spec["paths"].values():
            for operation in item.values():
                body = operation.get("requestBody", {}).get("content", {}).get("multipart/form-data")
                if body and body["schema"].get("$ref") == f"#/components/schemas/{name}":
                    body["schema"] = form


def _spell_nullable(node) -> None:
    """Writes "this or null" as `oneOf`. The Python generator drops the null from `anyOf`,
    and the SDK then refuses a null the server really sends, such as `user` when signed out."""
    if isinstance(node, dict):
        options = node.get("anyOf")
        if isinstance(options, list) and any(o.get("type") == "null" for o in options):
            node["oneOf"] = node.pop("anyOf")
        for key, value in node.items():
            if key not in ("example", "examples", "default"):
                _spell_nullable(value)
    elif isinstance(node, list):
        for value in node:
            _spell_nullable(value)


def _describe_schemas(spec: dict) -> None:
    """Fills in what the code does not already say."""
    for name, schema in spec["components"]["schemas"].items():
        if not schema.get("description") and name in docs.SCHEMAS:
            schema["description"] = docs.SCHEMAS[name]
        for field, prop in schema.get("properties", {}).items():
            if not prop.get("description"):
                text = docs.SCHEMA_PROPERTIES.get((name, field)) or docs.PROPERTIES.get(field)
                if text:
                    prop["description"] = text
            if (name, field) in docs.EXAMPLES:
                prop["examples"] = [docs.EXAMPLES[(name, field)]]


def _security(path: str) -> list[dict]:
    """Any one entry is enough. An empty entry means nothing at all is required."""
    if path in NO_KEY_NEEDED:
        return []
    if path in SESSION_IF_ANY:
        return [{"session": []}, {"apiKey": []}, {}]
    if path in PUBLIC:
        return [{"apiKey": []}, {}]
    return [{"session": []}, {"apiKey": []}]


def build() -> dict:
    spec = _rename_schemas(create_app().openapi())
    spec["openapi"] = "3.1.0"
    spec["info"].update(
        description=DESCRIPTION,
        contact={"name": "Salix", "url": "https://github.com/Baqir376/Paypal_Integration"},
        license={"name": "MIT", "identifier": "MIT"},
    )
    spec["servers"] = SERVERS

    components = spec.setdefault("components", {})
    components["securitySchemes"] = {
        "session": {
            "type": "apiKey",
            "in": "cookie",
            "name": "salix_session",
            "description": "Set when you sign in.",
        },
        "apiKey": {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
            "description": "The deployment's shared key, if it has one.",
        },
    }
    components.setdefault("schemas", {})["ApiError"] = ERROR_SCHEMA

    used: set[str] = set()
    seen_tags: set[str] = set()
    for path in list(spec["paths"]):
        if NOT_FOR_CLIENTS.match(path):
            del spec["paths"][path]
            continue
        item = spec["paths"][path]
        for method in list(item):
            # FastAPI registers HEAD beside GET under the same id, and no SDK wants it.
            if method not in METHODS:
                del item[method]
                continue
            operation = item[method]
            operation["operationId"] = _operation_id(method, path, used)
            if not operation.get("description") and (method, path) in docs.OPERATIONS:
                operation["description"] = docs.OPERATIONS[(method, path)]
            for parameter in operation.get("parameters", []):
                if not parameter.get("description") and parameter["name"] in docs.PARAMETERS:
                    parameter["description"] = docs.PARAMETERS[parameter["name"]]
            if not operation.get("tags"):
                operation["tags"] = ["system"]
            seen_tags.update(operation["tags"])
            operation["security"] = _security(path)

            responses = operation["responses"]
            if path not in PUBLIC:
                responses.setdefault("401", _error(ERRORS["401"]))
            if "{" in path:
                responses.setdefault("404", _error(ERRORS["404"]))
            responses.setdefault("429", _error(ERRORS["429"]))

    _describe_schemas(spec)
    _inline_upload_forms(spec)
    _spell_nullable(spec["paths"])
    _spell_nullable(spec["components"]["schemas"])
    _drop_titles(spec["paths"])
    for schema in spec["components"]["schemas"].values():
        _drop_titles(schema.get("properties", {}))
    spec["tags"] = [{"name": name, "description": TAGS.get(name, name.capitalize())} for name in sorted(seen_tags)]
    return spec


def stats(spec: dict) -> dict:
    operations = [op for item in spec["paths"].values() for op in item.values()]
    schemas = spec["components"]["schemas"]
    properties = [prop for schema in schemas.values() for prop in schema.get("properties", {}).values()]
    parameters = [p for op in operations for p in op.get("parameters", [])]
    return {
        "paths": len(spec["paths"]),
        "operations": len(operations),
        "without description": sum(not op.get("description") for op in operations),
        "schemas": len(schemas),
        "schemas without description": sum(not s.get("description") for s in schemas.values()),
        "properties": len(properties),
        "properties without description": sum(not p.get("description") for p in properties),
        "properties without example": sum("example" not in p and "examples" not in p for p in properties),
        "parameters": len(parameters),
        "parameters without description": sum(not p.get("description") for p in parameters),
    }


def dangling_refs(spec: dict) -> list[str]:
    text = json.dumps(spec)
    names = set(spec["components"]["schemas"])
    return sorted({ref for ref in re.findall(r'#/components/schemas/([^"]+)"', text) if ref not in names})


if __name__ == "__main__":
    document = build()
    OUTPUT.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(ROOT)}: {len(document['paths'])} paths")
    print("unresolved references:", dangling_refs(document) or "none")
    if "--stats" in sys.argv:
        for name, value in stats(document).items():
            print(f"  {name}: {value}")
