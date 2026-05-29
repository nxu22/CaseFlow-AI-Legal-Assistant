"""
Document 相关的响应模型。

注意：上传文档走的是 multipart/form-data（文件 + 表单字段），不是 JSON body，
所以这里没有 DocumentCreate —— 创建参数由 router 的 File(...) / Form(...) 直接接收。
本文件只定义"返回给前端"的形状。
"""
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from models.document import DocumentType


class DocumentResponse(BaseModel):
    """
    单个文档的元数据。注意不含文件本体，也不含可直接访问的 URL——
    下载要另外调 /download 端点换取 presigned URL。
    """
    id: uuid.UUID
    case_id: uuid.UUID
    filename: str                      # 原始文件名，仅显示用
    s3_key: str                        # S3 对象 key（MVP 阶段暴露方便调试核对）
    file_size: int                     # 字节
    mime_type: str
    document_type: DocumentType
    ai_summary: Optional[str] = None   # 后续 Claude 生成，现在为空
    uploaded_by_id: Optional[uuid.UUID] = None
    created_at: datetime

    # 允许从 SQLAlchemy ORM 对象直接构造（读 .id/.filename 等属性）
    model_config = {"from_attributes": True}


class DocumentDownloadResponse(BaseModel):
    """换取下载链接的返回。前端拿到 download_url 直接发起下载即可。"""
    filename: str
    download_url: str
    expires_in: int   # 链接有效秒数，前端可据此提示"链接 X 分钟内有效"
