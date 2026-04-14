# First Steps with FastAPI

Creating your first FastAPI application requires just a few lines of Python.

## Minimal Application Example

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def read_root():
    return {"Hello": "World"}

@app.get("/healthz")
async def health_check():
    return {"status": "ok"}
```

### Breakdown of the Code

1. `from fastapi import FastAPI`: Import the FastAPI class.
2. `app = FastAPI()`: Create the main ASGI application instance.
3. `@app.get("/")`: The path operation decorator.
   - `path`: `/`
   - `operation`: HTTP GET
4. `def read_root()`: The path operation function.
5. Return value: A dictionary that FastAPI automatically serializes into JSON.

## Interactive API Documentation

When you run your application with Uvicorn:

```bash
uvicorn main:app --reload
```

FastAPI automatically generates two interactive API documentation endpoints:

| URL Endpoint | Documentation System | Purpose |
|---|---|---|
| `/docs` | Swagger UI | Interactive testing, parameter exploration, authorization test |
| `/redoc` | ReDoc | Clean, responsive reference documentation layout |
| `/openapi.json` | OpenAPI Schema | Machine-readable specification conforming to OpenAPI 3.1 |

## HTTP Methods

FastAPI provides decorators for all standard HTTP methods:
- `@app.get()`: Read data
- `@app.post()`: Create data
- `@app.put()`: Replace/update data
- `@app.delete()`: Delete data
- `@app.options()`: CORS pre-flight
- `@app.head()`: Headers check
- `@app.patch()`: Partial update
