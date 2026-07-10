# =========================================================================
# PHOTO EVIDENCE COMPRESSION & SUPABASE STORAGE (utils/storage_engine.py)
# =========================================================================
import io
import uuid

import streamlit as st
from PIL import Image
from supabase import Client, create_client

# Grab existing credentials from your Streamlit secrets or environment
SUPABASE_URL = st.secrets.get("SUPABASE_URL", "https://your-project.supabase.co")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", "your-service-role-or-anon-key")

supabase_client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
BUCKET_NAME = "breeding-evidence"

def compress_and_upload_image(uploaded_file) -> str:
    """
    Accepts a raw uploaded file, compresses it to JPEG format with optimized
    dimensions, uploads it to Supabase Storage, and returns its public URL.
    """
    try:
        # 1. Open the image using Pillow
        img = Image.open(uploaded_file)

        # Convert RGBA/Palette profiles to standard RGB for JPEG safety
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        # 2. Downscale image if it exceeds standard HD resolution to preserve storage
        max_dimension = 1200
        img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)

        # 3. Compress image array into a memory byte stream
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format="JPEG", quality=75, optimize=True)
        img_bytes = img_byte_arr.getvalue()

        # 4. Construct an unrepeatable cryptographic filename partition
        unique_filename = f"site_evidence_{uuid.uuid4().hex}.jpg"

        # 5. Upload raw byte payload directly into Supabase Storage
        # Ensure your bucket 'breeding-evidence' is created and set to 'Public' in Supabase
        supabase_client.storage.from_(BUCKET_NAME).upload(
            path=unique_filename,
            file=img_bytes,
            file_options={"content-type": "image/jpeg"}
        )

        # 6. Resolve and return the fully qualified public asset URL
        public_url = supabase_client.storage.from_(BUCKET_NAME).get_public_url(unique_filename)
        return public_url

    except Exception as e:
        st.error(f"Media storage upload pipeline fault: {e}")
        return ""
