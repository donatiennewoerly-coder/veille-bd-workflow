# Expose the app to agents

Agents (Le Chat, Vibe, Studio agents) reach the app through a Studio HTTP connector pointed at the
API's OpenAPI spec. The connector turns each operation into a tool named after its operationId and
calls the API as the signed-in user, so every route keeps its own auth, access checks and audit.
There is no per-feature MCP server to install or keep in sync with the routes.

1. Keep every route connector-safe: a tag, a docstring (the tool description; FastAPI's generated
   `summary` says nothing), typed request and response models. Operation ids are `{tag}_{function}`,
   stable across deploys. The template route test fails on an operationId a connector rejects, and
   `gen-openapi --check` also fails on an operation with no description.
2. In Studio, create an HTTP connector on the app's plain `/openapi.json` with its base URL and auth.
   Leave out the operations agents should not call (web plumbing) by operationId at import; the spec
   itself is not cut. The health probes are already out of the spec.

Reach for FastMCP only for a real RPC the API does not expose as a route (a long-running agent
action, a stream an HTTP tool cannot carry). Mount it on its own prefix; with `admin-analytics`,
keep that prefix out of the mutation audit (`ignore_audit_prefix`) when it audits its own calls.
