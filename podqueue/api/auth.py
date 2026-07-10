import secrets
from fastapi import APIRouter, Request, HTTPException, status
from pydantic import BaseModel
from podqueue.config import settings

router = APIRouter(prefix="/api")

class LoginRequest(BaseModel):
    password: str

def require_auth(request: Request):
    if not request.session.get("authenticated"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )

@router.post("/login")
async def login(request: Request, data: LoginRequest):
    if secrets.compare_digest(data.password, settings.ADMIN_PASSWORD):
        request.session["authenticated"] = True
        return {"status": "ok", "message": "Login successful"}
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Incorrect password"
    )

@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return {"status": "ok", "message": "Logged out"}

@router.get("/me")
async def check_me(request: Request):
    if request.session.get("authenticated"):
        return {"authenticated": True}
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated"
    )
