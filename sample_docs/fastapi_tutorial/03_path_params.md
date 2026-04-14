# Path Parameters and Type Validation

You can declare path "parameters" or "variables" with the same syntax used by Python format strings.

## Basic Path Parameter Declaration

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/items/{item_id}")
async def read_item(item_id: int):
    return {"item_id": item_id}
```

The value of the path parameter `item_id` will be passed to your function as the argument `item_id`.
Because the type is declared as `int`, FastAPI provides automatic:
- **Data parsing**: String from URL converted to Python integer.
- **Data validation**: If a non-integer like `/items/foo` is requested, an HTTP 422 Unprocessable Entity error is returned immediately with error details.
- **Documentation**: OpenAPI documentation records that `item_id` is an integer.

## Predefined Values with Python Enum

If you have a path operation that receives a path parameter, but you want the possible valid parameter values to be predefined, you can use a standard Python `Enum`.

```python
from enum import Enum
from fastapi import FastAPI

class ModelName(str, Enum):
    alexnet = "alexnet"
    resnet = "resnet"
    lenet = "lenet"

app = FastAPI()

@app.get("/models/{model_name}")
async def get_model(model_name: ModelName):
    if model_name is ModelName.alexnet:
        return {"model_name": model_name, "message": "Deep Learning FTW!"}

    if model_name.value == "lenet":
        return {"model_name": model_name, "message": "LeCNN all the images"}

    return {"model_name": model_name, "message": "Have some residuals"}
```

### Path Parameter Validation Error Structure

When validation fails, FastAPI returns status code 422:

```json
{
  "detail": [
    {
      "type": "int_parsing",
      "loc": ["path", "item_id"],
      "msg": "Input should be a valid integer, unable to parse string as an integer",
      "input": "foo"
    }
  ]
}
```
