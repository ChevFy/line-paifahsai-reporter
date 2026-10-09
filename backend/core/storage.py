import asyncio
import logging

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from config.config import settings

logger = logging.getLogger(__name__)

CONNECT_TIMEOUT_SECONDS = 3
READ_TIMEOUT_SECONDS = 15
MAX_ATTEMPTS = 2
MISSING_OBJECT_CODES = {"NoSuchKey", "404"}

_client = None


class StorageUnavailableError(Exception):
    pass


class StorageObjectNotFoundError(Exception):
    pass


def get_s3_client():
    global _client
    if _client is None:
        _client = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT_URL,
            region_name=settings.S3_REGION,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            config=Config(
                connect_timeout=CONNECT_TIMEOUT_SECONDS,
                read_timeout=READ_TIMEOUT_SECONDS,
                retries={"max_attempts": MAX_ATTEMPTS, "mode": "standard"},
                s3={"addressing_style": "path"},
            ),
        )
    return _client


async def put_object(key: str, data: bytes, content_type: str) -> None:
    client = get_s3_client()
    try:
        await asyncio.to_thread(
            client.put_object,
            Bucket=settings.S3_BUCKET,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
    except (BotoCoreError, ClientError) as error:
        raise StorageUnavailableError(f"{type(error).__name__}: {error}") from error
    logger.info(
        "object stored: bucket=%s key=%s bytes=%s",
        settings.S3_BUCKET,
        key,
        len(data),
    )


async def get_object(key: str) -> tuple[bytes, str]:
    client = get_s3_client()
    try:
        response = await asyncio.to_thread(
            client.get_object, Bucket=settings.S3_BUCKET, Key=key
        )
        data = await asyncio.to_thread(response["Body"].read)
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") in MISSING_OBJECT_CODES:
            raise StorageObjectNotFoundError(key) from error
        raise StorageUnavailableError(f"{type(error).__name__}: {error}") from error
    except BotoCoreError as error:
        raise StorageUnavailableError(f"{type(error).__name__}: {error}") from error
    return data, response.get("ContentType") or "application/octet-stream"
