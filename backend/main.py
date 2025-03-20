from fastapi import FastAPI, HTTPException, UploadFile, File, Query
from pydantic import BaseModel
from pdf_parser import pdf_to_markdown  # Your existing pdf_to_markdown function
from gcs_utils import list_files_in_gcs, download_file_from_gcs,get_file_content
from chunking import process_and_upload_chunked_data
from gen_embedding import process_and_store_embeddings
from io import BytesIO
import json
from search import search_from_content,generate_response
import os

app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "Welcome to the FastAPI PDF Processing & Q/A Service"}

@app.get("/list_pdf_files")
def list_files_in_pdf_folder():
    """List all PDF files from the 'pdf_files' folder in GCS."""
    folder_name = "pdf_files"
    files = list_files_in_gcs(folder_name)
    return {"files": files}

@app.post("/upload_and_parse_pdf/")
async def upload_and_parse_pdf(file: UploadFile = File(...), parse_method: str = Query("pymupdf", enum=["pymupdf", "mistral", "docling"])):
    """Upload a PDF, parse it using a selected method, and convert it to Markdown."""
    try:
        if parse_method == "pymupdf":
            markdown_content = await pdf_to_markdown(file)
        elif parse_method == "mistral":
            print("awaiting code")
        elif parse_method == "docling":
            print("awaiting code")
        else:
            raise HTTPException(status_code=400, detail="Invalid parse method selected.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error while parsing the PDF: {str(e)}")
    
    return {"markdown_content": markdown_content}

# Helper function to handle BytesIO and pass the original file name
async def pdf_to_markdown_from_bytes(file: BytesIO, filename: str):
    """Extracts text from a PDF-like object and returns it as markdown."""
    
    # Create a mock UploadFile from the BytesIO object
    class MockUploadFile:
        def __init__(self, file_like_object, filename):
            self.file = file_like_object
            self.filename = filename  # Pass the original filename

        async def read(self):
            return self.file.read()

    # Pass the BytesIO as a mock UploadFile object to the original pdf_to_markdown function
    mock_file = MockUploadFile(file, filename)
    return await pdf_to_markdown(mock_file)

@app.get("/parse_gcs_pdf/")
async def parse_gcs_pdf(file_name: str = Query(...), parse_method: str = Query("pymupdf", enum=["pymupdf", "mistral", "docling"])):
    """Parse a selected PDF file from GCS."""
    try:
        # Download the file content as bytes from GCS
        file_content = download_file_from_gcs(file_name)  # This returns file content as bytes
      
        if not file_content:
            raise HTTPException(status_code=404, detail="File not found in GCS")
        
        if file_name.startswith("pdf_files/"):
            file_name = file_name[len("pdf_files/"):]

        # Convert the byte content into a file-like object using BytesIO
        file_like_object = BytesIO(file_content)
        
        # Call the corresponding parsing method based on the `parse_method` parameter
        if parse_method == "pymupdf":
            markdown_content = await pdf_to_markdown_from_bytes(file_like_object, file_name)
        elif parse_method == "mistral":
            markdown_content = await pdf_to_markdown_mistral(file_like_object, file_name)
        elif parse_method == "docling":
            markdown_content = await pdf_to_markdown_docling(file_like_object, file_name)
        else:
            raise HTTPException(status_code=400, detail="Invalid parse method selected.")
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error while parsing the PDF: {str(e)}")
    
    return {"markdown_content": markdown_content}

@app.get("/list_extracted_files")
def list_files_in_pdf_folder():
    """List all PDF files from the 'pdf_files' folder in GCS."""
    folder_name = "outputs"
    files = list_files_in_gcs(folder_name)
    return {"files": files}


@app.get("/fetch_file/")
async def fetch_file_from_gcs(
    file_name: str = Query(None, description="File name to fetch"),
    strategy: str = Query("fixed", enum=["fixed", "sentence", "sliding"], description="Chunking strategy")
):
    """Fetch the content of a file from GCS and process it with chunking."""
    
    try:
        # If file_name is not provided, get the list of available files
        if file_name is None:
            files = list_files_in_gcs("outputs")
            if not files:
                raise HTTPException(status_code=404, detail="No files available in GCS")
            file_name = files[0]  # Default to the first file in the list
        
        # Download the file content as bytes from GCS
        file_content = download_file_from_gcs(file_name)  # This returns file content as bytes
        
        if not file_content:
            raise HTTPException(status_code=404, detail="File not found in GCS")
        
        # Decode file content to text
        file_text = file_content.decode("utf-8")  # Assuming it's UTF-8 encoded text

        # Call chunking function from chunking.py
        output_file_name = f"chunked_{file_name}"
        process_and_upload_chunked_data(file_text, output_file_name, strategy)

        return {"file_name": file_name, "strategy": strategy, "message": "File processed and chunked successfully"}

    except Exception as e:
        # Handle any unexpected errors
        raise HTTPException(status_code=500, detail=f"Error fetching file: {e}")


@app.get("/list_chunked_output_files")
def list_files_in_chunked_folder():
    """List all PDF files from the 'pdf_files' folder in GCS."""
    folder_name = "chunked_outputs"
    files = list_files_in_gcs(folder_name)
    return {"files": files}

@app.get("/fetch_file_content")
def fetch_file_content(file_name: str):
    """Fetch the content of a file from GCS, generate embeddings, and upload the result to GCS."""
    try:
        # Fetch file content using the get_file_content function from gcs_utils.py
        content = get_file_content(file_name)

        # Prepare content to pass to gen_embedding
        content_dict = {file_name: [content]}  # Assuming the content is in a list format
        
        # Define the destination blob name for the embeddings file in GCS
        destination_blob_name = f"embeddings/{file_name}"

        # Process and upload embeddings using gen_embedding.py
        file_url = process_and_store_embeddings(content_dict, destination_blob_name)
        
        return {"file_name": file_name, "status": "Embeddings processed and uploaded.", "file_url": file_url}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing embeddings: {e}")
    
@app.get("/list_embedded_output_files")
def list_files_in_embedded_folder():
    """List all PDF files from the 'pdf_files' folder in GCS."""
    folder_name = "embeddings"
    files = list_files_in_gcs(folder_name)
    return {"files": files}

@app.get("/fetch_embedded_file_content")
def search_embedded_file(file_name: str, query: str, quarter_filter: str = None, top_n: int = 5):
    """
    Fetch content of an embedded file, process it, and return the search results along with the GPT-40-mini response.
    """
    try:
        if not query:
            raise HTTPException(status_code=400, detail="Query parameter is required.")

        # ✅ Fetch file content from GCS
        content = get_file_content(file_name)

        # ✅ Parse the JSON content into a Python dictionary
        embedded_data = json.loads(content)

        # ✅ Perform the search directly on the content
        results = search_from_content(
            content=embedded_data,      
            query=query,
            quarter_filter=quarter_filter,
            top_n=top_n
        )
   
        # ✅ Generate the GPT-40-mini response using retrieved chunks
        gpt_response = generate_response(query, results)

        # ✅ Return the results and the GPT response directly
        return {
            "file_name": file_name,
            "query": query,
            "results": results,  # Directly return the raw results from search.py
            "gpt_response": gpt_response  # Include the GPT-generated response
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process and search: {e}")