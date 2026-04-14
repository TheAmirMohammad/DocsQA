# Dependency Injection System

FastAPI has a very powerful, intuitive, yet simple Dependency Injection system.
Dependency Injection is designed to handle common tasks:
- Share database connections.
- Enforce security and authentication.
- Share business logic and query parameter processing.
- Minimize code duplication.

## Basic Dependency with `Depends`

```python
from typing import Annotated
from fastapi import Depends, FastAPI

app = FastAPI()

async def common_parameters(q: str | None = None, skip: int = 0, limit: int = 100):
    return {"q": q, "skip": skip, "limit": limit}

@app.get("/items/")
async def read_items(commons: Annotated[dict, Depends(common_parameters)]):
    return commons

@app.get("/users/")
async def read_users(commons: Annotated[dict, Depends(common_parameters)]):
    return commons
```

### How `Depends` Works

When a request arrives, FastAPI:
1. Calls your dependency function `common_parameters` with the right parameters.
2. Takes the result returned by your dependency.
3. Injects that result into the parameter in your path operation function.

## Dependencies with `yield` (Database Sessions)

You can create dependencies that do some work before executing the path operation, and then some cleanup work after the response is sent. This is done using `yield`:

```python
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends, FastAPI

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    db = AsyncSessionLocal()
    try:
        yield db
    finally:
        await db.close()

@app.get("/data/")
async def get_data(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Item))
    return result.scalars().all()
```

The code before the `yield` statement is executed before creating the response. The code after `yield` is executed after the response has been sent, ensuring database transactions and connections are always safely closed.
