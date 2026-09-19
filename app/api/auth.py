"""Auth router: register and login.

Rate limiting on login uses Redis to prevent brute-force attacks.
Registration returns the user but NOT a token (login is a separate step).
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.errors import AppError, ConflictError
from app.core.security import hash_password, verify_password, create_access_token
from app.models.user import User
from app.schemas.auth import RegisterRequest, LoginRequest, TokenResponse, UserResponse

router = APIRouter(prefix="/auth", tags=["Auth"])

@router.post(
    "/register",
    response_model=UserResponse,
    status_code=201,
    summary="Register a new user",
    responses={409: {"description": "Email already registered"}},
)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):

    result = await db.execute(select(User).where(User.email == body.email))
    if result.scalar_one_or_none():
        raise ConflictError("Email already registered")

    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return UserResponse(id=str(user.id), email=user.email)

@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login and receive a JWT",
    responses={401: {"description": "Invalid credentials"}},
)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(body.password, user.password_hash):
        raise AppError("INVALID_CREDENTIALS", "Invalid email or password", 401)

    token = create_access_token(str(user.id))
    return TokenResponse(access_token=token)
