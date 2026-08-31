import streamlit as st
from google import genai
from google.genai import types
from fpdf import FPDF
import requests
import urllib.parse
from PIL import Image
import io
import json
import tempfile
import os

st.set_page_config(page_title="AI Storybook Generator", layout="wide", page_icon="📖")

st.title("📖 AI Storybook & Picture Book Generator")
st.write("Generate a custom illustrated storybook and export it directly to PDF.")

# Sidebar for configuration
with st.sidebar:
    st.header("Configuration")
    gemini_key = st.text_input("Enter Gemini API Key", type="password")
    st.markdown("[Get a free Gemini API Key](https://aistudio.google.com/)")
    
    art_style = st.selectbox(
        "Illustration Art Style",
        [
            "Whimsical watercolor illustration, children's storybook",
            "Pixar 3D animated movie render, soft volumetric lighting",
            "Classic vintage fairy tale pencil drawing",
            "Vibrant digital comic book style, bold outlines"
        ]
    )
    pages_count = st.slider("Number of Pages", min_value=3, max_value=8, value=4)

story_prompt = st.text_area("What is your story about?", placeholder="e.g., A curious little fox named Oliver who discovers a hidden glowing tree in an autumn forest.")

class StoryPDF(FPDF):
    def header(self):
        pass
    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 9)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"Page {self.page_no()}", 0, 0, "C")

def generate_story(api_key, user_prompt, style, num_pages):
    client = genai.Client(api_key=api_key)
    
    system_instruction = f"""
    You are an expert children's story writer and visual director.
    Create an engaging story based on the prompt in exactly {num_pages} pages.
    Maintain strict visual consistency for characters.
    
    Return a STRICT JSON object matching this structure:
    {{
      "title": "Book Title",
      "character_description": "Detailed fixed description of the protagonist (colors, clothing, species)",
      "pages": [
        {{
          "page_number": 1,
          "story_text": "Story sentences for this page (max 40 words).",
          "image_prompt": "Scene visual description without style keywords"
        }}
      ]
    }}
    """
    
    response = client.models.generate_content(
     model='gemini-3.6-flash',
        contents=f"Story Idea: {user_prompt}",
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json"
        )
    )
    return json.loads(response.text)

import time
from PIL import ImageDraw

def create_fallback_image(text="Image generation timed out"):
    """Creates a blank placeholder image so the PDF generation never fails."""
    img = Image.new('RGB', (800, 800), color=(245, 245, 245))
    draw = ImageDraw.Draw(img)
    draw.rectangle([20, 20, 780, 780], outline=(200, 200, 200), width=3)
    draw.text((300, 390), text, fill=(120, 120, 120))
    return img

def fetch_image(prompt, style, character_desc, is_coloring=False):
    if is_coloring:
        full_prompt = f"black and white coloring book page, clean bold outlines, line art, white background, no shading, {character_desc}, {prompt}"
    else:
        full_prompt = f"{style}, {character_desc}, {prompt}, 8k"
        
    encoded_prompt = urllib.parse.quote(full_prompt)
    # Using model=turbo & 512x512 resolution for much faster, reliable generation
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=512&height=512&nologo=true&model=turbo"
    
    for attempt in range(3):
        try:
            res = requests.get(url, timeout=60)
            if res.status_code == 200 and len(res.content) > 1000:
                return Image.open(io.BytesIO(res.content))
        except (requests.exceptions.RequestException, Exception):
            time.sleep(2)
            
    return create_fallback_image("Scene rendering took too long")

def build_pdf(book_data, image_list):
    pdf = StoryPDF(orientation='P', unit='mm', format='A4')
    pdf.set_auto_page_break(auto=False)
    
    # Cover Page
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 26)
    pdf.ln(40)
    pdf.multi_cell(0, 12, book_data.get("title", "My Storybook"), align='C')
    pdf.ln(10)
    pdf.set_font("Helvetica", "I", 14)
    pdf.cell(0, 10, "Generated with AI", ln=True, align='C')
    
    # Story Pages
    for idx, page in enumerate(book_data.get("pages", [])):
        pdf.add_page()
        
        # Save temp image for PDF insertion
        img = image_list[idx]
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_file:
            img.save(tmp_file.name)
            temp_path = tmp_file.name
        
        # Draw image (Centered square)
        pdf.image(temp_path, x=35, y=30, w=140, h=140)
        os.remove(temp_path)
        
        # Text block
        pdf.set_y(185)
        pdf.set_font("Helvetica", "", 14)
        pdf.multi_cell(0, 8, page.get("story_text", ""), align='C')
        
    return bytes(pdf.output())

# Generation Flow
if st.button("✨ Generate Full Book", type="primary"):
    if not gemini_key:
        st.error("Please enter your Gemini API Key in the sidebar.")
    elif not story_prompt.strip():
        st.error("Please provide a prompt describing your story.")
    else:
        with st.spinner("Writing story and scene outlines..."):
            try:
                book = generate_story(gemini_key, story_prompt, art_style, pages_count)
            except Exception as e:
                st.error(f"Failed to generate story text: {e}")
                st.stop()
        
        st.success(f"Story created: **{book.get('title', 'Untitled')}**")
        
        images = []
        progress_bar = st.progress(0)
        
        for idx, page_item in enumerate(book.get("pages", [])):
            with st.spinner(f"Rendering illustration for page {idx + 1}..."):
                img = fetch_image(
                    page_item.get("image_prompt", ""),
                    art_style,
                    book.get("character_description", "")
                )
                images.append(img)
            progress_bar.progress((idx + 1) / len(book.get("pages", [])))
        
        st.subheader("Book Preview")
        cols = st.columns(2)
        for idx, page_item in enumerate(book.get("pages", [])):
            col_idx = idx % 2
            with cols[col_idx]:
                st.image(images[idx], caption=f"Page {idx+1}")
                st.write(page_item.get("story_text", ""))
                st.divider()
        
        with st.spinner("Compiling PDF document..."):
            pdf_bytes = build_pdf(book, images)
            
        st.download_button(
            label="📥 Download Complete PDF Book",
            data=pdf_bytes,
            file_name=f"{book.get('title', 'storybook').replace(' ', '_').lower()}.pdf",
            mime="application/pdf"
        )
