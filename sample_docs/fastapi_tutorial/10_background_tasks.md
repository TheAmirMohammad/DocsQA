# Background Tasks in FastAPI

You can define background tasks to be run after returning a response. This is useful for operations that need to happen after a request, but where the client doesn't really have to be waiting for the operation to complete before receiving the response.

## Using `BackgroundTasks`

```python
from fastapi import BackgroundTasks, FastAPI

app = FastAPI()

def write_notification(email: str, message=""):
    with open("log.txt", mode="a") as email_file:
        content = f"notification for {email}: {message}\n"
        email_file.write(content)

@app.post("/send-notification/{email}")
async def send_notification(email: str, background_tasks: BackgroundTasks):
    background_tasks.add_task(write_notification, email, message="some notification")
    return {"message": "Notification sent in the background"}
```

### Execution Model

- `background_tasks.add_task(function, *args, **kwargs)` registers a function call.
- The path operation finishes, sends the HTTP response immediately to the client with low latency.
- Right after the response is sent, the registered background tasks are executed.
- If an async function is passed (`async def`), it will be awaited in the asyncio event loop.
- If a standard function is passed (`def`), it will be run in the default thread pool executor.
