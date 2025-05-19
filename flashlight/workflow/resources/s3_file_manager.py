import os
import tempfile
import uuid
import boto3
from pathlib import Path
from dagster import ConfigurableIOManager, OutputContext, InputContext
from dagster_aws.s3 import S3Resource

class S3FileIOManager(ConfigurableIOManager):
    """
    A manager for handling input and output operations with Amazon S3, providing
    integration with Dagster's IOManager system.

    This class facilitates interaction with S3 for storing and retrieving files,
    raw bytes, and plain strings. It supports operations like uploading and
    downloading objects from specified S3 buckets, using optional client
    configuration and resource contexts.

    :ivar s3_bucket: The name of the S3 bucket used for storage operations.
    :type s3_bucket: str
    :ivar s3_prefix: An optional prefix used for all S3 keys to organize stored objects.
    :type s3_prefix: str
    :ivar s3_resource: An optional S3 resource instance for custom client configuration.
    :type s3_resource: S3Resource | None
    """

    s3_bucket: str
    s3_prefix: str = ""
    s3_resource: S3Resource | None = None

    def _get_s3_client(self, context):
        if self.s3_resource:
            return self.s3_resource.get_client()
        if hasattr(context.resources, "s3"):
            return context.resources.s3.get_client()
        return boto3.client("s3")

    def _get_s3_key(self, context, obj=None):
        prefix = self.s3_prefix.strip("/")
        asset_parts = list(context.asset_key.path)
        if context.has_partition_key:
            asset_parts.append(context.asset_partition_key)

        # figure extension
        ext = ""
        if obj is not None:
            if isinstance(obj, os.PathLike):
                ext = Path(obj).suffix
            elif isinstance(obj, (bytes, bytearray)):
                ext = ".bin"
            elif isinstance(obj, str):
                ext = ".txt"

        *dirs, filename = asset_parts
        if ext and not filename.endswith(ext):
            filename += ext

        parts = ([prefix] if prefix else []) + dirs + [filename]
        return "/".join(parts)

    def handle_output(self, context: OutputContext, obj):
        if obj is None:
            return

        s3_client = self._get_s3_client(context)
        s3_key = self._get_s3_key(context, obj)
        s3_url = f"s3://{self.s3_bucket}/{s3_key}"

        # 1) PathLike → actual file upload, then delete
        if isinstance(obj, os.PathLike):
            file_path = str(obj)
            s3_client.upload_file(Filename=file_path, Bucket=self.s3_bucket, Key=s3_key)
            context.log.info(f"Uploaded file {file_path} to {s3_url}")
            context.add_output_metadata({"s3_url": s3_url})
            try:
                os.remove(file_path)
                context.log.debug(f"Deleted local file {file_path}")
            except OSError as e:
                context.log.warning(f"Could not delete {file_path}: {e}")

        # 2) Raw bytes → binary object
        elif isinstance(obj, (bytes, bytearray)):
            s3_client.put_object(Bucket=self.s3_bucket, Key=s3_key, Body=obj)
            context.log.info(f"Uploaded {len(obj)} bytes to {s3_url}")
            context.add_output_metadata({"s3_url": s3_url})

        # 3) Plain str → text object (e.g. your URL)
        elif isinstance(obj, str):
            data = obj.encode("utf-8")
            s3_client.put_object(Bucket=self.s3_bucket, Key=s3_key, Body=data)
            context.log.info(f"Uploaded text ({len(data)} bytes) to {s3_url}")
            context.add_output_metadata({"s3_url": s3_url})

        else:
            raise TypeError(f"S3FileIOManager cannot handle type {type(obj)}")

    def load_input(self, context: InputContext):
        s3_client = self._get_s3_client(context)
        s3_key = self._get_s3_key(context)
        suffix = os.path.splitext(s3_key)[1] or ""
        tmp_path = os.path.join(tempfile.gettempdir(), f"dagster_temp_{uuid.uuid4().hex}{suffix}")
        s3_client.download_file(Bucket=self.s3_bucket, Key=s3_key, Filename=tmp_path)
        context.log.info(f"Downloaded {s3_key} to {tmp_path}")
        return tmp_path