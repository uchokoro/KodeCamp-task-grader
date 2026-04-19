import os

import nbformat
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

_ = load_dotenv(find_dotenv())
source_dir = os.getenv("DOCUMENTS_DOWNLOAD_FOLDER", "")


def extract_ipynb_to_txt(
    ipynb_dir: str | Path, filename: str, text_subdir_name: str = "as_text"
) -> None:
    """
    Extracts the content of a .ipynb file and saves it as a plain text file.

    Args:
        ipynb_dir: Directory containing the .ipynb file.
        filename (str): The name of the input .ipynb file.
        text_subdir_name: The name of the output text subdir within the ipynb directory.
    """
    if not isinstance(ipynb_dir, Path):
        ipynb_dir = Path(ipynb_dir)

    if not ipynb_dir.is_dir():
        raise ValueError(f"ipynb_dir={ipynb_dir} is not a directory")

    ipynb_filepath = ipynb_dir / f"{filename}.ipynb"

    if not ipynb_filepath.is_file():
        raise FileNotFoundError(f"No file found at {ipynb_filepath}")

    output_dir = ipynb_dir / f"{text_subdir_name}"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_filepath = output_dir / f"{filename}.txt"

    try:
        with open(ipynb_filepath, "r", encoding="utf-8") as in_file:
            notebook_content = nbformat.read(in_file, as_version=4)

        extracted_text = []

        for cell in notebook_content.cells:
            # Extract the code from code cells
            if cell.cell_type == "code":
                extracted_text.append(f"## Code Cell:\n{cell.source}\n")

                # Extract code execution output
                for output in cell.outputs:
                    if output.output_type == "stream":
                        # For print statements, stdout/stderr
                        extracted_text.append(
                            f"### Print statement or stdout/stderr output:\n{output.text}\n"
                        )
                    elif (
                        output.output_type == "display_data"
                        or output.output_type == "execute_result"
                    ):
                        # For display_data (e.g., images, HTML) or execution results
                        if "text/plain" in output.data:
                            extracted_text.append(
                                f"### Execution result:\n{output.data['text/plain']}\n"
                            )
            elif cell.cell_type == "markdown":
                extracted_text.append(f"## Markdown Cell:\n{cell.source}\n")

        with open(output_filepath, "w", encoding="utf-8") as out_file:
            out_file.write("\n\n".join(extracted_text))

        print(
            f"Successfully extracted the contents of  `{filename}.ipynb` to `{filename}.txt`"
        )

    except FileNotFoundError:
        print(f"Error: The file '{ipynb_filepath}' was not found.")
    except Exception as ex:
        print(f"An error occurred: {ex}")
