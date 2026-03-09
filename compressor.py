"""
File Compressor - Frontend Module

A GUI application for compressing files into ZIP archives.
Built with FreeSimpleGUI, this module handles all user interaction
and delegates compression to the zip_creator backend.
"""

import logging
import pathlib
import threading

import FreeSimpleGUI as sg
from zip_creator import make_archive

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ── Event keys for thread communication ──
COMPRESS_DONE = "-COMPRESS-DONE-"
COMPRESS_ERROR = "-COMPRESS-ERROR-"

# ── Compression state ──
cancel_event = threading.Event()
compress_thread = None


def run_compression(window, filepaths, folder, compress_level, overwrite):
    """Run make_archive in a background thread and post the result back to the GUI."""
    try:
        result = make_archive(
            filepaths,
            folder,
            compress_level=compress_level,
            overwrite=overwrite,
            cancel_event=cancel_event,
        )
        window.write_event_value(COMPRESS_DONE, result)
    except Exception as e:
        window.write_event_value(COMPRESS_ERROR, str(e))


def validate_paths(filepaths, folder):
    """Check that every selected file exists and the destination folder is valid.

    Returns:
        (valid_paths, error_message) — error_message is None if everything is fine.
    """
    if not folder or not folder.strip():
        return None, "Please select a destination folder."

    dest = pathlib.Path(folder)
    if not dest.is_dir():
        return None, f"Destination folder does not exist: {folder}"

    valid = []
    for fp in filepaths:
        fp = fp.strip()
        if not fp:
            continue
        p = pathlib.Path(fp)
        if not p.exists():
            return None, f"File not found: {p}"
        if not p.is_file():
            return None, f"Not a file: {p}"
        valid.append(fp)

    if not valid:
        return None, "Please select at least one file."

    return valid, None


def check_overwrite(dest_dir, archive_name="compressed.zip"):
    """If the archive already exists, ask the user what to do.

    Returns:
        True to overwrite, False to auto-rename, or None if the file doesn't exist.
    """
    dest = pathlib.Path(dest_dir, archive_name)
    if not dest.exists():
        return None

    choice = sg.popup_yes_no(
        f'"{archive_name}" already exists in the destination folder.\n\n'
        "Click Yes to overwrite, or No to save with a new name.",
        title="File Exists",
    )
    return choice == "Yes"


def set_ui_compressing(window):
    """Switch UI to the 'compressing' state."""
    window["Compress"].update(disabled=True)
    window["Cancel"].update(disabled=False)
    window["output"].update(value="Compressing...", text_color="orange")
    window.refresh()


def set_ui_idle(window):
    """Switch UI back to the idle state."""
    window["Compress"].update(disabled=False)
    window["Cancel"].update(disabled=True)


# ── Layout ──
layout = [
    [
        sg.Text("Select the file(s) to compress"),
        sg.Input(),
        sg.FilesBrowse("Choose", key="files"),
    ],
    [
        sg.Text("Select the destination folder"),
        sg.Input(),
        sg.FolderBrowse("Choose", key="folder"),
    ],
    [
        sg.Text("Compression level (0 = fast, 9 = max):"),
        sg.Slider(
            range=(0, 9),
            default_value=6,
            orientation="h",
            size=(20, 15),
            key="level",
            enable_events=False,
        ),
    ],
    [
        sg.Button("Compress"),
        sg.Button("Cancel", disabled=True),
        sg.Text(key="output", text_color="white"),
    ],
]

window = sg.Window("File Compressor", layout=layout)

while True:
    event, values = window.read()

    if event == sg.WIN_CLOSED:
        # If a compression is running, signal it to stop before exiting
        if compress_thread is not None and compress_thread.is_alive():
            cancel_event.set()
            compress_thread.join(timeout=5)
        break

    if event == "Compress":
        filepaths = values["files"].split(";")
        folder = values["folder"]
        compress_level = int(values["level"])

        # Validate all inputs before doing anything
        valid_paths, error = validate_paths(filepaths, folder)
        if error:
            window["output"].update(value=error, text_color="red")
            logger.warning("Validation failed: %s", error)
            continue

        # Ask user about overwrite if file exists
        overwrite_choice = check_overwrite(folder)
        overwrite = overwrite_choice is True  # False or None both mean don't overwrite

        # Reset cancel flag and launch background thread
        cancel_event.clear()
        set_ui_compressing(window)

        compress_thread = threading.Thread(
            target=run_compression,
            args=(window, valid_paths, folder, compress_level, overwrite),
            daemon=True,
        )
        compress_thread.start()
        logger.info("Compression started in background thread.")

    elif event == "Cancel":
        cancel_event.set()
        window["output"].update(value="Cancelling...", text_color="orange")
        window["Cancel"].update(disabled=True)
        logger.info("Cancel requested.")

    elif event == COMPRESS_DONE:
        result = values[COMPRESS_DONE]
        window["output"].update(
            value=f"Done: {result.path.name} ({result.file_count} files, {result.human_size()})",
            text_color="white",
        )
        logger.info("Archive created at %s", result.path)
        set_ui_idle(window)

    elif event == COMPRESS_ERROR:
        error_msg = values[COMPRESS_ERROR]
        window["output"].update(value=f"Error: {error_msg}", text_color="red")
        logger.error("Compression failed: %s", error_msg)
        set_ui_idle(window)

window.close()
