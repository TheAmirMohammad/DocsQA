# Query Parameters in FastAPI

When you declare other function parameters that are not part of the path parameters, they are automatically interpreted as "query" parameters.

## Basic Query Parameters

```python
from fastapi import FastAPI

app = FastAPI()

fake_items_db = [{"item_name": "Foo"}, {"item_name": "Bar"}, {"item_name": "Baz"}]

@app.get("/items/")
async def read_items(skip: int = 0, limit: int = 10):
    return fake_items_db[skip : skip + limit]
```

The query is the set of key-value pairs that go after the `?` in a URL, separated by `&` characters:
`http://127.0.0.1:8000/items/?skip=0&limit=10`

### Defaults and Optional Parameters

You can declare optional query parameters by setting their default to `None`:

```python
from typing import Optional
from fastapi import FastAPI

app = FastAPI()

@app.get("/items/{item_id}")
async def read_item(item_id: str, q: Optional[str] = None, short: bool = False):
    item = {"item_id": item_id}
    if q:
        item.update({"q": q})
    if not short:
        item.update({"description": "This is an amazing item with long description."})
    return item
```

### Boolean Parameter Conversion

FastAPI is smart with booleans. The following query values are all evaluated as `True`:
- `1`, `True`, `true`, `on`, `yes`

The following are evaluated as `False`:
- `0`, `False`, `false`, `off`, `no`
