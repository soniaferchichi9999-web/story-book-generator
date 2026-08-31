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
import random
import string
import re
import asyncio
import edge_tts
from concurrent.futures import ThreadPoolExecutor

st.set_page_config(page_title="MagicTales Deluxe — Picture Book Studio", layout="wide", page_icon="📚")

st.markdown("""
<style>
    .main-title { font-family: 'Georgia', serif; font-size: 2.2rem; font-weight: 700; color: #2C221E; }
    .sub-title { font-size: 1.05rem; color: #6E5D53; margin-bottom: 25px; }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title">📚 MagicTales Deluxe: Publishing-Grade Storybooks</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">Landscape two-page spreads, neural voice narration, seed-locked consistency, and activity suites.</div>', unsafe_allow_html=True)

# --- Sidebar Controls ---
with st.sidebar:
    st.header("🪄 Production Settings")
    gemini_key = st.text_input("Gemini API Key", type="password")
    st.markdown("[Get a free Gemini API Key](https://aistudio.google.com/)")
    
    art_style = st.selectbox(
        "Illustration Aesthetic",
        [
            "Enchanted fairy tale landscape, cinematic lighting, 8k Pixar 3D render, golden hour atmosphere",
            "Whimsical gouache & dreamy watercolor illustration, storybook masterpiece, rich textures",
            "Studio Ghibli aesthetic, vibrant lush background, soft volumetric sunlight",
            "Classic vintage bedtime storybook art, tactile pastel textures"
        ]
    )
    pages_count = st.slider("Story Pages (Spreads)", min_value=4, max_value=20, value=6)
    enable_audio = st.checkbox("Generate Neural Voice Narration", value=True)
    include_activities = st.checkbox("Include Coloring & Games Suite", value=True)

story_prompt = st.text_area(
    "What adventure shall we create?",
    placeholder="e.g., A brave little sea-otter named Barnaby who wears a seaweed vest and carries a glowing pearl lantern across the coral canyons."
)

def clean_pdf_text(text):
    """Sanitizes text for FPDF by stripping emojis and converting fancy Unicode punctuation to Latin-1."""
    if not text:
        return ""
    # Map common smart/fancy characters to standard ASCII
    replacements = {
        '—': '-', '–': '-', '―': '-',
        '“': '"', '”': '"', '‘': "'", '’': "'",
        '…': '...', '•': '*', '·': '*',
        '«': '"', '»': '"'
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    # Remove emoji and other characters outside Latin-1
    return text.encode('latin-1', 'ignore').decode('latin-1')

# --- PDF Builder Engine (Landscape 2-Page Spreads) ---
class LandscapeStorybookPDF(FPDF):
    def footer(self):
        if self.page_no() > 1:
            self.set_y(-12)
            self.set_font("Helvetica", "I", 9)
            self.set_text_color(160, 150, 140)
            self.cell(0, 10, f"- {self.page_no()} -", 0, 0, "C")

def create_fallback_image(text="Magical Scene Loading..."):
    img = Image.new('RGB', (1000, 750), color=(245, 240, 230))
    draw = ImageDraw.Draw(img)
    draw.rectangle([15, 15, 985, 735], outline=(210, 190, 170), width=4)
    draw.text((380, 360), text, fill=(140, 120, 100))
    return img

async def generate_narration_audio(text, output_path):
    """Generates expressive neural bedtime story narration using Edge-TTS."""
    communicate = edge_tts.Communicate(text, voice="en-US-AnaNeural", rate="-4%", pitch="+2Hz")
    await communicate.save(output_path)

def generate_full_tale(api_key, user_prompt, num_pages):
    client = genai.Client(api_key=api_key)
    
    system_instruction = f"""
    You are an award-winning children's author and visual storyboard director.
    Write an engaging, heartwarming story based on the prompt paced across EXACTLY {num_pages} spreads.
    
    PUBLISHING RULES:
    1. PROTAGONIST DESIGN: Give the hero distinctive, persistent visual markers (exact clothing, accessories, colors, and species).
    2. SENSORY PACING & ONOMATOPOEIA: Use rich sensory cues and playful sound words (e.g., 'Whoosh!', 'Plip-plop!').
    3. DYNAMIC SCENE ACTIONS: The character must be actively interacting with their environment in every scene.
    4. INTERACTIVE LOOK-AND-FIND: Provide a 'seek_and_find' prompt for each spread (e.g., 'Can you spot the 3 glowing blue shells?').
    5. COLORING & ACTIVITIES: 2 line-art coloring prompts, 2 comprehension questions, and 6 uppercase story words.
    
    Return a STRICT JSON object:
    {{
      "title": "Book Title",
      "tagline": "A Heartwarming Tale of Wonder",
      "character_description": "Detailed persistent visual traits of protagonist",
      "pages": [
        {{
          "spread_number": 1,
          "story_text": "Engaging narrative paragraph for this spread (40-60 words).",
          "seek_and_find": "Observation prompt for kids reading along.",
          "action_image_prompt": "Dynamic visual scene showing protagonist in motion within the environment"
        }}
      ],
      "coloring_prompts": [
        "Crisp line-art scene of hero performing an action",
        "Crisp line-art scene with cute secondary characters"
      ],
      "trivia": [
        {{"question": "Question about the story?", "options": ["Choice A", "Choice B", "Choice C"], "answer": "Choice A"}},
        {{"question": "Second question about the story?", "options": ["Choice A", "Choice B", "Choice C"], "answer": "Choice B"}}
      ],
      "word_search_words": ["MAGIC", "BRAVE", "GLOW", "PEARL", "RIVER", "TRAIL"]
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

def fetch_image(prompt, style, character_desc, seed, is_coloring=False):
    if is_coloring:
        full_prompt = (
            f"Children coloring book page, crisp bold black outlines, pure white background, "
            f"zero shading, zero gradients, clean vector lineart, simple composition: {character_desc}, {prompt}"
        )
    else:
        full_prompt = (
            f"{style}, {character_desc}, {prompt}, cinematic wide-angle composition, "
            f"storybook illustration masterpiece, soft volumetric lighting, 8k"
        )
        
    encoded_prompt = urllib.parse.quote(full_prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1000&height=750&seed={seed}&nologo=true&model=turbo"
    
    for _ in range(3):
        try:
            res = requests.get(url, timeout=35)
            if res.status_code == 200 and len(res.content) > 1500:
                return Image.open(io.BytesIO(res.content))
        except Exception:
            time.sleep(1.5)
            
    return create_fallback_image("Story Scene" if not is_coloring else "Coloring Sheet")

def generate_word_search_grid(words, size=8):
    grid = [[' ' for _ in range(size)] for _ in range(size)]
    placed_words = []
    
    for word in words:
        clean_word = clean_pdf_text(word).upper().replace(" ", "")[:size]
        placed = False
        for _ in range(50):
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
                    
    for r in range(size):
        for c in range(size):
            if grid[r][c] == ' ':
                grid[r][c] = random.choice(string.ascii_uppercase)
                
    return grid, placed_words

def build_pdf(book_data, story_images, coloring_images, include_acts):
    pdf = LandscapeStorybookPDF(orientation='L', unit='mm', format='A4')  # 297mm x 210mm
    pdf.set_auto_page_break(auto=False)
    
    title = clean_pdf_text(book_data.get("title", "A Magical Journey"))
    tagline = clean_pdf_text(book_data.get("tagline", "A Heartwarming Picture Book"))
    
    # --- 1. COVER SPREAD ---
    pdf.add_page()
    if story_images:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
            story_images[0].save(tmp.name)
            cover_img = tmp.name
        pdf.image(cover_img, x=0, y=0, w=297, h=210)
        os.remove(cover_img)
        
    # Title Ribbon
    pdf.set_fill_color(255, 253, 248)
    pdf.set_draw_color(212, 175, 55)
    pdf.set_line_width(1.2)
    pdf.rect(x=35, y=35, w=227, h=55, style='FD')
    
    pdf.set_xy(40, 43)
    pdf.set_font("Helvetica", "B", 26)
    pdf.set_text_color(50, 40, 48)
    pdf.multi_cell(217, 11, title, align='C')
    
    pdf.set_xy(40, 72)
    pdf.set_font("Helvetica", "I", 13)
    pdf.set_text_color(120, 105, 95)
    pdf.cell(217, 8, tagline, align='C')

    # --- 2. STORY SPREADS (Left: Art | Right: Text) ---
    for idx, page in enumerate(book_data.get("pages", [])):
        pdf.add_page()
        
        # Left Half: Full-Bleed Artwork
        img = story_images[idx]
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
            img.save(tmp.name)
            page_img = tmp.name
        pdf.image(page_img, x=0, y=0, w=155, h=210)
        os.remove(page_img)
        
        # Right Half: Warm Parchment Page
        pdf.set_fill_color(254, 252, 247)
        pdf.rect(155, 0, 142, 210, style='F')
        
        # Inner Border
        pdf.set_draw_color(230, 220, 205)
        pdf.set_line_width(0.8)
        pdf.rect(165, 12, 122, 186, style='D')
        
        # Chapter Indicator
        pdf.set_xy(170, 24)
        pdf.set_font("Helvetica", "I", 11)
        pdf.set_text_color(150, 130, 120)
        pdf.cell(112, 6, f"~ Chapter {idx + 1} ~", align='C', ln=True)
        pdf.ln(6)
        
        # Main Narrative Text
        story_txt = clean_pdf_text(page.get("story_text", ""))
        pdf.set_x(172)
        pdf.set_font("Helvetica", "", 13)
        pdf.set_text_color(45, 38, 42)
        pdf.multi_cell(108, 8, story_txt, align='L')
        
        # Seek & Find Card
        seek_txt = clean_pdf_text(page.get("seek_and_find", ""))
        if seek_txt:
            pdf.set_xy(170, 148)
            pdf.set_fill_color(246, 241, 233)
            pdf.set_draw_color(215, 200, 180)
            pdf.rect(170, 148, 112, 34, style='FD')
            
            pdf.set_xy(174, 152)
            pdf.set_font("Helvetica", "B", 10.5)
            pdf.set_text_color(110, 85, 70)
            pdf.cell(104, 5, "Seek & Find Quest:", ln=True)
            
            pdf.set_xy(174, 159)
            pdf.set_font("Helvetica", "I", 10)
            pdf.set_text_color(70, 60, 55)
            pdf.multi_cell(104, 5, seek_txt)

    # --- 3. COLORING SHEETS ---
    if include_acts and coloring_images:
        for idx, c_img in enumerate(coloring_images):
            pdf.add_page()
            pdf.set_fill_color(255, 255, 255)
            pdf.rect(0, 0, 297, 210, style='F')
            
            pdf.set_xy(15, 12)
            pdf.set_font("Helvetica", "B", 18)
            pdf.set_text_color(60, 45, 55)
            pdf.cell(267, 8, f"Storybook Coloring Studio - Sheet {idx + 1}", align='C', ln=True)
            
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
                c_img.save(tmp.name)
                c_path = tmp.name
            pdf.image(c_path, x=38, y=26, w=220, h=165)
            os.remove(c_path)

    # --- 4. ACTIVITIES & WORD HUNT ---
    if include_acts:
        pdf.add_page()
        pdf.set_fill_color(252, 250, 245)
        pdf.rect(0, 0, 297, 210, style='F')
        
        pdf.set_xy(15, 12)
        pdf.set_font("Helvetica", "B", 20)
        pdf.set_text_color(60, 45, 55)
        pdf.cell(267, 8, "Storytime Activities & Word Search", align='C', ln=True)
        pdf.ln(6)
        
        # Left Half: Word Search Grid
        pdf.set_xy(20, 30)
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(80, 60, 70)
        pdf.cell(120, 6, "1. Magic Word Hunt", ln=True)
        
        words_list = book_data.get("word_search_words", ["MAGIC", "BRAVE", "GLOW", "STAR"])
        grid, placed_words = generate_word_search_grid(words_list, size=8)
        
        start_x = 22
        start_y = 42
        cell_size = 9
        pdf.set_font("Courier", "B", 13)
        pdf.set_draw_color(200, 190, 175)
        
        for r_idx, row in enumerate(grid):
            for c_idx, letter in enumerate(row):
                x = start_x + (c_idx * cell_size)
                y = start_y + (r_idx * cell_size)
                pdf.set_fill_color(255, 255, 255)
                pdf.rect(x, y, cell_size, cell_size, style='FD')
                pdf.set_xy(x, y + 1.5)
                pdf.cell(cell_size, cell_size - 1.5, letter, align='C')
                
        # Word Bank
        pdf.set_xy(102, 42)
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(100, 80, 90)
        pdf.cell(45, 6, "WORDS TO FIND:", ln=True)
        pdf.set_font("Helvetica", "", 10.5)
        for w in placed_words:
            pdf.set_x(104)
            pdf.cell(45, 6, f"[  ]  {w}", ln=True)
            
        # Right Half: Quiz
        pdf.set_xy(160, 30)
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(80, 60, 70)
        pdf.cell(120, 6, "2. Reading Comprehension Quiz", ln=True)
        
        pdf.set_xy(160, 42)
        for q_idx, q in enumerate(book_data.get("trivia", [])):
            q_text = clean_pdf_text(q.get('question', ''))
            pdf.set_x(162)
            pdf.set_font("Helvetica", "B", 11)
            pdf.set_text_color(50, 40, 45)
            pdf.multi_cell(115, 6, f"Q{q_idx + 1}: {q_text}")
            pdf.set_font("Helvetica", "", 10.5)
            for opt in q.get("options", []):
                opt_text = clean_pdf_text(opt)
                pdf.set_x(168)
                pdf.cell(110, 5.5, f"(   )  {opt_text}", ln=True)
            pdf.ln(3)

    return bytes(pdf.output())

# --- Execution Workflow ---
if st.button("🌟 Generate Full Picture Book Experience", type="primary"):
    if not gemini_key:
        st.error("Please enter your Gemini API Key in the sidebar.")
    elif not story_prompt.strip():
        st.error("Please describe your story idea.")
    else:
        with st.spinner(f"Writing {pages_count}-spread story with seek-and-find quests..."):
            try:
                book = generate_full_tale(gemini_key, story_prompt, pages_count)
            except Exception as e:
                st.error(f"Error creating story arc: {e}")
                st.stop()

        st.success(f"✨ Created: **{book.get('title')}** — *{book.get('tagline')}*")
        
        # 1. Lock a random seed across all story illustrations for character continuity
        shared_seed = random.randint(100000, 999999)
        pages_list = book.get("pages", [])
        char_desc = book.get("character_description", "")
        
        with st.spinner(f"Painting {len(pages_list)} landscape illustrations (Seed: {shared_seed})..."):
            with ThreadPoolExecutor(max_workers=4) as executor:
                story_images = list(executor.map(
                    lambda p: fetch_image(p.get("action_image_prompt"), art_style, char_desc, shared_seed),
                    pages_list
                ))

        # 2. Render Coloring Sheets
        coloring_images = []
        if include_activities:
            c_prompts = book.get("coloring_prompts", [])[:2]
            with st.spinner("Generating crisp line-art coloring pages..."):
                with ThreadPoolExecutor(max_workers=2) as executor:
                    coloring_images = list(executor.map(
                        lambda cp: fetch_image(cp, art_style, char_desc, shared_seed, is_coloring=True),
                        c_prompts
                    ))

        # 3. Generate Neural Voice Audio Files (Async Edge-TTS)
        audio_files = []
        if enable_audio:
            with st.spinner("Generating neural bedtime story narration..."):
                for idx, p in enumerate(pages_list):
                    tmp_audio = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
                    asyncio.run(generate_narration_audio(p.get("story_text"), tmp_audio.name))
                    audio_files.append(tmp_audio.name)

        # 4. Interactive Live Preview
        tab1, tab2, tab3 = st.tabs(["📖 Storybook Experience", "🖍️ Coloring Studio", "🧩 Games & Quizzes"])
        
        with tab1:
            for idx, p in enumerate(pages_list):
                st.markdown(f"#### Spread {idx + 1}")
                col_left, col_right = st.columns([1.2, 1])
                with col_left:
                    st.image(story_images[idx], use_container_width=True)
                with col_right:
                    st.markdown(f"### Chapter {idx + 1}")
                    st.write(p.get("story_text"))
                    st.info(f"🔍 **Seek & Find:** {p.get('seek_and_find')}")
                    if enable_audio and idx < len(audio_files):
                        st.audio(audio_files[idx], format="audio/mp3")
                st.divider()
                
        with tab2:
            if coloring_images:
                c_cols = st.columns(len(coloring_images))
                for c_idx, c_pic in enumerate(coloring_images):
                    with c_cols[c_idx]:
                        st.image(c_pic, caption=f"Coloring Sheet {c_idx + 1}", use_container_width=True)
                        
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

        # 5. Compile PDF
        with st.spinner("Compiling landscape 2-page spread PDF..."):
            pdf_bytes = build_pdf(book, story_images, coloring_images, include_activities)
            
        st.download_button(
            label="📥 Download Landscape Deluxe PDF Book",
            data=pdf_bytes,
            file_name=f"{clean_pdf_text(book.get('title', 'fairytale')).replace(' ', '_').lower()}_deluxe.pdf",
            mime="application/pdf"
        )
