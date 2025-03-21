import logging
import time
from pathlib import Path
from docling_core.types.doc import ImageRefMode
from docling.document_converter import DocumentConverter
from gcs_utils import upload_to_gcs  # Assuming you have a function for GCS upload
from io import BytesIO

def process_pdf(pdf_path, output_dir, gcs_output_bucket="pdfstorage_1"):
    """Process a single PDF file and save its Markdown output."""
    logging.basicConfig(level=logging.INFO)
    input_doc_path = Path(pdf_path)
    output_dir = Path(output_dir)

    # Initialize the DocumentConverter
    doc_converter = DocumentConverter()

    start_time = time.time()
    try:
        # Convert the document
        conv_res = doc_converter.convert(input_doc_path)

        # Ensure the output directory exists
        output_dir.mkdir(parents=True, exist_ok=True)

        # Save markdown with embedded images
        md_filename_embedded = output_dir / f"{input_doc_path.stem}-with-images.md"
        conv_res.document.save_as_markdown(md_filename_embedded, image_mode=ImageRefMode.EMBEDDED)
        logging.info(f"Saved Markdown with embedded images: {md_filename_embedded}")

        # Save markdown with externally referenced images
        md_filename_referenced = output_dir / f"{input_doc_path.stem}-with-image-refs.md"
        conv_res.document.save_as_markdown(md_filename_referenced, image_mode=ImageRefMode.REFERENCED)
        logging.info(f"Saved Markdown with referenced images: {md_filename_referenced}")

        # Upload the markdown files to GCS (using file-like objects)
        with open(md_filename_embedded, 'rb') as file_embedded:
            file_stream_embedded = BytesIO(file_embedded.read())  # Convert file to BytesIO
            upload_to_gcs(file_stream_embedded, f"outputs/{md_filename_embedded.name}")

        with open(md_filename_referenced, 'rb') as file_referenced:
            file_stream_referenced = BytesIO(file_referenced.read())  # Convert file to BytesIO
            upload_to_gcs(file_stream_referenced, f"output/{md_filename_referenced.name}")

        # Clean up the local markdown files after upload if needed
        md_filename_embedded.unlink()
        md_filename_referenced.unlink()

        end_time = time.time() - start_time
        logging.info(f"Document converted and saved in {end_time:.2f} seconds. Files uploaded to GCS bucket: {gcs_output_bucket}")
    except Exception as e:
        logging.error(f"Failed to process {pdf_path}: {e}")
