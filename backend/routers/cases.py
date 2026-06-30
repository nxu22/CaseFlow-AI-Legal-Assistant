"""
Case CRUD endpoints.

所有端点都受 JWT 保护（Depends(get_current_user)）。

设计要点（面试可复述）：
1. 创建案件前先验证 client_id 真实存在 —— 与其让数据库外键抛 500，
   不如应用层主动查、查不到返回友好的 404。
2. case_number 后端自动生成（CFM-{年}-{4位序号}），不让前端控制。
3. 列表端点支持按 status / client_id 多条件筛选 + 分页。
4. PATCH 不允许改 client_id（案件归属客户是业务上的不变量）。
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from dependencies import get_current_user, get_db_with_rls
from models.case import Case, CaseStatus
from models.client import Client
from models.user import User
from schemas.case import CaseCreate, CaseResponse, CaseUpdate

router = APIRouter(prefix="/cases", tags=["Cases"])


def _generate_case_number(db: Session, firm_id: uuid.UUID) -> str:
    """
    生成唯一案号，格式 CFM-{当前年份}-{4位序号}。
    序号按律所隔离计数，不同律所各自从 0001 开始。
    注：MVP 简单实现。生产环境高并发下应加锁或用序列，避免竞态。
    """
    year = datetime.now(timezone.utc).year
    count = db.query(func.count(Case.id)).filter(Case.firm_id == firm_id).scalar() or 0
    return f"CFM-{year}-{count + 1:04d}"


@router.post(
    "",
    response_model=CaseResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_case(
    case_in: CaseCreate,
    db: Session = Depends(get_db_with_rls),
    current_user: User = Depends(get_current_user),
):
    """
    创建案件。
    步骤：①验证 client_id 存在 → ②（若给了律师）验证律师存在 → ③生成案号 → ④入库。
    """
    # ① 验证客户存在且属于本律所
    client = db.query(Client).filter(
        Client.id == case_in.client_id,
        Client.firm_id == current_user.firm_id,
    ).first()
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found",
        )

    # ② 若指定了律师，验证该律师存在且属于本律所
    if case_in.assigned_lawyer_id is not None:
        lawyer = db.query(User).filter(
            User.id == case_in.assigned_lawyer_id,
            User.firm_id == current_user.firm_id,
        ).first()
        if lawyer is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assigned lawyer not found",
            )

    # ③ 生成案号 + ④ 入库
    case = Case(
        case_number=_generate_case_number(db, current_user.firm_id),
        firm_id=current_user.firm_id,
        **case_in.model_dump(),
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


@router.get(
    "",
    response_model=list[CaseResponse],
)
def list_cases(
    db: Session = Depends(get_db_with_rls),
    current_user: User = Depends(get_current_user),
    skip: int = Query(0, ge=0, description="分页偏移"),
    limit: int = Query(50, ge=1, le=200, description="每页数量，上限 200"),
    status_filter: Optional[CaseStatus] = Query(
        None, alias="status", description="按案件状态筛选"
    ),
    client_id: Optional[uuid.UUID] = Query(None, description="按客户筛选"),
):
    """
    案件列表。支持多条件动态筛选：
    - status：只看某状态的案件（如 open）
    - client_id：只看某客户的案件
    两个条件可叠加，都不传则返回全部（分页内）。
    """
    query = db.query(Case).filter(Case.firm_id == current_user.firm_id)
    if status_filter is not None:
        query = query.filter(Case.status == status_filter)
    if client_id is not None:
        query = query.filter(Case.client_id == client_id)
    cases = query.order_by(Case.created_at.desc()).offset(skip).limit(limit).all()
    return cases


@router.get(
    "/{case_id}",
    response_model=CaseResponse,
)
def get_case(
    case_id: uuid.UUID,
    db: Session = Depends(get_db_with_rls),
    current_user: User = Depends(get_current_user),
):
    """单个案件详情。找不到或不属于本律所均返回 404。"""
    case = db.query(Case).filter(
        Case.id == case_id,
        Case.firm_id == current_user.firm_id,
    ).first()
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found",
        )
    return case


@router.patch(
    "/{case_id}",
    response_model=CaseResponse,
)
def update_case(
    case_id: uuid.UUID,
    case_in: CaseUpdate,
    db: Session = Depends(get_db_with_rls),
    current_user: User = Depends(get_current_user),
):
    """
    部分更新案件（可改状态、律师、罚款等）。
    若更新里带了 assigned_lawyer_id，验证该律师存在。
    """
    case = db.query(Case).filter(
        Case.id == case_id,
        Case.firm_id == current_user.firm_id,
    ).first()
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found",
        )

    update_data = case_in.model_dump(exclude_unset=True)

    # 若改派律师，验证新律师存在且属于本律所
    new_lawyer_id = update_data.get("assigned_lawyer_id")
    if new_lawyer_id is not None:
        lawyer = db.query(User).filter(
            User.id == new_lawyer_id,
            User.firm_id == current_user.firm_id,
        ).first()
        if lawyer is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assigned lawyer not found",
            )

    for field, value in update_data.items():
        setattr(case, field, value)

    db.commit()
    db.refresh(case)
    return case


@router.delete(
    "/{case_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_case(
    case_id: uuid.UUID,
    db: Session = Depends(get_db_with_rls),
    current_user: User = Depends(get_current_user),
):
    """
    删除案件。
    案件是末端实体（documents 通过 cascade 跟着删），删除直接执行，无 RESTRICT 阻拦。
    """
    case = db.query(Case).filter(
        Case.id == case_id,
        Case.firm_id == current_user.firm_id,
    ).first()
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found",
        )
    db.delete(case)
    db.commit()
    return None
