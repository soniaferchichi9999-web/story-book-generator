import streamlit as st
from google import genai
from google.genai import types
from fpdf import FPDF
import requests
import urllib.parse
from PIL import Image, ImageDraw
import io
import json
import tempfile
import os
import time

st.set_page_config(page_title="AI Story & Activity Book Generator", layout="wide", page_icon="🎨")

st.title("🎨 AI Storybook & Activity Book Generator")
st.write("Generate an illustrated children's storybook complete with coloring pages, trivia quizzes, and word hunt games — downloadable as a PDF.")

# Sidebar Configuration
with st.sidebar:
    st.header("⚙️ Settings")
    gemini_key = st.text_input("Gemini API Key", type="password")
    st.markdown("[Get a free Gemini API Key](https://aistudio.google.com/)")
    
    art_style = st.selectbox(
        "Illustration Art Style",
        [
            "Whimsical watercolor illustration, children's storybook",
            "Pixar 3D animated movie render, soft lighting",
            "Classic vintage fairy tale pencil drawing",
            "Vibrant digital comic book style, bold outlines"
        ]
    )
    pages_count = st.slider("Story Pages", min_value=3, max_value=6, value=4)
    include_activities = st.checkbox("Include Coloring & Activity Pages", value=True)

story_prompt = st.text_area(
    "What is your story idea?",
    placeholder="e.g., A brave little red panda named Pip wearing a yellow backpack who finds a glowing crystal in a misty bamboo forest."
)

class ActivityBookPDF(FPDF):
    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 9)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"Page {self.page_no()}", 0, 0, "C")

def create_fallback_image(text="Image generation timed out"):
    """Generates a clean placeholder frame if the image API server is unreachable."""
    img = Image.new('RGB', (600, 600), color=(245, 245, 245))
    draw = ImageDraw.Draw(img)
    draw.rectangle([20, 20, 580, 580], outline=(200, 200, 200), width=3)
    draw.text((180, 290), text, fill=(120, 120, 120))
    return img

def generate_book_and_activities(api_key, user_prompt, num_pages):
    client = genai.Client(api_key=api_key)
    
    system_instruction = f"""
    You are an expert children's author and activity book designer.
    Write an engaging story based on the user's prompt in exactly {num_pages} pages.
    Maintain strict visual consistency for the protagonist.
    Also provide coloring prompts and story-based comprehension activities.
    
    Return a STRICT JSON object matching this schema:
    {{
      "title": "Book Title",
      "character_description": "Detailed fixed description of the protagonist (clothing, colors, species)",
      "pages": [
        {{
          "page_number": 1,
          "story_text": "Story text for this page (max 40 words).",
          "image_prompt": "Scene visual description without style keywords"
        }}
      ],
      "coloring_prompts": [
        "Scene description 1 for a coloring page",
        "Scene description 2 for a coloring page"
      ],
      "trivia": [
        {{"question": "What did the character find first?", "options": ["Option A", "Option B", "Option C"], "answer": "Option A"}},
        {{"question": "How did they solve the main obstacle?", "options": ["Option A", "Option B", "Option C"], "answer": "Option B"}}
      ],
      "word_search_words": ["FOREST", "CRYSTAL", "FRIEND", "TRAIL", "CAVE"]
    }}
    """
    
    # Candidate models to cycle through if a 503 (high demand) or 404 occurs
    candidate_models = [
        'gemini-2.5-flash',
        'gemini-2.0-flash',
        'gemini-1.5-flash',
        'gemini-2.5-pro'
    ]
    
    last_error = None
    for model_name in candidate_models:
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=f"Story Idea: {user_prompt}",
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        response_mime_type="application/json"
                    )
                )
                return json.loads(response.text)
            except Exception as e:
                last_error = e
                time.sleep(2)  # Pause before retry or switching model
                continue
                
    raise last_error

