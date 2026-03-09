"""
File Compressor - Frontend Module

A GUI application for compressing files into archives (ZIP or tar.gz).
Built with FreeSimpleGUI, this module handles all user interaction
and delegates compression to the zip_creator backend.

Features:
    - File list with individual removal
    - Archive format selection (ZIP, tar.gz)
    - Adjustable compression level
    - Compression ratio display
    - Persistent last-used destination folder
    - Dark / light theme toggle
    - Threaded compression with cancel support
"""

import json
import logging
import pathlib
import threading

import FreeSimpleGUI as sg
from zip_creator import make_archive, SUPPORTED_FORMATS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ── Config persistence ──
CONFIG_PATH = pathlib.Path.home() / ".file_compressor_config.json"
THEMES = {"Dark": "DarkBlue3", "Light": "LightGrey1"}


def load_config():
    """Load saved preferences from disk."""
    defaults = {"last_folder": "", "theme": "Dark"}
    try:
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH, "r") as f:
                saved = json.load(f)
            defaults.update(saved)
    except Exception:
        pass
    return defaults


def save_config(config):
    """Persist preferences to disk."""
    try:
        with open(CONFIG_PATH, "w") as f:
            json.dump(config, f)
    except Exception as e:
        logger.warning("Could not save config: %s", e)


# ── Event keys ──
COMPRESS_DONE = "-COMPRESS-DONE-"
COMPRESS_ERROR = "-COMPRESS-ERROR-"

# ── State ──
cancel_event = threading.Event()
compress_thread = None
selected_files = []  # list of absolute path strings


def run_compression(window, filepaths, folder, fmt, compress_level, overwrite):
    """Run make_archive in a background thread and post the result back."""
    try:
        result = make_archive(
            filepaths,
            folder,
            fmt=fmt,
            compress_level=compress_level,
            overwrite=overwrite,
            cancel_event=cancel_event,
        )
        window.write_event_value(COMPRESS_DONE, result)
    except Exception as e:
        window.write_event_value(COMPRESS_ERROR, str(e))


def add_files(new_paths):
    """Add file paths to the selected list, skipping duplicates."""
    added = 0
    for fp in new_paths:
        fp = fp.strip()
        if not fp:
            continue
        fp = str(pathlib.Path(fp).resolve())
        if fp not in selected_files:
            selected_files.append(fp)
            added += 1
    return added


def refresh_file_list(window):
    """Update the listbox display from selected_files."""
    display = [pathlib.Path(f).name for f in selected_files]
    window["-FILELIST-"].update(values=display)
    window["-FILECOUNT-"].update(value=f"{len(selected_files)} file(s) selected")


def check_overwrite(dest_dir, fmt):
    """If the default archive already exists, ask the user what to do."""
    ext = ".tar.gz" if fmt == "tar.gz" else ".zip"
    dest = pathlib.Path(dest_dir, f"compressed{ext}")
    if not dest.exists():
        return None

    choice = sg.popup_yes_no(
        f'"compressed{ext}" already exists in the destination folder.\n\n'
        "Click Yes to overwrite, or No to save with a new name.",
        title="File Exists",
    )
    return choice == "Yes"


def set_ui_compressing(window):
    """Switch UI to the 'compressing' state."""
    window["Compress"].update(disabled=True)
    window["Cancel"].update(disabled=False)
    window["-ADD-"].update(disabled=True)
    window["-REMOVE-"].update(disabled=True)
    window["-CLEAR-"].update(disabled=True)
    window["-STATUS-"].update(value="Compressing...", text_color="orange")
    window.refresh()


def set_ui_idle(window):
    """Switch UI back to the idle state."""
    window["Compress"].update(disabled=False)
    window["Cancel"].update(disabled=True)
    window["-ADD-"].update(disabled=False)
    window["-REMOVE-"].update(disabled=False)
    window["-CLEAR-"].update(disabled=False)


def build_layout(config):
    """Construct the window layout."""
    file_frame = sg.Frame("Files to Compress", [
        [
            sg.Listbox(
                values=[],
                size=(55, 8),
                key="-FILELIST-",
                enable_events=True,
                select_mode=sg.LISTBOX_SELECT_MODE_EXTENDED,
                expand_x=True,
            ),
        ],
        [
            sg.Button("Add Files", key="-ADD-"),
            sg.Button("Remove Selected", key="-REMOVE-"),
            sg.Button("Clear All", key="-CLEAR-"),
            sg.Text("0 file(s) selected", key="-FILECOUNT-"),
        ],
    ], expand_x=True)

    dest_frame = sg.Frame("Destination", [
        [
            sg.Text("Folder:"),
            sg.Input(default_text=config.get("last_folder", ""), key="-DEST-", expand_x=True),
            sg.FolderBrowse("Choose", key="-DESTBROWSE-", target="-DEST-"),
        ],
    ], expand_x=True)

    options_frame = sg.Frame("Options", [
        [
            sg.Text("Format:"),
            sg.Combo(
                list(SUPPORTED_FORMATS),
                default_value="zip",
                key="-FORMAT-",
                readonly=True,
                size=(10, 1),
            ),
            sg.Text("   Compression level:"),
            sg.Slider(
                range=(0, 9),
                default_value=6,
                orientation="h",
                size=(18, 15),
                key="-LEVEL-",
                enable_events=False,
            ),
        ],
    ], expand_x=True)

    status_frame = sg.Frame("Status", [
        [sg.Text("Ready.", key="-STATUS-", size=(65, 1), text_color="white", expand_x=True)],
        [sg.Text("", key="-RATIO-", size=(65, 1), text_color="cyan", expand_x=True)],
    ], expand_x=True)

    layout = [
        [file_frame],
        [dest_frame],
        [options_frame],
        [
            sg.Button("Compress", size=(12, 1)),
            sg.Button("Cancel", size=(12, 1), disabled=True),
            sg.Push(),
            sg.Button("Toggle Theme", key="-THEME-", size=(14, 1)),
        ],
        [status_frame],
    ]
    return layout


