# CORS (Cross-Origin Resource Sharing)

CORS or "Cross-Origin Resource Sharing" refers to the situations when a frontend running in a browser has JavaScript code that communicates with a backend, and the backend is in a different "origin" than the frontend.

## Setting up CORSMiddleware

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

origins = [
    "http://localhost",
    "http://localhost:3000",
    "https://example.com",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def main():
    return {"message": "Hello World"}
```

### CORSMiddleware Configuration Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `allow_origins` | List[str] | `[]` | List of allowed origins (e.g. `['https://app.example.com']`). Wildcard `['*']` allows all. |
| `allow_origin_regex` | str | `None` | Regex string to match origins. |
| `allow_methods` | List[str] | `['GET']` | List of allowed HTTP methods. Use `['*']` for all standard methods. |
| `allow_headers` | List[str] | `[]` | List of allowed HTTP request headers. Use `['*']` for all headers. |
| `allow_credentials` | bool | `False` | Indicate that cookies are supported for cross-origin requests. |
| `max_age` | int | `600` | Sets a maximum time in seconds for browsers to cache CORS preflight responses. |
