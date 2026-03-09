"""
File Compressor - Frontend Module

A GUI application for compressing files into ZIP archives.
Built with FreeSimpleGUI, this module handles all user interaction
and delegates compression to the zip_creator backend.
"""

import logging
import FreeSimpleGUI as sg
from zip_creator import make_archive

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Row 1: File selection
label1 = sg.Text("Select the file(s) to compress")
input1 = sg.Input()
choose_button1 = sg.FilesBrowse("Choose", key="files")

# Row 2: Destination folder
label2 = sg.Text("Select the destination folder")
input2 = sg.Input()
choose_button2 = sg.FolderBrowse("Choose", key="folder")

# Row 3: Compress action and status
compress_button = sg.Button("Compress")
output_label = sg.Text(key="output", text_color="white")

window = sg.Window(
    "File Compressor",
    layout=[
        [label1, input1, choose_button1],
        [label2, input2, choose_button2],
        [compress_button, output_label],
    ],
)

while True:
    event, values = window.read()

    if event == sg.WIN_CLOSED:
        break

    if event == "Compress":
        filepaths = values["files"].split(";")
        folder = values["folder"]

        # Validate that the user actually selected files and a destination
        if not filepaths[0] or not folder:
            window["output"].update(
                value="Please select files and a destination.",
                text_color="red",
            )
            logger.warning("Compress clicked with missing inputs.")
            continue

        # Disable button during compression to prevent double-clicks
        window["Compress"].update(disabled=True)
        window["output"].update(value="Compressing...", text_color="orange")
        window.refresh()

        try:
            output_path = make_archive(filepaths, folder)
            window["output"].update(
                value=f"Compression completed: {output_path.name}",
                text_color="white",
            )
            logger.info("Archive created at %s", output_path)
        except Exception as e:
            window["output"].update(
                value=f"Error: {e}",
                text_color="red",
            )
            logger.error("Compression failed: %s", e)
        finally:
            window["Compress"].update(disabled=False)

window.close()
