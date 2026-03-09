"""
ZIP Creator - Backend Module

Provides file compression functionality using Python's zipfile module.
Can be used as an imported module or run standalone via CLI.
"""

import argparse
import pathlib
import zipfile


def make_archive(filepaths, dest_dir, archive_name="compressed.zip"):
    """Create a ZIP archive from a list of files.

    Args:
        filepaths: List of file path strings to include in the archive.
        dest_dir: Directory where the ZIP file will be created.
        archive_name: Name for the output ZIP file. Defaults to "compressed.zip".

    Returns:
        pathlib.Path pointing to the created archive.

    Raises:
        FileNotFoundError: If a source file does not exist.
        FileExistsError: If the output archive already exists.
        OSError: If the destination directory is invalid or disk is full.
    """
    dest_path = pathlib.Path(dest_dir, archive_name)

    # Overwrite protection
    if dest_path.exists():
        # Auto-increment filename: compressed_1.zip, compressed_2.zip, etc.
        stem = pathlib.Path(archive_name).stem
        suffix = pathlib.Path(archive_name).suffix
        counter = 1
        while dest_path.exists():
            dest_path = pathlib.Path(dest_dir, f"{stem}_{counter}{suffix}")
            counter += 1

    with zipfile.ZipFile(dest_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for filepath in filepaths:
            filepath = pathlib.Path(filepath)
            if not filepath.exists():
                raise FileNotFoundError(f"Source file not found: {filepath}")
            archive.write(filepath, arcname=filepath.name)

    return dest_path


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
    args = parser.parse_args()

    output = make_archive(args.files, args.dest, args.name)
    print(f"Archive created: {output}")
