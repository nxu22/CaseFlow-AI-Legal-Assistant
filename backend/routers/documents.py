"""
Document 上传/下载/删除端点。

所有端点都嵌套在某个 case 下（/cases/{case_id}/documents），受 JWT 保护，
且每次都先验证 case 存在，避免给不存在的案件挂文档。

文件本体进 S3，数据库 documents 表只存元数据 + s3_key。
router 不直接碰 boto3，全部通过 services.s3 模块，出错只捕获 S3ServiceError。

设计要点（面试可复述）：
1. 上传走 multipart/form-data：file 用 UploadFile，document_type 用 Form。
   （这也是为什么后端需要 python-multipart 这个依赖。）
2. 先校验文件大小（空文件 / 超 10MB 直接拒），再上传，避免无谓的 S3 调用。
3. 上传顺序：先传 S3 成功，再写数据库。若数据库写失败，S3 会留下孤儿对象
   —— MVP 可接受，生产用 S3 生命周期规则定期清理。
4. 删除顺序：先删数据库行（保证不出现"指向已消失对象"的坏记录），再删 S3。
   若 S3 删除失败只是留孤儿对象，不影响数据正确性。
5. 私有桶 + presigned URL：下载不暴露公开链接，按需签发有时效链接。
"""
import io
import uuid

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user
from models.case import Case
from models.document import Document, DocumentType
from models.user import User
from schemas.document import DocumentDownloadResponse, DocumentResponse
from services.ai import AIServiceError, UnsupportedFileTypeError, summarize_document
from services.s3 import (
    S3ServiceError,
    build_s3_key,
    delete_object,
    download_bytes,
    generate_presigned_url,
    upload_fileobj,
)

router = APIRouter(prefix="/cases/{case_id}/documents", tags=["Documents"])

# 单文件上限 10MB。罚单、法院通知、照片证据这类文件足够了。
MAX_FILE_SIZE = 10 * 1024 * 1024
PRESIGNED_URL_EXPIRES = 3600  # 1 小时


def _get_case_or_404(db: Session, case_id: uuid.UUID) -> Case:
    """复用：取案件，不存在抛 404。避免给孤儿案件挂文档。"""
    case = db.query(Case).filter(Case.id == case_id).first()
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case not found",
        )
    return case


@router.post(
    "",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
def upload_document(
    case_id: uuid.UUID,
    file: UploadFile = File(...),
    document_type: DocumentType = Form(DocumentType.OTHER),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    上传文档到指定案件。
    步骤：①验证 case 存在 → ②读文件+校验大小 → ③传 S3 → ④写 documents 表。
    保持同步 def（和项目其余端点一致，sync SQLAlchemy 架构）：
    file.file.read() 是底层文件对象的同步读取。
    """
    # ① case 必须存在
    _get_case_or_404(db, case_id)

    # ② 读出全部字节，顺便算大小（MVP 文件小，读进内存可接受）
    contents = file.file.read()
    file_size = len(contents)
    if file_size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty",
        )
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large (max {MAX_FILE_SIZE // (1024 * 1024)} MB)",
        )

    # ③ 生成 key 并上传 S3
    safe_filename = file.filename or "unnamed"
    s3_key = build_s3_key(case_id, safe_filename)
    content_type = file.content_type or "application/octet-stream"
    try:
        upload_fileobj(io.BytesIO(contents), s3_key, content_type)
    except S3ServiceError:
        # 不把 boto3 的内部错误细节泄露给前端
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to store file in object storage",
        )

    # ④ 写数据库元数据
    document = Document(
        case_id=case_id,
        filename=safe_filename,
        s3_key=s3_key,
        file_size=file_size,
        mime_type=content_type,
        document_type=document_type,
        uploaded_by_id=current_user.id,
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


@router.get("", response_model=list[DocumentResponse])
def list_documents(
    case_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出某案件下所有文档（按上传时间倒序）。"""
    _get_case_or_404(db, case_id)
    return (
        db.query(Document)
        .filter(Document.case_id == case_id)
        .order_by(Document.created_at.desc())
        .all()
    )


@router.get(
    "/{document_id}/download",
    response_model=DocumentDownloadResponse,
)
def get_document_download_url(
    case_id: uuid.UUID,
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    换取有时效的下载链接（presigned URL）。
    桶是私有的，前端不能直接访问 S3，必须通过这里临时签发链接。
    """
    document = (
        db.query(Document)
        .filter(Document.id == document_id, Document.case_id == case_id)
        .first()
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    try:
        url = generate_presigned_url(document.s3_key, PRESIGNED_URL_EXPIRES)
    except S3ServiceError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to generate download URL",
        )
    return DocumentDownloadResponse(
        filename=document.filename,
        download_url=url,
        expires_in=PRESIGNED_URL_EXPIRES,
    )


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_document(
    case_id: uuid.UUID,
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    删除文档：先删数据库行，再删 S3 对象（顺序见文件头注释第 4 点）。
    """
    document = (
        db.query(Document)
        .filter(Document.id == document_id, Document.case_id == case_id)
        .first()
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    s3_key = document.s3_key  # 先取出 key，删行后就读不到了
    db.delete(document)
    db.commit()

    # 数据库已干净。S3 删失败也只是留孤儿对象，不报错给用户。
    try:
        delete_object(s3_key)
    except S3ServiceError:
        # 生产环境这里应记日志 / 进重试队列；MVP 静默忽略
        pass

    return None


@router.post(
    "/{document_id}/summarize",
    response_model=DocumentResponse,
)
def summarize_document_endpoint(
    case_id: uuid.UUID,
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    用 Claude 给某文档生成摘要，写进 ai_summary 字段。
    流程：①取文档(校验属于该 case) → ②从 S3 下载字节 → ③喂给 Claude →
          ④存库返回。
    设计：单独的动作端点，不混进上传流程（解耦：上传永远快，AI 失败不连累上传）。
    """
    document = (
        db.query(Document)
        .filter(Document.id == document_id, Document.case_id == case_id)
        .first()
    )
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    # ② 从 S3 取回文件本体
    try:
        file_bytes = download_bytes(document.s3_key)
    except S3ServiceError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to read file from object storage",
        )

    # ③ 调 Claude 生成摘要
    try:
        summary = summarize_document(file_bytes, document.mime_type)
    except UnsupportedFileTypeError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="This file type cannot be summarized",
        )
    except AIServiceError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to generate AI summary",
        )

    # ④ 存库
    document.ai_summary = summary
    db.commit()
    db.refresh(document)
    return document
