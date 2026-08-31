import streamlit as st
from google import genai
from google.genai import types
from fpdf import FPDF
import requests
import urllib.parse
from PIL import Image, ImageDraw, ImageFont
import io
import json
import tempfile
import os
import time
import random
import string
from concurrent.futures import ThreadPoolExecutor

st.set_page_config(page_title="MagicTales — Storybook Creator", layout="wide", page_icon="✨")

st.markdown("""
<style>
    .main-header { font-family: 'Georgia', serif; font-size: 2.3rem; font-weight: 700; color: #3A2E39; }
    .sub-text { font-size: 1.1rem; color: #6E6259; margin-bottom: 20px; }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-header">✨ MagicTales Studio: Premium Illustrated Storybooks</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-text">Create full-bleed fairy tale picture books with dynamic character action, real coloring pages, and printable games.</div>', unsafe_allow_html=True)

# --- Sidebar Controls ---
with st.sidebar:
    st.header("🪄 Story Workshop")
    gemini_key = st.text_input("Gemini API Key", type="password")
    st.markdown("[Get a free Gemini API Key](https://aistudio.google.com/)")
    
    art_style = st.selectbox(
        "Visual Atmosphere",
        [
            "Lush Enchanted Fairy Tale, cinematic lighting, 8k Pixar style render, magical glow",
            "Whimsical Dreamy Watercolor & Gouache, gold leaf details, storybook masterpiece",
            "Studio Ghibli aesthetic, vibrant hand-painted anime landscape, soft sunlight",
            "Classic 3D Claymation & Miniature Diorama, tactile warmth, soft focus"
        ]
    )
    pages_count = st.slider("Story Pages", min_value=4, max_value=20, value=6)
    include_activities = st.checkbox("Include Coloring & Games Suite", value=True)

story_prompt = st.text_area(
    "What magical adventure shall we tell?",
    placeholder="e.g., A tiny hedgehog named Bramble who wears an oversized acorn helmet and wants to catch a falling star to light up the dark Whispering Hollow."
)

# --- PDF Builder Engine ---
class FairyTalePDF(FPDF):
    def footer(self):
        # Decorative page numbering on pages after cover
        if self.page_no() > 1:
            self.set_y(-12)
            self.set_font("Helvetica", "I", 9)
            self.set_text_color(160, 150, 140)
            self.cell(0, 10, f"~ {self.page_no()} ~", 0, 0, "C")

def create_fallback_image(text="Magical Scene Loading..."):
    img = Image.new('RGB', (800, 1000), color=(240, 235, 225))
    draw = ImageDraw.Draw(img)
    draw.rectangle([15, 15, 785, 985], outline=(200, 180, 160), width=4)
    draw.text((260, 480), text, fill=(130, 110, 95))
    return img

def generate_full_tale(api_key, user_prompt, num_pages):
    client = genai.Client(api_key=api_key)
    
    system_instruction = f"""
    You are an award-winning children's author and visual storyboard artist for Disney & Pixar.
    Write a vibrant, heartwarming, magical fairy tale based on the user's idea in EXACTLY {num_pages} pages.
    
    CRITICAL STORYBOARDING RULES:
    1. PROTAGONIST DESIGN: Give the character a clear, distinct visual trait (e.g., 'a fluffy caramel-colored red panda wearing a turquoise knitted poncho and carrying a wooden star-lantern').
    2. DYNAMIC ACTION IN EVERY SCENE: The character MUST NEVER just stand there. They must be actively running, climbing, reaching, gasping, gliding, laughing, or interacting with the scene.
    3. SCENARIO PROGRESSION: Make the environment evolve across every page (e.g., misty glen -> starry canopy -> crystal cavern -> moonlit lake).
    4. COLORING PROMPTS: Generate 2 scene descriptions with strong outlines, fun objects, and clear subjects for kids to color.
    5. COMPREHENSION TRIVIA: 2 fun multiple-choice questions about key events.
    6. WORD SEARCH: 6 distinct uppercase story keywords (4-7 letters each).
    
    Return a STRICT JSON object:
    {{
      "title": "Magical Story Title",
      "tagline": "A Whimsical Tale of Wonder and Courage",
      "character_description": "Detailed persistent visual description of protagonist",
      "pages": [
        {{
          "page_number": 1,
          "story_text": "Story text for this page (30-45 words). Written with rhythm, emotion, and kid-friendly wonder.",
          "action_image_prompt": "Specific visual action showing the protagonist in motion within the scene"
        }}
      ],
      "coloring_prompts": [
        "Line art scene 1 of character performing a fun action",
        "Line art scene 2 with cute secondary characters and flora"
      ],
      "trivia": [
        {{"question": "Fun story question?", "options": ["Choice A", "Choice B", "Choice C"], "answer": "Choice A"}},
        {{"question": "Second story question?", "options": ["Choice A", "Choice B", "Choice C"], "answer": "Choice B"}}
      ],
      "word_search_words": ["STAR", "GLOW", "MAGIC", "BRAVE", "FOREST", "RIVER"]
    }}
    """
    
    candidate_models = ['gemini-2.5-flash', 'gemini-3.6-flash', 'gemini-3.1-pro-preview']
    last_error = None
    for model_name in candidate_models:
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=f"Story Concept: {user_prompt}",
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        response_mime_type="application/json"
                    )
                )
                return json.loads(response.text)
            except Exception as e:
                last_error = e
                time.sleep(2)
                continue
                
    raise last_error

def fetch_image(prompt, style, character_desc, is_coloring=False):
    if is_coloring:
        full_prompt = (
            f"Children coloring book page, crisp bold black outlines, pure white background, "
            f"zero shading, zero gradients, zero grayscale, clean vector lineart, simple composition for kids: {character_desc}, {prompt}"
        )
    else:
        full_prompt = (
            f"{style}, {character_desc}, dynamic composition, {prompt}, "
            f"highly detailed, vibrant whimsical palette, cinematic depth of field, 8k resolution"
        )
        
    encoded_prompt = urllib.parse.quote(full_prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=800&height=1000&nologo=true&model=turbo"
    
    for _ in range(3):
        try:
            res = requests.get(url, timeout=35)
            if res.status_code == 200 and len(res.content) > 1500:
                return Image.open(io.BytesIO(res.content))
        except Exception:
            time.sleep(1.5)
            
    return create_fallback_image("Story Scene" if not is_coloring else "Coloring Sheet")

def generate_word_search_grid(words, size=9):
    """Generates an actual letter grid with hidden words placed horizontally or vertically."""
    grid = [[' ' for _ in range(size)] for _ in range(size)]
    placed_words = []
    
    for word in words:
        clean_word = word.upper().replace(" ", "")[:size]
        placed = False
        for _ in range(50):  # 50 placement attempts
            direction = random.choice(['H', 'V'])
            if direction == 'H':
                row = random.randint(0, size - 1)
                col = random.randint(0, size - len(clean_word))
                if all(grid[row][col + i] in (' ', clean_word[i]) for i in range(len(clean_word))):
                    for i, ch in enumerate(clean_word):
                        grid[row][col + i] = ch
                    placed = True
                    placed_words.append(clean_word)
                    break
            else:
                row = random.randint(0, size - len(clean_word))
                col = random.randint(0, size - 1)
                if all(grid[row + i][col] in (' ', clean_word[i]) for i in range(len(clean_word))):
                    for i, ch in enumerate(clean_word):
                        grid[row + i][col] = ch
                    placed = True
                    placed_words.append(clean_word)
                    break
                    
    # Fill remaining empty spots with random uppercase letters
    for r in range(size):
        for c in range(size):
            if grid[r][c] == ' ':
                grid[r][c] = random.choice(string.ascii_uppercase)
                
    return grid, placed_words

def build_pdf(book_data, story_images, coloring_images, include_acts):
    pdf = FairyTalePDF(orientation='P', unit='mm', format='A4')
    pdf.set_auto_page_break(auto=False)
    
    # ---------------- 1. COVER PAGE (FULL BLEED HERO) ----------------
    pdf.add_page()
    if story_images:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
            story_images[0].save(tmp.name)
            cover_img_path = tmp.name
        # Full page background artwork
        pdf.image(cover_img_path, x=0, y=0, w=210, h=297)
        os.remove(cover_img_path)
    
    # Elegant Title Ribbon Box on Cover
    pdf.set_fill_color(255, 252, 245)
    pdf.set_draw_color(212, 175, 55)  # Gold border
    pdf.set_line_width(1.2)
    pdf.rect(x=15, y=30, w=180, h=52, style='FD')
    
    pdf.set_xy(18, 38)
    pdf.set_font("Helvetica", "B", 24)
    pdf.set_text_color(58, 46, 57)
    pdf.multi_cell(174, 10, book_data.get("title", "A Magical Adventure"), align='C')
    
    pdf.set_xy(18, 62)
    pdf.set_font("Helvetica", "I", 12)
    pdf.set_text_color(120, 105, 95)
    pdf.cell(174, 8, book_data.get("tagline", "A Tale of Magic and Wonder"), align='C')

    # ---------------- 2. STORY PAGES (FULL-BLEED ART + PARCHMENT TEXT) ----------------
    for idx, page in enumerate(book_data.get("pages", [])):
        pdf.add_page()
        img = story_images[idx]
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
            img.save(tmp.name)
            page_img_path = tmp.name
        
        # Illustration covers the upper 72% of the page
        pdf.image(page_img_path, x=0, y=0, w=210, h=215)
        os.remove(page_img_path)
        
        # Bottom Parchment Story Card (Zero dead white space)
        pdf.set_fill_color(255, 253, 248)
        pdf.set_draw_color(225, 215, 200)
        pdf.set_line_width(0.8)
        pdf.rect(x=10, y=200, w=190, h=82, style='FD')
        
        # Subtle decorative inner border
        pdf.set_draw_color(240, 230, 215)
        pdf.rect(x=13, y=203, w=184, h=76, style='D')
        
        # Story narrative text
        pdf.set_xy(18, 212)
        pdf.set_font("Helvetica", "", 13)
        pdf.set_text_color(45, 38, 42)
        pdf.multi_cell(174, 7.5, page.get("story_text", ""), align='C')

    # ---------------- 3. COLORING STUDIO ----------------
    if include_acts and coloring_images:
        for idx, c_img in enumerate(coloring_images):
            pdf.add_page()
            # Warm paper background
            pdf.set_fill_color(253, 252, 250)
            pdf.rect(0, 0, 210, 297, style='F')
            
            # Header
            pdf.set_xy(10, 16)
            pdf.set_font("Helvetica", "B", 20)
            pdf.set_text_color(70, 50, 65)
            pdf.cell(190, 10, f"🎨 Storybook Coloring Studio — Sheet {idx + 1}", align='C', ln=True)
            
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
                c_img.save(tmp.name)
                color_img_path = tmp.name
            
            # Large, crisp coloring illustration frame
            pdf.set_draw_color(180, 170, 160)
            pdf.set_line_width(1.0)
            pdf.rect(15, 32, 180, 220, style='D')
            pdf.image(color_img_path, x=16, y=33, w=178, h=218)
            os.remove(color_img_path)
            
            pdf.set_xy(15, 260)
            pdf.set_font("Helvetica", "I", 11)
            pdf.set_text_color(120, 110, 100)
            pdf.cell(180, 8, "Use your favorite crayons or colored pencils to bring this moment to life!", align='C')

    # ---------------- 4. INTERACTIVE GAMES SUITE ----------------
    if include_acts:
        pdf.add_page()
        # Soft parchment backdrop
        pdf.set_fill_color(252, 250, 245)
        pdf.rect(0, 0, 210, 297, style='F')
        
        pdf.set_xy(10, 16)
        pdf.set_font("Helvetica", "B", 22)
        pdf.set_text_color(60, 45, 55)
        pdf.cell(190, 10, "✨ Fairy Tale Games & Quizzes", align='C', ln=True)
        pdf.ln(4)
        
        # Word Hunt Section with REAL Letter Grid
        pdf.set_font("Helvetica", "B", 14)
        pdf.set_text_color(80, 60, 70)
        pdf.set_x(15)
        pdf.cell(180, 8, "1. Magic Word Hunt (Can you find all the hidden words?)", ln=True)
        
        words_list = book_data.get("word_search_words", ["STAR", "GLOW", "MAGIC", "BRAVE"])
        grid, placed_words = generate_word_search_grid(words_list, size=8)
        
        # Draw Word Search Grid
        start_x = 22
        start_y = 44
        cell_size = 8
        pdf.set_font("Courier", "B", 13)
        pdf.set_draw_color(200, 190, 175)
        
        for r_idx, row in enumerate(grid):
            for c_idx, letter in enumerate(row):
                x = start_x + (c_idx * cell_size)
                y = start_y + (r_idx * cell_size)
                pdf.set_fill_color(255, 255, 255)
                pdf.rect(x, y, cell_size, cell_size, style='FD')
                pdf.set_xy(x, y + 1.2)
                pdf.cell(cell_size, cell_size - 1.2, letter, align='C')
                
        # Word Bank next to the grid
        pdf.set_xy(100, 46)
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(100, 80, 90)
        pdf.cell(90, 6, "FIND THESE WORDS:", ln=True)
        pdf.set_font("Helvetica", "", 11)
        for w in placed_words:
            pdf.set_x(102)
            pdf.cell(90, 5.5, f"[  ]  {w}", ln=True)
            
        pdf.ln(18)
        
        # Story Quiz Section
        pdf.set_font("Helvetica", "B", 14)
        pdf.set_text_color(80, 60, 70)
        pdf.set_x(15)
        pdf.cell(180, 8, "2. Story Detective Quiz", ln=True)
        
        for q_idx, q in enumerate(book_data.get("trivia", [])):
            pdf.set_x(18)
            pdf.set_font("Helvetica", "B", 11)
            pdf.set_text_color(50, 40, 45)
            pdf.multi_cell(174, 6, f"Q{q_idx + 1}: {q.get('question')}")
            pdf.set_font("Helvetica", "", 10.5)
            for opt in q.get("options", []):
                pdf.set_x(24)
                pdf.cell(168, 5.2, f"(   )  {opt}", ln=True)
            pdf.ln(3)

    return bytes(pdf.output())

# --- Generation Execution Flow ---
if st.button("🌟 Generate Full Illustrated Book", type="primary"):
    if not gemini_key:
        st.error("Please add your Gemini API Key in the sidebar.")
    elif not story_prompt.strip():
        st.error("Please describe your story idea.")
    else:
        with st.spinner(f"Writing {pages_count}-page enchanted tale with dynamic scene actions..."):
            try:
                book = generate_full_tale(gemini_key, story_prompt, pages_count)
            except Exception as e:
                st.error(f"Error creating story arc: {e}")
                st.stop()

        st.success(f"✨ Created: **{book.get('title')}** — *{book.get('tagline')}*")
        
        # Character & Scene Visuals in Parallel
        pages_list = book.get("pages", [])
        char_desc = book.get("character_description", "")
        
        with st.spinner(f"Painting {len(pages_list)} rich fairytale illustrations..."):
            with ThreadPoolExecutor(max_workers=4) as executor:
                story_images = list(executor.map(
                    lambda p: fetch_image(p.get("action_image_prompt"), art_style, char_desc),
                    pages_list
                ))

        # Real Line Art Coloring Sheets in Parallel
        coloring_images = []
        if include_activities:
            c_prompts = book.get("coloring_prompts", [])[:2]
            with st.spinner("Generating crisp line-art coloring pages..."):
                with ThreadPoolExecutor(max_workers=2) as executor:
                    coloring_images = list(executor.map(
                        lambda cp: fetch_image(cp, art_style, char_desc, is_coloring=True),
                        c_prompts
                    ))

        # Live Web Experience
        tab1, tab2, tab3 = st.tabs(["📖 Story Showcase", "🖍️ Coloring Studio", "🧩 Games & Quizzes"])
        
        with tab1:
            for idx, p in enumerate(book.get("pages", [])):
                col1, col2 = st.columns([3, 2])
                with col1:
                    st.image(story_images[idx], use_container_width=True)
                with col2:
                    st.markdown(f"### Page {idx + 1}")
                    st.markdown(f"*{p.get('story_text')}*")
                    st.caption(f"**Action:** {p.get('action_image_prompt')}")
                st.divider()
                
        with tab2:
            if coloring_images:
                c_cols = st.columns(len(coloring_images))
                for c_idx, c_pic in enumerate(coloring_images):
                    with c_cols[c_idx]:
                        st.image(c_pic, caption=f"Coloring Sheet {c_idx + 1}", use_container_width=True)
            else:
                st.info("Coloring sheets disabled.")
                
        with tab3:
            if include_activities:
                col_a, col_b = st.columns(2)
                with col_a:
                    st.subheader("🧩 Word Hunt Keywords")
                    st.write(", ".join(book.get("word_search_words", [])))
                with col_b:
                    st.subheader("💡 Story Quiz")
                    for q in book.get("trivia", []):
                        st.write(f"**{q.get('question')}**")
                        st.write("Options:", ", ".join(q.get("options", [])))
            else:
                st.info("Activities disabled.")

        # PDF Compilation
        with st.spinner("Assembling print-ready A4 picture book..."):
            pdf_bytes = build_pdf(book, story_images, coloring_images, include_activities)
            
        st.download_button(
            label="📥 Download Complete Illustrated PDF Book",
            data=pdf_bytes,
            file_name=f"{book.get('title', 'fairytale').replace(' ', '_').lower()}.pdf",
            mime="application/pdf"
        )
