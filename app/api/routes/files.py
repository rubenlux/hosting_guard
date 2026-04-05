import os
import shutil
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.security import verify_token
from app.infra.audit.hosting_repository import HostingRepository

router = APIRouter(prefix="/files", tags=["files"])

_hosting_repo = HostingRepository()

CLIENTS_ROOT    = "/opt/clients"
MAX_FILE_BYTES  = 2 * 1024 * 1024  # 2 MB
EDITABLE_EXT    = {
    ".html", ".css", ".js", ".php", ".json", ".md",
    ".txt",  ".xml", ".svg", ".ts",  ".jsx", ".tsx", ".yml", ".yaml",
}
# Archivos internos del sistema que nunca se exponen al cliente
_HIDDEN = {"_upload.zip", "_extracted"}


# ── helpers ──────────────────────────────────────────────────────────────────

def _safe_path(container_name: str, rel_path: str) -> Path:
    """
    Resuelve el path relativo dentro de /opt/clients/{container_name}/.
    Rechaza cualquier intento de path traversal (../, symlinks externos, etc.).
    """
    root   = Path(CLIENTS_ROOT, container_name).resolve()
    target = (root / rel_path).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise HTTPException(status_code=400, detail="Path fuera del directorio permitido.")
    return target


def _get_hosting(hosting_id: int, user_id: int) -> dict:
    hosting = _hosting_repo.get_hosting(hosting_id, user_id)
    if not hosting:
        raise HTTPException(status_code=404, detail="Hosting no encontrado.")
    return hosting


# ── endpoints ────────────────────────────────────────────────────────────────

@router.get("/{hosting_id}")
def list_files(
    hosting_id: int,
    path: str = Query(default="", description="Ruta relativa al root del hosting"),
    user: dict = Depends(verify_token),
):
    """Lista archivos y carpetas de un directorio del hosting."""
    hosting  = _get_hosting(hosting_id, user["user_id"])
    base     = _safe_path(hosting["container_name"], path)

    if not base.exists():
        raise HTTPException(status_code=404, detail="Directorio no encontrado.")
    if not base.is_dir():
        raise HTTPException(status_code=400, detail="La ruta no es un directorio.")

    items = []
    try:
        entries = sorted(base.iterdir(), key=lambda e: (e.is_file(), e.name.lower()))
    except PermissionError:
        raise HTTPException(status_code=403, detail="Sin permiso para leer el directorio.")

    root = Path(CLIENTS_ROOT, hosting["container_name"]).resolve()

    for entry in entries:
        if entry.name in _HIDDEN:
            continue
        rel = str(entry.resolve().relative_to(root))
        ext = entry.suffix.lower()
        items.append({
            "name":     entry.name,
            "path":     rel,
            "type":     "dir" if entry.is_dir() else "file",
            "size":     entry.stat().st_size if entry.is_file() else None,
            "editable": entry.is_file() and ext in EDITABLE_EXT and entry.stat().st_size <= MAX_FILE_BYTES,
            "ext":      ext,
        })

    # breadcrumb — lista de segmentos del path actual
    parts = [p for p in path.strip("/").split("/") if p]
    breadcrumb = []
    accumulated = ""
    for part in parts:
        accumulated = f"{accumulated}/{part}".lstrip("/")
        breadcrumb.append({"name": part, "path": accumulated})

    return {"items": items, "breadcrumb": breadcrumb, "current_path": path}


@router.get("/{hosting_id}/read")
def read_file(
    hosting_id: int,
    path: str = Query(..., description="Ruta relativa al archivo"),
    user: dict = Depends(verify_token),
):
    """Lee el contenido de un archivo editable."""
    hosting = _get_hosting(hosting_id, user["user_id"])
    target  = _safe_path(hosting["container_name"], path)

    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Archivo no encontrado.")

    ext = target.suffix.lower()
    if ext not in EDITABLE_EXT:
        raise HTTPException(status_code=400, detail=f"Extensión '{ext}' no editable.")

    size = target.stat().st_size
    if size > MAX_FILE_BYTES:
        raise HTTPException(status_code=400, detail=f"Archivo demasiado grande ({size // 1024} KB). Límite: 2 MB.")

    try:
        content = target.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error leyendo archivo: {exc}")

    return {"path": path, "content": content, "size": size}


class SaveRequest(BaseModel):
    path:    str
    content: str


@router.post("/{hosting_id}/save")
def save_file(
    hosting_id: int,
    body: SaveRequest,
    user: dict = Depends(verify_token),
):
    """
    Guarda contenido en un archivo.
    Crea un backup .bak antes de escribir por si el proceso falla a mitad.
    """
    hosting = _get_hosting(hosting_id, user["user_id"])
    target  = _safe_path(hosting["container_name"], body.path)

    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Archivo no encontrado.")

    ext = target.suffix.lower()
    if ext not in EDITABLE_EXT:
        raise HTTPException(status_code=400, detail=f"Extensión '{ext}' no editable.")

    encoded = body.content.encode("utf-8")
    if len(encoded) > MAX_FILE_BYTES:
        raise HTTPException(status_code=400, detail="Contenido supera el límite de 2 MB.")

    # Backup antes de escribir
    bak = target.with_suffix(target.suffix + ".bak")
    try:
        shutil.copy2(target, bak)
    except Exception:
        pass  # no bloquear el guardado si el backup falla

    try:
        target.write_bytes(encoded)
    except PermissionError:
        raise HTTPException(status_code=403, detail="Sin permiso para escribir el archivo.")
    except Exception as exc:
        # Intentar restaurar el backup
        if bak.exists():
            shutil.copy2(bak, target)
        raise HTTPException(status_code=500, detail=f"Error guardando: {exc}")

    return {"ok": True, "path": body.path, "size": len(encoded)}


@router.delete("/{hosting_id}")
def delete_file(
    hosting_id: int,
    path: str = Query(..., description="Ruta relativa al archivo a eliminar"),
    user: dict = Depends(verify_token),
):
    """Elimina un archivo (no directorios)."""
    hosting = _get_hosting(hosting_id, user["user_id"])
    target  = _safe_path(hosting["container_name"], path)

    if not target.exists():
        raise HTTPException(status_code=404, detail="Archivo no encontrado.")
    if target.is_dir():
        raise HTTPException(status_code=400, detail="No se pueden eliminar directorios.")

    try:
        target.unlink()
    except PermissionError:
        raise HTTPException(status_code=403, detail="Sin permiso para eliminar el archivo.")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error eliminando: {exc}")

    return {"ok": True, "path": path}
