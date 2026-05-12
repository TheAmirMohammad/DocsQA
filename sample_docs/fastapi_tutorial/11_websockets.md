# WebSockets in FastAPI

WebSockets provide full-duplex communication channels over a single TCP connection.

## Basic WebSocket Endpoint

To use WebSockets in FastAPI, import `WebSocket` from `fastapi`:

```python
from fastapi import FastAPI, WebSocket

app = FastAPI()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    while True:
        data = await websocket.receive_text()
        await websocket.send_text(f"Message received: {data}")
```

## Awaiting Connections and Disconnects

When a client disconnects, `WebSocketDisconnect` is raised:

```python
from fastapi import WebSocket, WebSocketDisconnect

@app.websocket("/ws/{client_id}")
async def websocket_chat(websocket: WebSocket, client_id: int):
    await websocket.accept()
    try:
        while True:
            text = await websocket.receive_text()
            await websocket.send_text(f"Client {client_id}: {text}")
    except WebSocketDisconnect:
        print(f"Client {client_id} disconnected")
```
