import re
import uuid
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404

ALLOWED_EXTENSIONS = {".pdf", ".ppt", ".pptx", ".doc", ".docx", ".jpg", ".jpeg", ".png", ".txt"}


class StorageError(Exception):
    pass


def _local_root() -> Path:
    root = Path(settings.OBJECT_STORAGE_ROOT)
    root.mkdir(parents=True, exist_ok=True)
    return root


def use_remote():
    return bool(settings.OBJECT_STORAGE_ENDPOINT and settings.OBJECT_STORAGE_BUCKET and settings.OBJECT_STORAGE_ACCESS_KEY)


def validate_upload(uploaded):
    name = uploaded.name or "upload"
    ext = Path(name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise StorageError(f"Unsupported file type '{ext or 'unknown'}'. Allowed: PDF, PPT/PPTX, DOC/DOCX, JPG, PNG.")
    size = uploaded.size or 0
    if size > settings.MAX_UPLOAD_BYTES:
        raise StorageError("File exceeds the 15 MB limit.")
    if size <= 0:
        raise StorageError("Empty file.")
    return ext


def _safe_name(name):
    base = Path(name).name
    return re.sub(r"[^A-Za-z0-9._-]+", "_", base)[:120] or "file"


def put_bytes(data: bytes, filename: str, prefix: str = "uploads") -> str:
    key = f"{prefix}/{uuid.uuid4().hex}_{_safe_name(filename)}"
    if use_remote():
        import boto3

        client = boto3.client(
            "s3",
            endpoint_url=settings.OBJECT_STORAGE_ENDPOINT,
            aws_access_key_id=settings.OBJECT_STORAGE_ACCESS_KEY,
            aws_secret_access_key=settings.OBJECT_STORAGE_SECRET_KEY,
            region_name=settings.OBJECT_STORAGE_REGION or "auto",
        )
        client.put_object(Bucket=settings.OBJECT_STORAGE_BUCKET, Key=key, Body=data)
        return key
    path = _local_root() / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return key


def put_upload(uploaded, prefix="uploads") -> str:
    validate_upload(uploaded)
    data = uploaded.read()
    return put_bytes(data, uploaded.name, prefix=prefix)


def delete_object(key: str):
    if not key:
        return
    if use_remote():
        import boto3

        client = boto3.client(
            "s3",
            endpoint_url=settings.OBJECT_STORAGE_ENDPOINT,
            aws_access_key_id=settings.OBJECT_STORAGE_ACCESS_KEY,
            aws_secret_access_key=settings.OBJECT_STORAGE_SECRET_KEY,
            region_name=settings.OBJECT_STORAGE_REGION or "auto",
        )
        client.delete_object(Bucket=settings.OBJECT_STORAGE_BUCKET, Key=key)
        return
    path = _local_root() / key
    if path.exists():
        path.unlink()


def open_object(key: str):
    if not key:
        raise Http404("Missing object key")
    if use_remote():
        import boto3
        from django.http import HttpResponse

        client = boto3.client(
            "s3",
            endpoint_url=settings.OBJECT_STORAGE_ENDPOINT,
            aws_access_key_id=settings.OBJECT_STORAGE_ACCESS_KEY,
            aws_secret_access_key=settings.OBJECT_STORAGE_SECRET_KEY,
            region_name=settings.OBJECT_STORAGE_REGION or "auto",
        )
        obj = client.get_object(Bucket=settings.OBJECT_STORAGE_BUCKET, Key=key)
        body = obj["Body"].read()
        resp = HttpResponse(body, content_type=obj.get("ContentType") or "application/octet-stream")
        resp["Content-Disposition"] = f'attachment; filename="{Path(key).name}"'
        return resp
    path = _local_root() / key
    if not path.exists():
        raise Http404("File not found in object storage")
    return FileResponse(path.open("rb"), as_attachment=True, filename=path.name)


def read_bytes(key: str) -> bytes:
    if use_remote():
        import boto3

        client = boto3.client(
            "s3",
            endpoint_url=settings.OBJECT_STORAGE_ENDPOINT,
            aws_access_key_id=settings.OBJECT_STORAGE_ACCESS_KEY,
            aws_secret_access_key=settings.OBJECT_STORAGE_SECRET_KEY,
            region_name=settings.OBJECT_STORAGE_REGION or "auto",
        )
        obj = client.get_object(Bucket=settings.OBJECT_STORAGE_BUCKET, Key=key)
        return obj["Body"].read()
    path = _local_root() / key
    return path.read_bytes() if path.exists() else b""


def extract_text_from_bytes(filename: str, data: bytes) -> str:
    ext = Path(filename).suffix.lower()
    if ext in {".txt", ".md"}:
        return data.decode("utf-8", errors="ignore")
    if ext == ".pdf":
        try:
            from pypdf import PdfReader
            import io

            reader = PdfReader(io.BytesIO(data))
            return "\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception:
            return ""
    if ext == ".pptx":
        try:
            from pptx import Presentation
            import io

            pres = Presentation(io.BytesIO(data))
            chunks = []
            for slide in pres.slides:
                for shape in slide.shapes:
                    if hasattr(shape, "text"):
                        chunks.append(shape.text)
            return "\n".join(chunks)
        except Exception:
            return ""
    if ext == ".docx":
        try:
            import io
            import zipfile
            from xml.etree import ElementTree

            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                xml = zf.read("word/document.xml")
            root = ElementTree.fromstring(xml)
            texts = [node.text for node in root.iter() if node.text]
            return "\n".join(texts)
        except Exception:
            return ""
    return ""