def fetch_image(prompt, style, character_desc, is_coloring=False):
    if is_coloring:
        full_prompt = f"black and white coloring book page for kids, clean bold outlines, line art, pure white background, no shading, no gray fill, {character_desc}, {prompt}"
    else:
        full_prompt = f"{style}, {character_desc}, {prompt}, high detail, 8k"
        
    encoded_prompt = urllib.parse.quote(full_prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=600&height=600&nologo=true&model=turbo"
    
    # Retry up to 3 times to mitigate read timeouts under load
    for attempt in range(3):
        try:
            res = requests.get(url, timeout=30)
            if res.status_code == 200 and len(res.content) > 1000:
                return Image.open(io.BytesIO(res.content))
        except Exception:
            time.sleep(2)
            
    return create_fallback_image("Scene rendering timed out")

def build_pdf(book_data, story_images, coloring_images, include_acts):
    pdf = ActivityBookPDF(orientation='P', unit='mm', format='A4')
    pdf.set_auto_page_break(auto=False)
    
    # 1. Cover Page
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 26)
    pdf.ln(50)
    pdf.multi_cell(0, 12, book_data.get("title", "My Storybook"), align='C')
    pdf.ln(8)
    pdf.set_font("Helvetica", "I", 14)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 10, "Story & Activity Book", ln=True, align='C')
    pdf.set_text_color(0, 0, 0)
    
    # 2. Story Pages
    for idx, page in enumerate(book_data.get("pages", [])):
        pdf.add_page()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
            story_images[idx].save(tmp.name)
            temp_path = tmp.name
        pdf.image(temp_path, x=35, y=30, w=140, h=140)
        os.remove(temp_path)
        
        pdf.set_y(185)
        pdf.set_font("Helvetica", "", 13)
        pdf.multi_cell(0, 7, page.get("story_text", ""), align='C')
        
    # 3. Coloring Pages
    if include_acts and coloring_images:
        for idx, c_img in enumerate(coloring_images):
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 18)
            pdf.cell(0, 15, f"Coloring Time! (Sheet {idx + 1})", ln=True, align='C')
            
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
                c_img.save(tmp.name)
                temp_path = tmp.name
            pdf.image(temp_path, x=25, y=35, w=160, h=160)
            os.remove(temp_path)
            
            pdf.set_y(210)
            pdf.set_font("Helvetica", "I", 11)
            pdf.cell(0, 10, "Grab your colors and bring this scene to life!", ln=True, align='C')

    # 4. Activity & Games Page
    if include_acts:
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 20)
        pdf.cell(0, 15, "Story Fun & Games", ln=True, align='C')
        pdf.ln(5)
        
        # Word Hunt Section
        pdf.set_font("Helvetica", "B", 13)
        pdf.cell(0, 8, "1. Story Word Hunt (Can you find these in the story?):", ln=True)
        pdf.set_font("Helvetica", "", 12)
        words = "  *  ".join(book_data.get("word_search_words", []))
        pdf.multi_cell(0, 8, f"{words}")
        pdf.ln(8)
        
        # Trivia Quiz Section
        pdf.set_font("Helvetica", "B", 13)
        pdf.cell(0, 8, "2. Story Quiz:", ln=True)
        pdf.set_font("Helvetica", "", 11)
        for q_idx, q in enumerate(book_data.get("trivia", [])):
            pdf.set_font("Helvetica", "B", 11)
            pdf.multi_cell(0, 6, f"Q{q_idx + 1}: {q.get('question')}")
            pdf.set_font("Helvetica", "", 10)
            for opt in q.get("options", []):
                pdf.cell(0, 5, f"   [ ] {opt}", ln=True)
            pdf.ln(3)

    return bytes(pdf.output())

# Generation Execution
if st.button("✨ Generate Story & Activities", type="primary"):
    if not gemini_key:
        st.error("Please enter your Gemini API Key in the sidebar.")
    elif not story_prompt.strip():
        st.error("Please enter a story idea.")
    else:
        with st.spinner("Writing the story, coloring outlines, and activity games..."):
            try:
                book = generate_book_and_activities(gemini_key, story_prompt, pages_count)
            except Exception as e:
                st.error(f"Error generating story structure: {e}")
                st.stop()

        st.success(f"Created: **{book.get('title', 'Untitled')}**")
        
        # Render Story Scenes
        story_images = []
        coloring_count = 2 if include_activities else 0
        total_steps = len(book.get("pages", [])) + coloring_count
        progress_bar = st.progress(0)
        current_step = 0
        
        for idx, page_item in enumerate(book.get("pages", [])):
            with st.spinner(f"Rendering story illustration {idx + 1}..."):
                img = fetch_image(page_item.get("image_prompt"), art_style, book.get("character_description"))
                story_images.append(img)
            current_step += 1
            progress_bar.progress(current_step / total_steps)

        # Render Coloring Sheets
        coloring_images = []
        if include_activities:
            for idx, c_prompt in enumerate(book.get("coloring_prompts", [])[:2]):
                with st.spinner(f"Rendering coloring sheet {idx + 1}..."):
                    c_img = fetch_image(c_prompt, art_style, book.get("character_description"), is_coloring=True)
                    coloring_images.append(c_img)
                current_step += 1
                progress_bar.progress(current_step / total_steps)

        # Tabs for Web Preview
        tab1, tab2, tab3 = st.tabs(["📖 Storybook", "🖍️ Coloring Sheets", "🎮 Activities"])
        
        with tab1:
            cols = st.columns(2)
            for idx, p in enumerate(book.get("pages", [])):
                with cols[idx % 2]:
                    st.image(story_images[idx], caption=f"Page {idx + 1}")
                    st.write(p.get("story_text"))
                    st.divider()
                    
        with tab2:
            if coloring_images:
                c_cols = st.columns(len(coloring_images))
                for c_idx, c_pic in enumerate(coloring_images):
                    with c_cols[c_idx]:
                        st.image(c_pic, caption=f"Coloring Sheet {c_idx + 1}")
            else:
                st.info("Coloring pages are disabled.")
                        
        with tab3:
            if include_activities:
                st.subheader("Quiz Questions")
                for q in book.get("trivia", []):
                    st.markdown(f"**{q.get('question')}**")
                    st.write("Options: ", " | ".join(q.get("options", [])))
                st.subheader("Word Hunt Keywords")
                st.write(", ".join(book.get("word_search_words", [])))
            else:
                st.info("Activities are disabled.")

        # PDF Compilation
        with st.spinner("Assembling complete PDF book..."):
            pdf_bytes = build_pdf(book, story_images, coloring_images, include_activities)
            
        st.download_button(
            label="📥 Download Complete Book + Activities (PDF)",
            data=pdf_bytes,
            file_name=f"{book.get('title', 'storybook').replace(' ', '_').lower()}_activities.pdf",
            mime="application/pdf"
        )
