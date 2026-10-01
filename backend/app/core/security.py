from fastapi import Header, HTTPException

from app.schemas.contracts import Scope


class TokenAuthenticator:
    def __init__(self, tokens):
        self.tokens = tokens

    def scope_for(self, authorization: str | None) -> Scope:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Bearer token required")
        details = self.tokens.get(authorization.removeprefix("Bearer ").strip())
        if not details or len(details) != 2:
            raise HTTPException(status_code=401, detail="Invalid bearer token")
        return Scope(user_id=details[0], workspace_id=details[1])


def scoped_auth(authenticator: TokenAuthenticator):
    async def resolve(authorization: str | None = Header(default=None)) -> Scope:
        return authenticator.scope_for(authorization)
    return resolve
