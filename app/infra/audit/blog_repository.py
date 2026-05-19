import logging
import re
import unicodedata
from datetime import datetime, timezone
from typing import Optional

from app.infra.db import get_connection, release_connection

logger = logging.getLogger(__name__)

_DANGEROUS = re.compile(
    r'<\s*(script|iframe|object|embed|base|form)[^>]*>.*?</\s*\1\s*>',
    re.IGNORECASE | re.DOTALL,
)
_DANGEROUS_OPEN = re.compile(
    r'<\s*(script|iframe|object|embed|base|form)[^>]*/?>',
    re.IGNORECASE,
)
_ON_ATTRS = re.compile(r'\s+on\w+\s*=\s*(?:"[^"]*"|\'[^\']*\')', re.IGNORECASE)


def slugify(text: str) -> str:
    text = unicodedata.normalize('NFKD', text)
    text = text.encode('ascii', 'ignore').decode('ascii')
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'-+', '-', text)
    text = text.strip('-')
    return text[:120] or 'post'


def _sanitize(content: str) -> str:
    content = _DANGEROUS.sub('', content)
    content = _DANGEROUS_OPEN.sub('', content)
    content = _ON_ATTRS.sub('', content)
    return content


class BlogRepository:

    def list_posts(
        self,
        status: Optional[str] = None,
        include_deleted: bool = False,
        limit: int = 20,
        offset: int = 0,
    ) -> list:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            conditions, params = [], []
            if not include_deleted:
                conditions.append("p.deleted_at IS NULL")
            if status:
                conditions.append("p.status = %s")
                params.append(status)
            where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
            params += [limit, offset]
            cursor.execute(f"""
                SELECT p.post_id, p.title, p.slug, p.excerpt, p.cover_image_url,
                       p.category, p.tags, p.status, p.published_at, p.created_at,
                       p.updated_at, p.author_id, u.email AS author_email
                FROM blog_posts p
                LEFT JOIN users u ON u.user_id = p.author_id
                {where}
                ORDER BY COALESCE(p.published_at, p.created_at) DESC
                LIMIT %s OFFSET %s
            """, params)
            return [dict(r) for r in cursor.fetchall()]
        finally:
            release_connection(conn)

    def count_posts(self, status: Optional[str] = None, include_deleted: bool = False) -> int:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            conditions, params = [], []
            if not include_deleted:
                conditions.append("deleted_at IS NULL")
            if status:
                conditions.append("status = %s")
                params.append(status)
            where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
            cursor.execute(f"SELECT COUNT(*) AS cnt FROM blog_posts {where}", params)
            row = cursor.fetchone()
            return row["cnt"] if row else 0
        finally:
            release_connection(conn)

    def get_by_id(self, post_id: int) -> Optional[dict]:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT p.*, u.email AS author_email
                FROM blog_posts p
                LEFT JOIN users u ON u.user_id = p.author_id
                WHERE p.post_id = %s AND p.deleted_at IS NULL
            """, (post_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            release_connection(conn)

    def get_by_slug(self, slug: str, published_only: bool = True) -> Optional[dict]:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            extra = "AND p.status = 'published'" if published_only else ""
            cursor.execute(f"""
                SELECT p.*, u.email AS author_email
                FROM blog_posts p
                LEFT JOIN users u ON u.user_id = p.author_id
                WHERE p.slug = %s AND p.deleted_at IS NULL {extra}
            """, (slug,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            release_connection(conn)

    def slug_exists(self, slug: str, exclude_post_id: Optional[int] = None) -> bool:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            if exclude_post_id:
                cursor.execute(
                    "SELECT 1 FROM blog_posts WHERE slug = %s AND post_id != %s AND deleted_at IS NULL",
                    (slug, exclude_post_id),
                )
            else:
                cursor.execute(
                    "SELECT 1 FROM blog_posts WHERE slug = %s AND deleted_at IS NULL",
                    (slug,),
                )
            return cursor.fetchone() is not None
        finally:
            release_connection(conn)

    def create_post(
        self,
        author_id: int,
        title: str,
        slug: str,
        excerpt: Optional[str],
        content: str,
        cover_image_url: Optional[str],
        category: Optional[str],
        tags: Optional[str],
        seo_title: Optional[str],
        seo_description: Optional[str],
    ) -> dict:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            now = datetime.now(timezone.utc)
            cursor.execute("""
                INSERT INTO blog_posts
                    (author_id, title, slug, excerpt, content, cover_image_url,
                     category, tags, status, seo_title, seo_description, created_at, updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'draft',%s,%s,%s,%s)
                RETURNING *
            """, (
                author_id, title, slug, excerpt, _sanitize(content),
                cover_image_url, category, tags, seo_title, seo_description, now, now,
            ))
            row = cursor.fetchone()
            conn.commit()
            return dict(row)
        finally:
            release_connection(conn)

    def update_post(self, post_id: int, **fields) -> Optional[dict]:
        allowed = {
            "title", "slug", "excerpt", "content", "cover_image_url",
            "category", "tags", "seo_title", "seo_description",
        }
        updates = {k: v for k, v in fields.items() if k in allowed}
        if "content" in updates:
            updates["content"] = _sanitize(updates["content"])
        if not updates:
            return self.get_by_id(post_id)
        conn = get_connection()
        try:
            cursor = conn.cursor()
            now = datetime.now(timezone.utc)
            set_clause = ", ".join(f"{k} = %s" for k in updates)
            values = list(updates.values()) + [now, post_id]
            cursor.execute(f"""
                UPDATE blog_posts
                SET {set_clause}, updated_at = %s
                WHERE post_id = %s AND deleted_at IS NULL
                RETURNING *
            """, values)
            row = cursor.fetchone()
            conn.commit()
            return dict(row) if row else None
        finally:
            release_connection(conn)

    def publish_post(self, post_id: int) -> Optional[dict]:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            now = datetime.now(timezone.utc)
            cursor.execute("""
                UPDATE blog_posts
                SET status = 'published', published_at = %s, updated_at = %s
                WHERE post_id = %s AND deleted_at IS NULL
                RETURNING *
            """, (now, now, post_id))
            row = cursor.fetchone()
            conn.commit()
            return dict(row) if row else None
        finally:
            release_connection(conn)

    def unpublish_post(self, post_id: int) -> Optional[dict]:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            now = datetime.now(timezone.utc)
            cursor.execute("""
                UPDATE blog_posts
                SET status = 'draft', published_at = NULL, updated_at = %s
                WHERE post_id = %s AND deleted_at IS NULL
                RETURNING *
            """, (now, post_id))
            row = cursor.fetchone()
            conn.commit()
            return dict(row) if row else None
        finally:
            release_connection(conn)

    def archive_post(self, post_id: int) -> Optional[dict]:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            now = datetime.now(timezone.utc)
            cursor.execute("""
                UPDATE blog_posts
                SET status = 'archived', deleted_at = %s, updated_at = %s
                WHERE post_id = %s AND deleted_at IS NULL
                RETURNING *
            """, (now, now, post_id))
            row = cursor.fetchone()
            conn.commit()
            return dict(row) if row else None
        finally:
            release_connection(conn)

    def list_published(self, limit: int = 20, offset: int = 0) -> list:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT post_id, title, slug, excerpt, cover_image_url, category, tags,
                       published_at, created_at, author_id
                FROM blog_posts
                WHERE status = 'published' AND deleted_at IS NULL
                ORDER BY published_at DESC
                LIMIT %s OFFSET %s
            """, (limit, offset))
            return [dict(r) for r in cursor.fetchall()]
        finally:
            release_connection(conn)
