# OAuth2 Security Scopes in FastAPI

OAuth2 scopes allow granting fine-grained permissions to access tokens.

## Defining Security Scopes

Use `SecurityScopes` to check that the current user possesses required permissions:

```python
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import OAuth2PasswordBearer, SecurityScopes

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="token",
    scopes={"me": "Read own user profile", "items": "Read and write items"},
)

async def get_current_user(security_scopes: SecurityScopes, token: str = Depends(oauth2_scheme)):
    if security_scopes.scopes:
        authenticate_value = f'Bearer scope="{security_scopes.scope_str}"'
    else:
        authenticate_value = "Bearer"
    # Verify token claims and scope permissions
    return {"user": "alice", "scopes": security_scopes.scopes}
```

## Route Level Scope Enforcement

Decorate endpoints with `Security`:

```python
@app.get("/users/me/items/")
async def read_own_items(current_user: dict = Security(get_current_user, scopes=["items"])):
    return [{"item_id": "Foo", "owner": current_user["user"]}]
```
