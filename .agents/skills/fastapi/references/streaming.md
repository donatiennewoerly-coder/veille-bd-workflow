# Streaming

## Stream JSON Lines

To stream JSON Lines, declare the return type and use `yield` to return the data.

```python
@app.get("/items/stream")
async def stream_items() -> AsyncIterable[Item]:
    for item in items:
        yield item
```

## Server-Sent Events (SSE)

To stream Server-Sent Events, use the toolkit's `event_stream_response` and `format_sse` (`mistralai_capabilities.fastapi.sse`), not `EventSourceResponse`.

## Stream bytes

To stream bytes, declare a `response_class=` of `StreamingResponse` or a sub-class, and use `yield` to return the data.

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from app.utils import read_image

app = FastAPI()


class PNGStreamingResponse(StreamingResponse):
    media_type = "image/png"

@app.get("/image", response_class=PNGStreamingResponse)
def stream_image_no_async_no_annotation():
    with read_image() as image_file:
        yield from image_file
```

prefer this over returning a `StreamingResponse` directly:

```python
# DO NOT DO THIS

import anyio
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from app.utils import read_image

app = FastAPI()


class PNGStreamingResponse(StreamingResponse):
    media_type = "image/png"


@app.get("/")
async def main():
    return PNGStreamingResponse(read_image())
```
