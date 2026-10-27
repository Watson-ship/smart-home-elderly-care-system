from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from infrastructure.security.jwt_tool import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

async def get_current_user(token: str = Depends(oauth2_scheme)):
    return decode_token(token)
