# Security and OAuth2 Authentication

FastAPI provides complete, production-ready tools to implement authentication and authorization using OAuth2 with Password hashing and Bearer JWT tokens.

## OAuth2 Password Bearer Flow

```python
from typing import Annotated
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

app = FastAPI()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

@app.post("/token")
async def login(form_data: Annotated[OAuth2PasswordRequestForm, Depends()]):
    user = authenticate_user(fake_users_db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/users/me")
async def read_users_me(token: Annotated[str, Depends(oauth2_scheme)]):
    user = get_current_user(token)
    return user
```

### Flow Explanation

1. The client sends username and password to `/token` as form data (`application/x-www-form-urlencoded`).
2. The server verifies credentials and returns a signed JSON Web Token (JWT).
3. For protected endpoints like `/users/me`, the client sends `Authorization: Bearer <token>`.
4. `OAuth2PasswordBearer` extracts the token string from the request header. If missing, it returns HTTP 401 Unauthorized automatically.

## JWT Token Structure

A JWT contains three base64-url encoded segments separated by dots:
- **Header**: Algorithm (`HS256`) and token type (`JWT`).
- **Payload**: Claims such as subject (`sub`), expiration (`exp`), and issued at (`iat`).
- **Signature**: HMAC SHA256 signature using a secret server key.
