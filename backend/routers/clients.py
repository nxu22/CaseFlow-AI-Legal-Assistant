"""
Client CRUD endpoints.

所有端点都受 JWT 保护（Depends(get_current_user)）——律所内部系统，
未登录不可访问任何客户数据。

设计要点（面试可复述）：
1. PATCH 而非 PUT：部分更新，前端只传要改的字段。
2. 列表端点带分页（skip/limit）+ 按名字模糊搜索（ilike，大小写不敏感）。
3. 删除时若客户仍有关联案件，DB 的 ondelete="RESTRICT" 会拒绝；
   我们捕获 IntegrityError 转成 409 友好提示，而不是裸奔成 500。
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dependencies import get_current_user, get_db_with_rls
from models.client import Client
from models.user import User
from schemas.client import ClientCreate, ClientResponse, ClientUpdate

router = APIRouter(prefix="/clients", tags=["Clients"])


@router.post(
    "",
    response_model=ClientResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_client(
    client_in: ClientCreate,
    db: Session = Depends(get_db_with_rls),
    current_user: User = Depends(get_current_user),
):
    """创建客户。full_name 必填，其余可选。"""
    client = Client(firm_id=current_user.firm_id, **client_in.model_dump())
    db.add(client)
    db.commit()
    db.refresh(client)
    return client


@router.get(
    "",
    response_model=list[ClientResponse],
)
def list_clients(
    db: Session = Depends(get_db_with_rls),
    current_user: User = Depends(get_current_user),
    skip: int = Query(0, ge=0, description="分页偏移"),
    limit: int = Query(50, ge=1, le=200, description="每页数量，上限 200"),
    search: Optional[str] = Query(None, description="按客户姓名模糊搜索"),
):
    """
    客户列表。
    - 分页：skip/limit，limit 硬上限 200 防一次拉太多。
    - 搜索：search 非空时按 full_name 大小写不敏感模糊匹配。
    """
    query = db.query(Client).filter(Client.firm_id == current_user.firm_id)
    if search:
        query = query.filter(Client.full_name.ilike(f"%{search}%"))
    clients = query.order_by(Client.created_at.desc()).offset(skip).limit(limit).all()
    return clients


@router.get(
    "/{client_id}",
    response_model=ClientResponse,
)
def get_client(
    client_id: uuid.UUID,
    db: Session = Depends(get_db_with_rls),
    current_user: User = Depends(get_current_user),
):
    """单个客户详情。找不到或不属于本律所均返回 404。"""
    client = db.query(Client).filter(
        Client.id == client_id,
        Client.firm_id == current_user.firm_id,
    ).first()
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found",
        )
    return client


@router.patch(
    "/{client_id}",
    response_model=ClientResponse,
)
def update_client(
    client_id: uuid.UUID,
    client_in: ClientUpdate,
    db: Session = Depends(get_db_with_rls),
    current_user: User = Depends(get_current_user),
):
    """
    部分更新客户。
    exclude_unset=True：只取请求里实际传了的字段，没传的保持原值。
    """
    client = db.query(Client).filter(
        Client.id == client_id,
        Client.firm_id == current_user.firm_id,
    ).first()
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found",
        )

    update_data = client_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(client, field, value)

    db.commit()
    db.refresh(client)
    return client


@router.delete(
    "/{client_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_client(
    client_id: uuid.UUID,
    db: Session = Depends(get_db_with_rls),
    current_user: User = Depends(get_current_user),
):
    """
    删除客户。
    若客户仍有关联案件，Case 外键 ondelete="RESTRICT" 会触发 IntegrityError，
    我们回滚并返回 409 Conflict，提示先处理其案件。
    """
    client = db.query(Client).filter(
        Client.id == client_id,
        Client.firm_id == current_user.firm_id,
    ).first()
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found",
        )

    try:
        db.delete(client)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete client with existing cases. Reassign or close cases first.",
        )
    # 204 无响应体
    return None
