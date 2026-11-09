# Path Operations and Routing

## Including Routers

The file router mounts each route module's module-level `router` at the URL its file path names, so do not give that `router` a `prefix` or include it into the app yourself; sub-routers included into it are fine.

Apply shared dependencies at the router level via `dependencies=[Depends(...)]`.

## Use one HTTP operation per function

Don't mix HTTP operations in a single function. Having one function per HTTP operation helps separate concerns and organize the code.

Do this:

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

Instead of:

```python
# DO NOT DO THIS
from fastapi import FastAPI, Request
from pydantic import BaseModel

app = FastAPI()


class Item(BaseModel):
    name: str


@app.api_route("/items/", methods=["GET", "POST"])
async def handle_items(request: Request):
    if request.method == "GET":
        return []
```
