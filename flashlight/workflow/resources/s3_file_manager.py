import os
import tempfile
import uuid
import pickle
import boto3
from dagster import ConfigurableIOManager, OutputContext, InputContext
from dagster_aws.s3 import S3Resource
from pathlib import Path


class S3FileIOManager(ConfigurableIOManager):
    """
    IOManager that:
      • Always uses the “extension” declared in your AssetOut or Out definition metadata.
      • PathLike → uploads the file as-is (then deletes local copy)
      • Everything else → pickle.dumps(...) → binary upload
      • Throws if you forgot to declare `metadata={"extension": "..."}`
    """

    s3_bucket: str
    s3_prefix: str = ""
    s3_resource: S3Resource | None = None

    def _get_s3_client(self, context: OutputContext | InputContext):
        if self.s3_resource:
            return self.s3_resource.get_client()
        if hasattr(context.resources, "s3"):
            return context.resources.s3.get_client()
        return boto3.client("s3")

    def _get_s3_key(self, context, obj=None) -> str:
        # Build base path
        prefix = self.s3_prefix.strip("/")
        parts = list(context.asset_key.path)
        if context.has_partition_key:
            parts = [context.asset_partition_key, *parts]

        # Require extension from definition metadata
        meta = getattr(context, "definition_metadata", {}) or {}
        ext = meta.get("ext")
        if not isinstance(ext, str) or not ext.startswith("."):
            raise RuntimeError(
                f"Asset `{'.'.join(context.asset_key.path)}` is missing "
                f"`extension` in definition metadata. "
                "Please declare e.g. @asset(out=Out(metadata={'extension': '.png'}))"
            )

        # Assemble key (ensure it ends with ext)
        *dirs, name = parts
        if not name.endswith(ext):
            name = f"{name}{ext}"
        key_parts = ([prefix] if prefix else []) + dirs + [name]
        return "/".join(key_parts)

    def handle_output(self, context: OutputContext, obj):
        if obj is None:
            return

        client = self._get_s3_client(context)
        key = self._get_s3_key(context, obj)
        s3_url = f"s3://{self.s3_bucket}/{key}"

        if isinstance(obj, os.PathLike):
            # Upload the file bytes as-is
            local = str(obj)
            client.upload_file(Filename=local, Bucket=self.s3_bucket, Key=key)
            context.log.info(f"Uploaded file {local} to {s3_url}")
            context.add_output_metadata({"s3_url": s3_url})
            try:
                os.remove(local)
            except OSError:
                context.log.warning(f"Could not delete local file {local}")
        else:
            # Pickle everything else
            try:
                body = pickle.dumps(obj)
            except pickle.PicklingError as e:
                raise TypeError(f"Cannot pickle object of type {type(obj)}: {e}")
            client.put_object(Bucket=self.s3_bucket, Key=key, Body=body)
            context.log.info(f"Pickled and uploaded object to {s3_url}")
            context.add_output_metadata({"s3_url": s3_url})

    def load_input(self, context: InputContext):
        client = self._get_s3_client(context)
        key = self._get_s3_key(context)  # will error if no metadata["extension"]
        suffix = os.path.splitext(key)[1]

        tmp = os.path.join(
            tempfile.gettempdir(),
            f"dagster_temp_{uuid.uuid4().hex}{suffix}"
        )
        client.download_file(Bucket=self.s3_bucket, Key=key, Filename=tmp)
        context.log.info(f"Downloaded {key} to {tmp}")

        if suffix == ".pkl":
            try:
                with open(tmp, "rb") as fp:
                    obj = pickle.load(fp)
                os.remove(tmp)
                context.log.debug(f"Unpickled object and deleted {tmp}")
                return obj
            except Exception as e:
                raise RuntimeError(f"Failed to unpickle from {tmp}: {e}")

        return Path(tmp)
