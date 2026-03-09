"""
Archive Creator - Backend Module

Provides file compression functionality supporting ZIP and tar.gz formats.
Can be used as an imported module or run standalone via CLI.
"""

import argparse
import os
import pathlib
import tarfile
import zipfile

SUPPORTED_FORMATS = ("zip", "tar.gz")


def _human_size(size_bytes):
    """Convert byte count to a human-readable string."""
    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


class CompressionResult:
    """Container for compression output metadata."""

    def __init__(self, path, file_count, original_size, archive_size):
        self.path = path
        self.file_count = file_count
        self.original_size = original_size
        self.archive_size = archive_size

    def human_archive_size(self):
        """Return archive size as a human-readable string."""
        return _human_size(self.archive_size)

    def human_original_size(self):
        """Return original total size as a human-readable string."""
        return _human_size(self.original_size)

    def ratio_percent(self):
        """Return compression ratio as a percentage saved.

        Returns 0.0 if original size is 0 to avoid division by zero.
        """
        if self.original_size == 0:
            return 0.0
        return (1 - self.archive_size / self.original_size) * 100


def _resolve_unique_arcname(existing_names, basename):
    """Generate a unique archive entry name to avoid duplicate basenames.

    If 'data.csv' already exists in the archive, returns 'data_1.csv', etc.
    """
    if basename not in existing_names:
        return basename

    stem = pathlib.Path(basename).stem
    suffix = pathlib.Path(basename).suffix
    counter = 1
    while f"{stem}_{counter}{suffix}" in existing_names:
        counter += 1
    return f"{stem}_{counter}{suffix}"


def _get_archive_extension(fmt):
    """Return the file extension for a given format string."""
    if fmt == "tar.gz":
        return ".tar.gz"
    return ".zip"


def _build_output_path(dest_dir, archive_name, fmt, overwrite):
    """Determine the output file path, handling auto-increment if needed."""
    ext = _get_archive_extension(fmt)

    # If archive_name already has the right extension, use it as-is.
    # Otherwise, replace or append the correct extension.
    name_path = pathlib.Path(archive_name)
    if fmt == "tar.gz" and archive_name.endswith(".tar.gz"):
        stem = archive_name[: -len(".tar.gz")]
    elif name_path.suffix == ext:
        stem = name_path.stem
    else:
        stem = name_path.stem

    dest_path = pathlib.Path(dest_dir, f"{stem}{ext}")

    if not overwrite and dest_path.exists():
        counter = 1
        while dest_path.exists():
            dest_path = pathlib.Path(dest_dir, f"{stem}_{counter}{ext}")
            counter += 1

    return dest_path


def make_archive(
    filepaths,
    dest_dir,
    archive_name="compressed.zip",
    fmt="zip",
    compress_level=6,
    overwrite=False,
    cancel_event=None,
):
    """Create a compressed archive from a list of files.

    Args:
        filepaths: List of file path strings to include in the archive.
        dest_dir: Directory where the archive will be created.
        archive_name: Base name for the output file. Defaults to "compressed.zip".
        fmt: Archive format — "zip" or "tar.gz". Defaults to "zip".
        compress_level: Compression level 0-9 (ZIP deflate) or 0-9 (gzip). Defaults to 6.
        overwrite: If True, overwrite an existing archive. If False, auto-increment filename.
        cancel_event: Optional threading.Event; if set, compression is aborted.

    Returns:
        CompressionResult with the output path, file count, sizes, and ratio.

    Raises:
        FileNotFoundError: If a source file does not exist.
        ValueError: If no valid file paths are provided or format is unsupported.
        OSError: If the destination directory is invalid or the disk is full.
        InterruptedError: If compression was cancelled via cancel_event.
    """
    if fmt not in SUPPORTED_FORMATS:
        raise ValueError(f"Unsupported format: {fmt}. Use one of {SUPPORTED_FORMATS}.")

    # Validate paths
    valid_paths = []
    for fp in filepaths:
        fp = fp.strip() if isinstance(fp, str) else str(fp)
        if not fp:
            continue
        p = pathlib.Path(fp)
        if not p.exists():
            raise FileNotFoundError(f"Source file not found: {p}")
        if not p.is_file():
            raise ValueError(f"Not a file: {p}")
        valid_paths.append(p)

    if not valid_paths:
        raise ValueError("No valid files to compress.")

    # Calculate original total size
    original_size = sum(p.stat().st_size for p in valid_paths)

    # Resolve output path
    dest_path = _build_output_path(dest_dir, archive_name, fmt, overwrite)

    # Build archive
    used_arcnames = set()
    file_count = 0

    if fmt == "zip":
        _write_zip(dest_path, valid_paths, used_arcnames, compress_level, cancel_event)
    else:
        _write_tar_gz(dest_path, valid_paths, used_arcnames, compress_level, cancel_event)

    # Check cancellation after writing
    if cancel_event is not None and cancel_event.is_set():
        dest_path.unlink(missing_ok=True)
        raise InterruptedError("Compression cancelled.")

    file_count = len(used_arcnames)
    archive_size = os.path.getsize(dest_path)
    return CompressionResult(dest_path, file_count, original_size, archive_size)


def _write_zip(dest_path, valid_paths, used_arcnames, compress_level, cancel_event):
    """Write files into a ZIP archive."""
    with zipfile.ZipFile(
        dest_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=compress_level
    ) as archive:
        for filepath in valid_paths:
            if cancel_event is not None and cancel_event.is_set():
                break
            arcname = _resolve_unique_arcname(used_arcnames, filepath.name)
            used_arcnames.add(arcname)
            archive.write(filepath, arcname=arcname)


def _write_tar_gz(dest_path, valid_paths, used_arcnames, compress_level, cancel_event):
    """Write files into a tar.gz archive."""
    with tarfile.open(dest_path, "w:gz", compresslevel=compress_level) as archive:
        for filepath in valid_paths:
            if cancel_event is not None and cancel_event.is_set():
                break
            arcname = _resolve_unique_arcname(used_arcnames, filepath.name)
            used_arcnames.add(arcname)
            archive.add(filepath, arcname=arcname)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Compress files into a ZIP or tar.gz archive."
    )
    parser.add_argument(
        "files",
        nargs="+",
        help="Paths to files to compress.",
    )
    parser.add_argument(
        "-d", "--dest",
        default=".",
        help="Destination directory for the archive. Defaults to current directory.",
    )
    parser.add_argument(
        "-n", "--name",
        default="compressed.zip",
        help="Name for the output archive. Defaults to 'compressed.zip'.",
    )
    parser.add_argument(
        "-f", "--format",
        default="zip",
        choices=SUPPORTED_FORMATS,
        help="Archive format. Defaults to 'zip'.",
    )
    parser.add_argument(
        "-l", "--level",
        type=int,
        default=6,
        choices=range(0, 10),
        help="Compression level 0-9 (0=store only, 9=max). Defaults to 6.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing archive instead of auto-renaming.",
    )
    args = parser.parse_args()

    result = make_archive(
        args.files, args.dest, args.name,
        fmt=args.format, compress_level=args.level, overwrite=args.overwrite,
    )
    print(
        f"Archive created: {result.path}\n"
        f"  {result.file_count} files | "
        f"{result.human_original_size()} -> {result.human_archive_size()} "
        f"({result.ratio_percent():.1f}% saved)"
    )
