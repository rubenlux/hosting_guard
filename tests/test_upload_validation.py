"""
Tests for upload magic-byte validation (_validate_magic_bytes).

Coverage:
  1. ZIP real válido
  2. ZIP falso renombrado (non-ZIP bytes)
  3. SQL real (UTF-8)
  4. SQL real (latin-1) — MySQL dumps often use this encoding
  5. SQL binario falso (null bytes)
  6. WPRESS válido — custom binary, NOT a ZIP (AIWM format is not ZIP)
  7. WPRESS falso — ELF executable masked as .wpress
  8. WPRESS falso — PE executable masked as .wpress
"""
import zipfile

import pytest
from fastapi import HTTPException

from app.api.routes.import_hosting import _validate_magic_bytes


# ── helpers ───────────────────────────────────────────────────────────────────

def _write_valid_zip(path):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("wp-content/uploads/image.jpg", b"fake jpeg content")
        zf.writestr("readme.txt", b"WordPress backup")


# ── .zip ──────────────────────────────────────────────────────────────────────

def test_zip_valid(tmp_path):
    f = tmp_path / "backup.zip"
    _write_valid_zip(f)
    _validate_magic_bytes(f, ".zip")  # must not raise


def test_zip_fake_renamed(tmp_path):
    f = tmp_path / "fake.zip"
    f.write_bytes(b"This is plain text, not a ZIP file at all.")
    with pytest.raises(HTTPException) as exc:
        _validate_magic_bytes(f, ".zip")
    assert exc.value.status_code == 400


def test_zip_elf_disguised_as_zip(tmp_path):
    f = tmp_path / "evil.zip"
    f.write_bytes(b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 200)
    with pytest.raises(HTTPException) as exc:
        _validate_magic_bytes(f, ".zip")
    assert exc.value.status_code == 400


# ── .sql ──────────────────────────────────────────────────────────────────────

def test_sql_valid_utf8(tmp_path):
    f = tmp_path / "dump.sql"
    f.write_bytes(
        b"-- MySQL dump 10.13 Distrib 8.0.32\n"
        b"CREATE DATABASE IF NOT EXISTS `mysite`;\n"
        b"USE `mysite`;\n"
        b"CREATE TABLE `wp_posts` (ID bigint NOT NULL);\n"
    )
    _validate_magic_bytes(f, ".sql")  # must not raise


def test_sql_valid_latin1(tmp_path):
    # Older MySQL exports use latin-1 for non-ASCII characters.
    # These must NOT be rejected — no null bytes in latin-1 text.
    content = "-- Exportación latin-1: café, Ñoño\nINSERT INTO t VALUES ('données');\n"
    f = tmp_path / "dump_latin1.sql"
    f.write_bytes(content.encode("latin-1"))
    _validate_magic_bytes(f, ".sql")  # must not raise


def test_sql_binary_fake(tmp_path):
    f = tmp_path / "binary.sql"
    f.write_bytes(b"\x00\x01\x02\x03\xff\xfe\xfd binary garbage with null at start")
    with pytest.raises(HTTPException) as exc:
        _validate_magic_bytes(f, ".sql")
    assert exc.value.status_code == 400
    assert "nulos" in exc.value.detail


def test_sql_null_in_middle(tmp_path):
    f = tmp_path / "embed_null.sql"
    f.write_bytes(b"-- looks like SQL\n" + b"A" * 100 + b"\x00" + b"B" * 100)
    with pytest.raises(HTTPException) as exc:
        _validate_magic_bytes(f, ".sql")
    assert exc.value.status_code == 400


# ── .wpress ───────────────────────────────────────────────────────────────────

def test_wpress_valid_custom_binary(tmp_path):
    # All-in-One WP Migration .wpress is a proprietary ServMask archive format.
    # It is NOT a ZIP file — it has a custom binary header.
    # We cannot validate its exact signature without a real export to inspect,
    # so valid wpress files are accepted as long as they are not known executables.
    f = tmp_path / "backup.wpress"
    # Simulate a plausible custom binary header (non-executable, non-ZIP)
    f.write_bytes(b"\x01\xb0\xca\x11" + b"\x00" * 12 + b"ai1wm" + b"a" * 200)
    _validate_magic_bytes(f, ".wpress")  # must not raise


def test_wpress_elf_rejected(tmp_path):
    f = tmp_path / "evil.wpress"
    f.write_bytes(b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 200)
    with pytest.raises(HTTPException) as exc:
        _validate_magic_bytes(f, ".wpress")
    assert exc.value.status_code == 400
    assert "ejecutable" in exc.value.detail


def test_wpress_pe_rejected(tmp_path):
    f = tmp_path / "evil_pe.wpress"
    # PE/COFF header used by Windows .exe and .dll files
    f.write_bytes(b"MZ\x90\x00\x03\x00\x00\x00" + b"\x00" * 200)
    with pytest.raises(HTTPException) as exc:
        _validate_magic_bytes(f, ".wpress")
    assert exc.value.status_code == 400
    assert "ejecutable" in exc.value.detail


def test_wpress_zip_not_rejected(tmp_path):
    # A ZIP file uploaded as .wpress must NOT be blocked — it is plausible that
    # some AIWM versions or third-party tools produce wpress files with ZIP structure.
    # The format boundary is uncertain; we defer to the AIWM plugin to reject bad content.
    f = tmp_path / "maybe_valid.wpress"
    _write_valid_zip(f)
    _validate_magic_bytes(f, ".wpress")  # must not raise
