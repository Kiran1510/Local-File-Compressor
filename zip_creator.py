"""
ZIP Creator - Backend Module

Provides file compression functionality using Python's zipfile module.
Can be used as an imported module or run standalone via CLI.
"""

import argparse
import os
import pathlib
import zipfile


class CompressionResult:
    """Container for compression output metadata."""

    def __init__(self, path, file_count, archive_size):
        self.path = path
        self.file_count = file_count
        self.archive_size = archive_size

    def human_size(self):
        """Return archive size as a human-readable string."""
        size = self.archive_size
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"


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


def make_archive(
    filepaths,
    dest_dir,
    archive_name="compressed.zip",
    compress_level=6,
    overwrite=False,
    cancel_event=None,
):
    """Create a ZIP archive from a list of files.

    Args:
        filepaths: List of file path strings to include in the archive.
        dest_dir: Directory where the ZIP file will be created.
        archive_name: Name for the output ZIP file. Defaults to "compressed.zip".
        compress_level: Deflate compression level 0-9 (0=fast/none, 9=max). Defaults to 6.
        overwrite: If True, overwrite an existing archive. If False, auto-increment filename.
        cancel_event: Optional threading.Event; if set, compression is aborted.

    Returns:
        CompressionResult with the output path, file count, and archive size.

    Raises:
        FileNotFoundError: If a source file does not exist.
        ValueError: If no valid file paths are provided.
        OSError: If the destination directory is invalid or the disk is full.
        InterruptedError: If compression was cancelled via cancel_event.
    """
    # Validate that we have actual paths to work with
    valid_paths = []
    for fp in filepaths:
        fp = fp.strip()
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

    # Resolve output path
    dest_path = pathlib.Path(dest_dir, archive_name)

    if not overwrite and dest_path.exists():
        stem = pathlib.Path(archive_name).stem
        suffix = pathlib.Path(archive_name).suffix
        counter = 1
        while dest_path.exists():
            dest_path = pathlib.Path(dest_dir, f"{stem}_{counter}{suffix}")
            counter += 1

    # Compress with duplicate basename handling
    used_arcnames = set()
    file_count = 0

    with zipfile.ZipFile(
        dest_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=compress_level
    ) as archive:
        for filepath in valid_paths:
            # Check for cancellation between files
            if cancel_event is not None and cancel_event.is_set():
                break

            arcname = _resolve_unique_arcname(used_arcnames, filepath.name)
            used_arcnames.add(arcname)
            archive.write(filepath, arcname=arcname)
            file_count += 1

    # If cancelled, clean up the partial archive
    if cancel_event is not None and cancel_event.is_set():
        dest_path.unlink(missing_ok=True)
        raise InterruptedError("Compression cancelled.")

    archive_size = os.path.getsize(dest_path)
    return CompressionResult(dest_path, file_count, archive_size)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Compress files into a ZIP archive."
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
        compress_level=args.level, overwrite=args.overwrite,
    )
    print(f"Archive created: {result.path} ({result.file_count} files, {result.human_size()})")
