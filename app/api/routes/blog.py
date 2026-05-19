from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.security import require_role
from app.infra.audit.blog_repository import BlogRepository, slugify

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


# ── Helper ────────────────────────────────────────────────────────────────────

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
