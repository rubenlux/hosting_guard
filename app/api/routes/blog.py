import os
import re
import unicodedata
import uuid as _uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

from app.api.security import require_role
from app.infra.audit.blog_repository import BlogRepository, slugify

_BLOG_MEDIA_DIR      = os.getenv("BLOG_MEDIA_DIR",      "/app/media/blog")
_BLOG_MEDIA_URL_BASE = os.getenv("BLOG_MEDIA_URL_BASE", "https://api.hostingguard.lat/media/blog")
_MAX_UPLOAD_BYTES    = 5 * 1024 * 1024                        # 5 MB hard cap
_ALLOWED_TYPES       = {"image/jpeg", "image/png", "image/webp"}
_CT_TO_EXT           = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}

router = APIRouter(tags=["blog"])

_repo = BlogRepository()


# ── Request models ────────────────────────────────────────────────────────────

class PostCreate(BaseModel):
    title: str
    slug: Optional[str] = None
    excerpt: Optional[str] = None
    content: str = ""
    cover_image_url: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[str] = None
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None


class PostUpdate(BaseModel):
    title: Optional[str] = None
    slug: Optional[str] = None
    excerpt: Optional[str] = None
    content: Optional[str] = None
    cover_image_url: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[str] = None
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _media_slug(text: str, max_len: int = 90) -> str:
    """Convert arbitrary text to a safe, lowercase, ASCII slug for filenames."""
    text = unicodedata.normalize("NFKD", text or "")
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    text = text.strip("-")
    return text[:max_len] or "blog-image"


def _build_media_filename(
    content_type: str,
    post_slug: Optional[str],
    post_title: Optional[str],
    image_role: Optional[str],
    image_alt: Optional[str],
    image_name: Optional[str],
) -> str:
    ext = _CT_TO_EXT[content_type]
    short_hash = _uuid.uuid4().hex[:8]

    base_slug = _media_slug(post_slug or post_title or "blog-image")

    if image_role == "cover":
        filename_base = f"{base_slug}-portada"
    else:
        label = _media_slug(image_name or image_alt or "imagen")
        filename_base = f"{base_slug}-{label}" if label else f"{base_slug}-imagen"

    filename_base = filename_base[:90].rstrip("-")
    return f"{filename_base}-{short_hash}{ext}"


def _unique_slug(base: str, exclude_id: Optional[int] = None) -> str:
    candidate = base
    suffix = 1
    while _repo.slug_exists(candidate, exclude_post_id=exclude_id):
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


# ── Admin endpoints ───────────────────────────────────────────────────────────

@router.get("/admin/blog/posts")
def admin_list_posts(
    status: Optional[str] = Query(None),
    include_deleted: bool = Query(False),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: dict = Depends(require_role("admin")),
):
    posts = _repo.list_posts(
        status=status,
        include_deleted=include_deleted,
        limit=limit,
        offset=offset,
    )
    total = _repo.count_posts(status=status, include_deleted=include_deleted)
    return {"posts": posts, "total": total, "limit": limit, "offset": offset}


@router.post("/admin/blog/posts", status_code=201)
def admin_create_post(body: PostCreate, user: dict = Depends(require_role("admin"))):
    base = slugify(body.slug or body.title)
    slug = _unique_slug(base)
    post = _repo.create_post(
        author_id=user["user_id"],
        title=body.title,
        slug=slug,
        excerpt=body.excerpt,
        content=body.content,
        cover_image_url=body.cover_image_url,
        category=body.category,
        tags=body.tags,
        seo_title=body.seo_title,
        seo_description=body.seo_description,
    )
    return post


@router.get("/admin/blog/posts/{post_id}")
def admin_get_post(post_id: int, user: dict = Depends(require_role("admin"))):
    post = _repo.get_by_id(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post no encontrado")
    return post


@router.put("/admin/blog/posts/{post_id}")
def admin_update_post(
    post_id: int,
    body: PostUpdate,
    user: dict = Depends(require_role("admin")),
):
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    if "slug" in fields:
        fields["slug"] = _unique_slug(slugify(fields["slug"]), exclude_id=post_id)
    post = _repo.update_post(post_id, **fields)
    if not post:
        raise HTTPException(status_code=404, detail="Post no encontrado")
    return post


@router.post("/admin/blog/posts/{post_id}/publish")
def admin_publish_post(post_id: int, user: dict = Depends(require_role("admin"))):
    post = _repo.publish_post(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post no encontrado")
    return post


@router.post("/admin/blog/posts/{post_id}/unpublish")
def admin_unpublish_post(post_id: int, user: dict = Depends(require_role("admin"))):
    post = _repo.unpublish_post(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post no encontrado")
    return post


@router.delete("/admin/blog/posts/{post_id}", status_code=200)
def admin_archive_post(post_id: int, user: dict = Depends(require_role("admin"))):
    post = _repo.archive_post(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post no encontrado")
    return {"status": "archived", "post_id": post_id}


@router.post("/admin/blog/media/upload")
async def admin_upload_media(
    file:       UploadFile      = File(...),
    post_slug:  Optional[str]   = Form(None),
    post_title: Optional[str]   = Form(None),
    image_role: Optional[str]   = Form(None),   # "cover" | "inline"
    image_alt:  Optional[str]   = Form(None),
    image_name: Optional[str]   = Form(None),
    user:       dict            = Depends(require_role("admin")),
):
    if file.content_type not in _ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Formato no permitido: {file.content_type}. Usa JPEG, PNG o WebP.",
        )

    data = await file.read(_MAX_UPLOAD_BYTES + 1)
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Archivo muy grande. Máximo {_MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
        )

    subdir   = datetime.now(timezone.utc).strftime("%Y/%m")
    filename = _build_media_filename(
        content_type=file.content_type,
        post_slug=post_slug,
        post_title=post_title,
        image_role=image_role,
        image_alt=image_alt,
        image_name=image_name,
    )
    rel_path = f"{subdir}/{filename}"

    dest_dir = os.path.join(_BLOG_MEDIA_DIR, subdir)
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, filename)
    with open(dest, "wb") as fh:
        fh.write(data)
    os.chmod(dest, 0o644)

    return {
        "url":          f"{_BLOG_MEDIA_URL_BASE}/{rel_path}",
        "path":         f"/media/blog/{rel_path}",
        "filename":     filename,
        "content_type": file.content_type,
        "size":         len(data),
    }


# ── Public endpoints ──────────────────────────────────────────────────────────

@router.get("/blog/posts")
def public_list_posts(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    posts = _repo.list_published(limit=limit, offset=offset)
    total = _repo.count_posts(status="published")
    return {"posts": posts, "total": total, "limit": limit, "offset": offset}


@router.get("/blog/posts/{slug}")
def public_get_post(slug: str):
    post = _repo.get_by_slug(slug, published_only=True)
    if not post:
        raise HTTPException(status_code=404, detail="Post no encontrado")
    return post
