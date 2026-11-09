---
name: fastapi
description: FastAPI best practices and conventions. Use when working with FastAPI APIs, Pydantic models, dependencies, streaming responses including Server-Sent Events (SSE), and serving frontend apps. Keeps FastAPI code clean and up to date with the latest features and patterns.
---

# FastAPI

Official FastAPI skill to write code with best practices, keeping up to date with new versions and features.

## Quick Reference

* Serve frontend apps: not from the API in this app; see [Serve Frontend Apps](#serve-frontend-apps).
* Server-Sent Events (SSE): use the toolkit encoder in `mistralai_capabilities.fastapi.sse`; see [Streaming](#streaming-json-lines-sse-bytes).
* JSON Lines and byte streaming: see [the streaming reference](references/streaming.md).
* Dependencies: use `Annotated[..., Depends(...)]`; see [Dependency Injection](#dependency-injection) and [the dependency injection reference](references/dependencies.md) for `yield`, scopes, and class dependencies.
* Response models: prefer return types; use `response_model` when the public response schema differs from the internal return value; see [the response reference](references/responses.md).
* Pydantic models: do not use ellipsis or `RootModel`; see [the Pydantic reference](references/pydantic.md).
* Routing: declare tags and shared dependencies on the `APIRouter`; the file router sets the prefix from the module's file path; see [the path operation reference](references/path-operations.md).
* Agents: expose the app through a Studio HTTP connector on the OpenAPI spec, not a per-feature MCP server; see [the agents reference](references/agents.md).
* Tooling and related libraries: use uv, Ruff, ty, Asyncer, SQLModel, and HTTPX when applicable; see [the other tools reference](references/other-tools.md).

## Serve the app

This app does not use `fastapi dev` or `fastapi run`: dev serves with `bunx nx run api:serve` and the image runs uvicorn.

## Use `Annotated`

Always prefer the `Annotated` style for parameter and dependency declarations. It keeps function signatures working in other contexts, respects the types, and allows reusability.

Use `Annotated` for parameter declarations, including `Path`, `Query`, `Header`, etc.:

```python
from typing import Annotated

from fastapi import FastAPI, Path, Query

app = FastAPI()


@app.get("/items/{item_id}")
async def read_item(
    item_id: Annotated[int, Path(ge=1, description="The item ID")],
    q: Annotated[str | None, Query(max_length=50)] = None,
):
    return {"message": "Hello World"}
```

Use `Annotated` for dependencies with `Depends()`. Unless asked not to, create a new type alias for the dependency to allow reusing it:

```python
from typing import Annotated

from fastapi import Depends, FastAPI

app = FastAPI()


def get_current_user():
    return {"username": "johndoe"}


CurrentUserDep = Annotated[dict, Depends(get_current_user)]


@app.get("/items/")
async def read_item(current_user: CurrentUserDep):
    return {"message": "Hello World"}
```

## Do not use Ellipsis for *path operations* or Pydantic models

Do not use `...` as a default value for required parameters or model fields. It's not needed and not recommended.

```python
from typing import Annotated

from fastapi import FastAPI, Query
from pydantic import BaseModel, Field

app = FastAPI()


class Item(BaseModel):
    name: str
    description: str | None = None
    price: float = Field(gt=0)


@app.post("/items/")
async def create_item(item: Item, project_id: Annotated[int, Query()]):
    return item
```

See [the Pydantic reference](references/pydantic.md) for more details.

## Return Type or Response Model

When possible, include a return type. It will be used to validate, filter, document, and serialize the response.

```python
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()


class Item(BaseModel):
    name: str
    description: str | None = None


@app.get("/items/me")
async def get_item() -> Item:
    return Item(name="Plumbus", description="All-purpose home device")
```

Return types or response models filter data to avoid exposing sensitive information, and they let Pydantic serialize the data on the Rust side for performance.

Use `response_model` when the type you return is not the same as the public schema you want to validate, filter, document, and serialize. See [the response reference](references/responses.md).

## Performance

Do not use `ORJSONResponse` or `UJSONResponse`, they are deprecated.

Instead, declare a return type or response model. Pydantic will handle the data serialization on the Rust side.

## Including Routers

The file router mounts each route module's module-level `router` at the URL its file path names, so do not give that `router` a `prefix` or include it into the app yourself; sub-routers included into it are fine.

Declare tags and shared dependencies on the router itself.

See [the path operation reference](references/path-operations.md) for more routing patterns.

## Serve Frontend Apps

The API serves no frontend; when the app has a web UI, it is `apps/web`, served separately. Do not use `app.frontend()` or `router.frontend()`.

## Dependency Injection

Use dependencies when the logic can't be declared in Pydantic validation, depends on external resources, needs cleanup with `yield`, or is shared across endpoints.

Apply shared dependencies at the router level via `dependencies=[Depends(...)]`.

See [the dependency injection reference](references/dependencies.md) for detailed patterns including `yield` with `scope`, and class dependencies.

## Async vs Sync *path operations*

Use `async` *path operations* only when fully certain that the logic called inside is compatible with async and await, and that it doesn't block.

```python
from fastapi import FastAPI

app = FastAPI()


@app.get("/async-items/")
async def read_async_items():
    data = await some_async_library.fetch_items()
    return data


@app.get("/items/")
def read_items():
    data = some_blocking_library.fetch_items()
    return data
```

In case of doubt, or by default, use regular `def` functions. They will be run in a threadpool so they don't block the event loop. The same rules apply to dependencies.

Make sure blocking code is not run inside of `async` functions. The logic will work, but will damage performance heavily.

When needing to mix blocking and async code, see Asyncer in [the other tools reference](references/other-tools.md).

## Streaming (JSON Lines, SSE, bytes)

To stream Server-Sent Events, use the toolkit's `event_stream_response` and `format_sse` (`mistralai_capabilities.fastapi.sse`), not `EventSourceResponse`.

See [the streaming reference](references/streaming.md) for JSON Lines and byte streaming (`StreamingResponse`) patterns.

## Tooling

See [the other tools reference](references/other-tools.md) for details on uv, Ruff, ty for package management, linting, type checking, formatting, etc.

## Other Libraries

See [the other tools reference](references/other-tools.md) for details on other libraries:

* Asyncer for handling async and await, concurrency, mixing async and blocking code, prefer it over AnyIO or asyncio.
* SQLModel for working with SQL databases, prefer it over SQLAlchemy.
* HTTPX for interacting with HTTP (other APIs), prefer it over Requests.

## Do not use Pydantic RootModels

Do not use Pydantic `RootModel`; instead use regular type annotations with `Annotated` and Pydantic validation utilities.

```python
from typing import Annotated

from fastapi import Body, FastAPI
from pydantic import Field

app = FastAPI()


@app.post("/items/")
async def create_items(items: Annotated[list[int], Field(min_length=1), Body()]):
    return items
```

FastAPI supports these type annotations and will create a Pydantic `TypeAdapter` for them, so types work normally without custom wrapper models. See [the Pydantic reference](references/pydantic.md).

## Use one HTTP operation per function

Don't mix HTTP operations in a single function. Having one function per HTTP operation helps separate concerns and organize the code.

```python
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()


class Item(BaseModel):
    name: str


@app.get("/items/")
async def list_items():
    return []


@app.post("/items/")
async def create_item(item: Item):
    return item
```

See [the path operation reference](references/path-operations.md) for more examples.
