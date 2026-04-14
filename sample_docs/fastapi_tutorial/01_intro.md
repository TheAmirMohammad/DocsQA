# FastAPI Introduction and Core Features

FastAPI is a modern, fast (high-performance), web framework for building APIs with Python 3.8+ based on standard Python type hints.

## Key Features

- **Fast**: Very high performance, on par with NodeJS and Go (thanks to Starlette and Pydantic). One of the fastest Python frameworks available.
- **Fast to code**: Increase the speed to develop features by about 200% to 300%.
- **Fewer bugs**: Reduce about 40% of human (developer) induced errors.
- **Intuitive**: Great editor support. Completion everywhere. Less time debugging.
- **Easy**: Designed to be easy to use and learn. Less time reading docs.
- **Short**: Minimize code duplication. Multiple features from each parameter declaration.
- **Robust**: Get production-ready code. With automatic interactive documentation.
- **Standards-based**: Based on (and fully compatible with) the open standards for APIs: OpenAPI (previously known as Swagger) and JSON Schema.

## Technical Foundation

FastAPI stands on the shoulders of giants:
- **Starlette** for the web parts, routing, WebSockets, and background tasks.
- **Pydantic** for the data parts, schema validation, and serialization.
- **Uvicorn** as the lightning-fast ASGI server implementation using `uvloop` and `httptools`.

### Performance Comparison Matrix

| Framework | Requests/sec | Latency (avg) | Type Validation | Interactive Docs |
|---|---|---|---|---|
| FastAPI | 45,000 | 1.8ms | Native (Pydantic) | Yes (Swagger + ReDoc) |
| Flask | 12,000 | 7.5ms | Manual | Manual extension |
| Django REST | 9,500 | 9.8ms | Serializers | Manual extension |
| Express.js | 42,000 | 2.1ms | Manual | Manual extension |

## Concurrency and Async

FastAPI supports both standard synchronous functions and modern asynchronous functions:

```python
from fastapi import FastAPI

app = FastAPI(title="Concurrency Demo")

@app.get("/async-endpoint")
async def get_async_data():
    return {"message": "Executed concurrently using asyncio event loop"}

@app.get("/sync-endpoint")
def get_sync_data():
    # FastAPI automatically runs sync functions inside an external threadpool
    return {"message": "Executed safely in a separate thread worker"}
```