def main():
    global compress_thread, selected_files

    config = load_config()
    current_theme = config.get("theme", "Dark")
    sg.theme(THEMES[current_theme])

    window = sg.Window(
        "File Compressor",
        layout=build_layout(config),
        finalize=True,
        resizable=True,
        enable_close_attempted_event=True,
    )

    while True:
        event, values = window.read()

        # ── Window close ──
        if event in (sg.WIN_CLOSED, sg.WINDOW_CLOSE_ATTEMPTED_EVENT):
            if compress_thread is not None and compress_thread.is_alive():
                cancel_event.set()
                compress_thread.join(timeout=5)
            # Save last-used folder
            folder = values.get("-DEST-", "") if values else ""
            config["last_folder"] = folder
            config["theme"] = current_theme
            save_config(config)
            break

        # ── Theme toggle ──
        if event == "-THEME-":
            current_theme = "Light" if current_theme == "Dark" else "Dark"
            config["theme"] = current_theme
            sg.theme(THEMES[current_theme])

            # Save current state, rebuild window
            folder = values.get("-DEST-", "")
            config["last_folder"] = folder
            fmt = values.get("-FORMAT-", "zip")
            level = int(values.get("-LEVEL-", 6))

            window.close()
            window = sg.Window(
                "File Compressor",
                layout=build_layout(config),
                finalize=True,
                resizable=True,
                enable_close_attempted_event=True,
            )
            # Restore state
            window["-FORMAT-"].update(value=fmt)
            window["-LEVEL-"].update(value=level)
            refresh_file_list(window)
            continue

        # ── Add files via dialog ──
        if event == "-ADD-":
            files = sg.popup_get_file(
                "Select files to add",
                multiple_files=True,
                no_window=True,
                file_types=(("All Files", "*.*"),),
            )
            if files:
                if isinstance(files, str):
                    files = files.split(";")
                add_files(files)
                refresh_file_list(window)

        # ── Remove selected files ──
        if event == "-REMOVE-":
            indices = window["-FILELIST-"].get_indexes()
            if indices:
                for idx in sorted(indices, reverse=True):
                    if idx < len(selected_files):
                        removed = selected_files.pop(idx)
                        logger.info("Removed: %s", removed)
                refresh_file_list(window)

        # ── Clear all files ──
        if event == "-CLEAR-":
            selected_files.clear()
            refresh_file_list(window)
            window["-STATUS-"].update(value="Ready.", text_color="white")
            window["-RATIO-"].update(value="")

        # ── Compress ──
        if event == "Compress":
            folder = values["-DEST-"]
            fmt = values["-FORMAT-"]
            compress_level = int(values["-LEVEL-"])

            # Validate
            if not selected_files:
                window["-STATUS-"].update(
                    value="Please add at least one file.", text_color="red"
                )
                continue

            if not folder or not folder.strip():
                window["-STATUS-"].update(
                    value="Please select a destination folder.", text_color="red"
                )
                continue

            if not pathlib.Path(folder).is_dir():
                window["-STATUS-"].update(
                    value=f"Destination does not exist: {folder}", text_color="red"
                )
                continue

            # Validate all file paths still exist
            missing = [f for f in selected_files if not pathlib.Path(f).exists()]
            if missing:
                name = pathlib.Path(missing[0]).name
                window["-STATUS-"].update(
                    value=f"File no longer exists: {name}", text_color="red"
                )
                continue

            # Overwrite check
            overwrite_choice = check_overwrite(folder, fmt)
            overwrite = overwrite_choice is True

            # Launch background thread
            cancel_event.clear()
            window["-RATIO-"].update(value="")
            set_ui_compressing(window)

            compress_thread = threading.Thread(
                target=run_compression,
                args=(window, list(selected_files), folder, fmt, compress_level, overwrite),
                daemon=True,
            )
            compress_thread.start()
            logger.info("Compression started (%s, level %d).", fmt, compress_level)

        # ── Cancel ──
        elif event == "Cancel":
            cancel_event.set()
            window["-STATUS-"].update(value="Cancelling...", text_color="orange")
            window["Cancel"].update(disabled=True)
            logger.info("Cancel requested.")

        # ── Compression finished ──
        elif event == COMPRESS_DONE:
            result = values[COMPRESS_DONE]
            window["-STATUS-"].update(
                value=(
                    f"Done: {result.path.name} "
                    f"({result.file_count} files, {result.human_archive_size()})"
                ),
                text_color="white",
            )
            window["-RATIO-"].update(
                value=(
                    f"Original: {result.human_original_size()} -> "
                    f"Compressed: {result.human_archive_size()} "
                    f"({result.ratio_percent():.1f}% saved)"
                ),
                text_color="cyan",
            )
            logger.info("Archive created at %s", result.path)

            # Save the folder for next time
            config["last_folder"] = str(pathlib.Path(result.path).parent)
            save_config(config)
            set_ui_idle(window)

        # ── Compression error ──
        elif event == COMPRESS_ERROR:
            error_msg = values[COMPRESS_ERROR]
            window["-STATUS-"].update(value=f"Error: {error_msg}", text_color="red")
            window["-RATIO-"].update(value="")
            logger.error("Compression failed: %s", error_msg)
            set_ui_idle(window)

    window.close()


if __name__ == "__main__":
    main()
