from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import get_db
from models.user import User
from security import decode_access_token

# tokenUrl 指向登录端点，仅用于 Swagger UI 的 Authorize 按钮。
# 注意：不加前导斜杠，相对路径，和 router 的 prefix="/auth" 拼成 auth/login。
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    从 Bearer token 解析当前用户。
    链路：提取 token → 验签/验过期拿 user_id → 查 DB → 返回 User 对象。
    任何环节失败统一抛 401，不泄露具体原因。
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # 1. 解码 token，拿 user_id（decode 失败返回 None）
    user_id = decode_access_token(token)
    if user_id is None:
        raise credentials_exception

    # 2. 用 user_id 查 DB（token 里的 sub 是字符串形式的 UUID）
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception

    # 3. 状态实时校验：被停用的用户即使持有效 token 也拒绝
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )

    # 4. 租户归属校验：未分配律所的账号无法访问任何租户数据
    if user.firm_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not assigned to a firm",
        )

    return user


def get_db_with_rls(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Session:
    """
    Drop-in replacement for get_db on protected endpoints.
    Executes SET LOCAL so every query in this request is automatically
    scoped to the user's firm by the RLS policies. SET LOCAL is
    transaction-scoped: the variable vanishes when the transaction ends,
    so pooled connections never carry stale tenant context between requests.

    The RLS policies use nullif(..., '')::uuid guards so that when the GUC
    resets to '' (after SET LOCAL + COMMIT), direct-column policies return
    true (IS NULL branch) and sub-select policies cast NULL safely.
    """
    db.execute(text("SET LOCAL app.current_tenant = :fid"), {"fid": str(current_user.firm_id)})
    return db
