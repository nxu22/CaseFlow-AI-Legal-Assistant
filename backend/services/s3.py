"""
S3 object-storage service.

职责（面试可复述）：
封装所有和 AWS S3 打交道的细节，让上层 router 完全不碰 boto3。
router 只调用本模块的 4 个函数，出错时只需捕获一个 S3ServiceError，
不需要知道 boto3 的 ClientError / BotoCoreError 长什么样。
这就是"服务层"的意义：把第三方依赖隔离在一个边界里。

设计要点：
1. boto3 client 在模块加载时创建一次（进程级单例），复用连接池。
2. 文件本体存 S3，数据库只存 s3_key（见 Document model）。
3. 下载不返回公开 URL，而是按需生成有时效的 presigned URL —— 桶是私有的，
   presigned URL 用 IAM 密钥临时签名，过期即失效。这是私有对象安全分发的标准做法。
"""
import io
import uuid
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from config import settings


class S3ServiceError(Exception):
    """本服务统一对外抛出的异常，屏蔽 boto3 内部异常类型。"""


# 进程级单例 client。
# signature_version="s3v4"：ca-central-1 等较新区域要求 SigV4 签名，
# 显式指定可避免 presigned URL 在某些区域签名失败的坑。
_s3_client = boto3.client(
    "s3",
    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    region_name=settings.AWS_REGION,
    config=Config(signature_version="s3v4"),
)


def build_s3_key(case_id: uuid.UUID, original_filename: str) -> str:
    """
    生成 S3 对象 key，格式 cases/{case_id}/{随机uuid}{原扩展名}。
    为什么用随机 uuid 而不是原文件名：
    - 避免同名文件互相覆盖
    - 避免文件名里的特殊字符 / 中文 / 空格引发 key 问题
    原文件名另存在 Document.filename 字段，仅供显示。
    """
    ext = Path(original_filename).suffix  # 形如 ".pdf"，无扩展名则为 ""
    return f"cases/{case_id}/{uuid.uuid4().hex}{ext}"


def upload_fileobj(fileobj: io.BytesIO, s3_key: str, content_type: str) -> None:
    """
    把文件流上传到 S3。
    用 upload_fileobj（托管传输，大文件会自动分片）而不是 put_object。
    ExtraArgs 里设 ContentType，下载/预览时浏览器才能正确识别类型。
    """
    try:
        _s3_client.upload_fileobj(
            Fileobj=fileobj,
            Bucket=settings.AWS_S3_BUCKET,
            Key=s3_key,
            ExtraArgs={"ContentType": content_type},
        )
    except (BotoCoreError, ClientError) as exc:
        raise S3ServiceError(f"上传到 S3 失败: {exc}") from exc


def generate_presigned_url(s3_key: str, expires_in: int = 3600) -> str:
    """
    为私有对象生成有时效的下载链接（默认 1 小时）。
    链接里带临时签名，任何人在有效期内可直接从 S3 下载，过期即失效。
    数据库永远不存这个 URL，每次请求现生成 —— 这样桶可以保持完全私有。
    """
    try:
        return _s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.AWS_S3_BUCKET, "Key": s3_key},
            ExpiresIn=expires_in,
        )
    except (BotoCoreError, ClientError) as exc:
        raise S3ServiceError(f"生成 presigned URL 失败: {exc}") from exc


def delete_object(s3_key: str) -> None:
    """从 S3 删除一个对象。删除文档时调用。"""
    try:
        _s3_client.delete_object(Bucket=settings.AWS_S3_BUCKET, Key=s3_key)
    except (BotoCoreError, ClientError) as exc:
        raise S3ServiceError(f"从 S3 删除失败: {exc}") from exc


def download_bytes(s3_key: str) -> bytes:
    """
    从 S3 把整个对象读成字节。
    摘要功能要用：文件本体在 S3，生成摘要时得先取回来再喂给 Claude。
    """
    try:
        response = _s3_client.get_object(Bucket=settings.AWS_S3_BUCKET, Key=s3_key)
        return response["Body"].read()
    except (BotoCoreError, ClientError) as exc:
        raise S3ServiceError(f"从 S3 下载失败: {exc}") from exc
