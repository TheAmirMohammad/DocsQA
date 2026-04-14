# Request Body and Pydantic Models

When you need to send data from a client (like a browser or frontend) to your API, you send it as a request body.

## Declaring Request Bodies with Pydantic

To declare a request body, you use Pydantic models with all their power and benefits.

```python
from typing import Optional
from fastapi import FastAPI
from pydantic import BaseModel, Field

class Item(BaseModel):
    name: str = Field(..., example="Foo")
    description: Optional[str] = Field(None, max_length=300)
    price: float = Field(..., gt=0, description="The price must be greater than zero")
    tax: Optional[float] = None

app = FastAPI()

@app.post("/items/")
async def create_item(item: Item):
    item_dict = item.model_dump()
    if item.tax:
        price_with_tax = item.price + item.tax
        item_dict.update({"price_with_tax": price_with_tax})
    return item_dict
```

### What FastAPI Does with Pydantic Models

1. Reads the body of the request as JSON.
2. Converts the corresponding types (if needed).
3. Validates the data:
   - If the data is invalid, it returns a clean and clear 422 error indicating exactly where and what was incorrect.
4. Gives you the received data in the parameter `item` with complete type hints and editor auto-completion.
5. Generates standard JSON Schema definitions for your models, used in OpenAPI.

## Nested Models and Lists

Pydantic models can contain other nested models:

```python
from typing import List, Set
from pydantic import BaseModel, HttpUrl

class Image(BaseModel):
    url: HttpUrl
    name: str

class Product(BaseModel):
    name: str
    tags: Set[str] = set()
    images: Optional[List[Image]] = None
```
