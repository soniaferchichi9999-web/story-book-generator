import streamlit as st
from google import genai
from google.genai import types
from fpdf import FPDF
from PIL import Image, ImageDraw, ImageFont
import io
import json
import tempfile
import os
import time
import random
import string
import asyncio
import edge_tts

st.set_page_config(page_title="MagicTales Studio — Pro Picture Books", layout="wide", page_icon="✨")

st.markdown("""
<style>
    .main-title { font-family: 'Georgia', serif; font-size: 2.3rem; font-weight: 700; color: #2C221E; }
    .sub-title { font-size: 1.05rem; color: #6E5D53; margin-bottom: 25px; }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title">✨ MagicTales Studio: Premium Illustrated Storybooks</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">Powered by Imagen 3 & Gemini — High-detail 3D Pixar renders with composited parchment scrolls.</div>', unsafe_allow_html=True)

# --- Sidebar Controls ---
with st.sidebar:
    st.header("⚙️ Studio Settings")
    gemini_key = st.text_input("Gemini API Key", type="password")
    st.markdown("[Get a Gemini API Key](https://aistudio.google.com/)")
    
    age_group = st.selectbox("Target Age Group", ["Ages 3-5", "Ages 5-8", "Ages 8-12"], index=1)
    pages_count = st.slider("Story Pages", min_value=3, max_value=8, value=4)
    enable_audio = st.checkbox("Generate Bedtime Voice Narration", value=True)
    include_activities = st.checkbox("Include Coloring & Games Pages", value=True)

story_prompt = st.text_area(
    "What magical story shall we create?",
    value="Ziggy Zappop the curious turquoise-blue bunny creature with big fluffy ears wearing a leather backpack and sneakers. Ziggy sits on his wooden treehouse porch reading a glowing magical map with a little sprout-buddy, looking over the Whispering Forest full of smiley mushrooms and magical glowing lights."
)

def clean_pdf_text(text):
    if not text:
        return ""
    replacements = {
        '—': '-', '–': '-', '―': '-',
        '“': '"', '”': '"', '‘': "'", '’': "'",
        '…': '...', '•': '*', '·': '*'
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text.encode('latin-1', 'ignore').decode('latin-1')

# --- Pillow Parchment & Scroll Compositing Engine ---
def draw_parchment_scroll(draw, x, y, w, h, text):
    """Draws an antique rolled parchment scroll with curled ends and crisp typography."""
    draw.rectangle([x + 4, y + 5, x + w + 4, y + h + 5], fill=(20, 15, 10, 120))
    draw.rectangle([x, y, x + w, y + h], fill=(250, 241, 222), outline=(130, 90, 50), width=3)
    
    curl_w = 10
    draw.rectangle([x - curl_w, y - 3, x, y + h + 3], fill=(225, 210, 180), outline=(110, 75, 40), width=2)
    draw.line([x - curl_w, y + h // 2, x, y + h // 2], fill=(160, 130, 95), width=2)
    
    draw.rectangle([x + w, y - 3, x + w + curl_w, y + h + 3], fill=(225, 210, 180), outline=(110, 75, 40), width=2)
    draw.line([x + w, y + h // 2, x + w + curl_w, y + h // 2], fill=(160, 130, 95), width=2)
    
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 28)
    except Exception:
        font = ImageFont.load_default()
        
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    text_x = x + (w - tw) // 2
    text_y = y + (h - th) // 2 - 2
    
    draw.text((text_x + 1, text_y + 1), text, fill=(210, 195, 170), font=font)
    draw.text((text_x, text_y), text, fill=(35, 25, 20), font=font)

def apply_storybook_frame(image, snippets):
    """Applies vintage border and composited parchment scrolls over full-bleed artwork."""
    img = image.convert("RGBA").resize((1024, 1024))
    overlay = Image.new("RGBA", img.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)
    W, H = img.size
    
    margin = 25
    draw.rectangle([margin, margin, W - margin, H - margin], outline=(190, 145, 75, 255), width=5)
    draw.rectangle([margin + 7, margin + 7, W - margin - 7, H - margin - 7], outline=(120, 85, 40, 255), width=2)
    
    cs = 32
    for cx, cy in [(margin, margin), (W - margin, margin), (margin, H - margin), (W - margin, H - margin)]:
        draw.arc([cx - cs, cy - cs, cx + cs, cy + cs], 0, 360, fill=(212, 175, 55, 255), width=4)
        
    positions = [
        (55, 55, 420, 85),
        (W - 460, H // 2 - 45, 400, 85),
        (W - 470, H - 150, 410, 85)
    ]
    
    for i, snip in enumerate(snippets[:3]):
        if snip.strip():
            px, py, pw, ph = positions[i]
            draw_parchment_scroll(draw, px, py, pw, ph, snip.strip())
            
    final_img = Image.alpha_composite(img, overlay)
    return final_img.convert("RGB")

# --- Square PDF Engine ---
class SquareStorybookPDF(FPDF):
    def footer(self):
        pass

async def generate_narration_audio(text, output_path):
    communicate = edge_tts.Communicate(text, voice="en-US-AnaNeural", rate="-4%", pitch="+2Hz")
    await communicate.save(output_path)

def generate_storybook_data(api_key, user_prompt, num_pages, age_str):
    client = genai.Client(api_key=api_key)
    
    system_instruction = f"""
    You are an award-winning children's author and visual director for high-end Disney/Pixar storybooks.
    Create a magical story based on the prompt in EXACTLY {num_pages} pages for {age_str}.
    
    CRITICAL TEXT RULES:
    Break every page into 2 or 3 short, whimsical story snippets (5 to 8 words each) that will be placed inside parchment scrolls on the page.
    Example:
    - Snippet 1: "Ziggy lived beside the Whispering Forest."
    - Snippet 2: "Every day was an adventure."
    - Snippet 3: "Even when he was not looking for one."
    
    Return STRICT JSON:
    {{
      "title": "ZIGGY ZAPPOP and the Mystery Backpack",
      "subtitle": "Book 0 | Introduction Story {age_str}",
      "author_tag": "By Little Dreamers",
      "character_description": "A fluffy vibrant turquoise-blue bunny creature with giant upright ears, expressive big eyes, wearing a leather backpack and sneakers",
      "pages": [
        {{
          "page_number": 1,
          "full_text_narration": "Full combined sentences for the audio voice reader.",
          "snippets": [
            "Ziggy lived beside the Whispering Forest.",
            "Every day was an adventure.",
            "Even when he was not looking for one."
          ],
          "image_action_prompt": "3D Pixar render, sitting on rocking chair on wooden treehouse porch reading a glowing storybook next to a friendly little leaf-creature, sunny magical forest with flowers, masterpiece 8k"
        }}
      ],
      "coloring_prompts": [
        "Ziggy happily running across a mushroom bridge with his backpack",
        "Ziggy discovering a tiny glowing creature inside a hollow tree"
      ],
      "trivia": [
        {{"question": "Where does the story take place?", "options": ["Whispering Forest", "Cloud Mountain", "Crystal Beach"], "answer": "Whispering Forest"}},
        {{"question": "What does the hero love doing?", "options": ["Going on adventures", "Taking naps", "Eating stones"], "answer": "Going on adventures"}}
      ],
      "word_search_words": ["ZIGGY", "FOREST", "MAGIC", "QUEST", "STORY"]
    }}
    """
    
    response = client.models.generate_content(
        model='gemini-3.6-flash',
        contents=f"Story Concept: {user_prompt}",
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json"
        )
    )
    return json.loads(response.text)

def generate_imagen_artwork(api_key, prompt, character_desc, is_coloring=False):
    """Uses Google Imagen 3 API directly for high-resolution 3D Pixar quality renders."""
    client = genai.Client(api_key=api_key)
    
    if is_coloring:
        full_prompt = (
            f"Children coloring book page, clean bold crisp black line art, pure white background, "
            f"zero shading, zero gradients, vector coloring sheet: {character_desc}, {prompt}"
        )
    else:
        full_prompt = (
            f"Pixar 3D animated movie render, children storybook illustration, {character_desc}, {prompt}, "
            f"ultra detailed soft fluffy fur texture, big expressive glossy eyes, vibrant warm lighting, "
            f"enchanted whimsical environment, 8k resolution, cinematic lighting, masterpiece"
        )
        
    for attempt in range(2):
        try:
            result = client.models.generate_images(
                model='imagen-3.0-generate-002',
                prompt=full_prompt,
                config=dict(
                    number_of_images=1,
                    aspect_ratio="1:1",
                    output_mime_type="image/jpeg"
                )
            )
            image_bytes = result.generated_images[0].image.image_bytes
            return Image.open(io.BytesIO(image_bytes))
        except Exception:
            time.sleep(2)
            
    fb = Image.new('RGB', (1024, 1024), color=(240, 235, 220))
    draw = ImageDraw.Draw(fb)
    draw.rectangle([20, 20, 1004, 1004], outline=(190, 150, 90), width=5)
    return fb

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

def build_pdf(book_data, framed_story_images, coloring_images, include_acts):
    pdf = SquareStorybookPDF(orientation='P', unit='mm', format=(210, 210))
    pdf.set_auto_page_break(auto=False)
    
    title = clean_pdf_text(book_data.get("title", "A Magical Journey"))
    subtitle = clean_pdf_text(book_data.get("subtitle", "Book 0 | Introduction Story"))
    author = clean_pdf_text(book_data.get("author_tag", "By Little Dreamers"))
    
    # 1. Full-Bleed Cover Page
    pdf.add_page()
    if framed_story_images:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
            framed_story_images[0].save(tmp.name)
            cov_path = tmp.name
        pdf.image(cov_path, x=0, y=0, w=210, h=210)
        os.remove(cov_path)
        
    pdf.set_fill_color(255, 252, 245)
    pdf.set_draw_color(212, 175, 55)
    pdf.set_line_width(1.2)
    pdf.rect(x=15, y=16, w=180, h=44, style='FD')
    
    pdf.set_xy(18, 22)
    pdf.set_font("Helvetica", "B", 20)
    pdf.set_text_color(55, 40, 50)
    pdf.multi_cell(174, 9, title, align='C')
    
    pdf.set_xy(18, 46)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(115, 95, 80)
    pdf.cell(174, 6, subtitle, align='C')
    
    pdf.set_xy(15, 186)
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(60, 45, 35)
    pdf.cell(180, 8, author, align='C')

    # 2. Story Pages (Full-Bleed with Composited Scrolls)
    for img in framed_story_images:
        pdf.add_page()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
            img.save(tmp.name)
            page_path = tmp.name
        pdf.image(page_path, x=0, y=0, w=210, h=210)
        os.remove(page_path)

    # 3. Coloring Pages
    if include_acts and coloring_images:
        for idx, c_img in enumerate(coloring_images):
            pdf.add_page()
            pdf.set_fill_color(255, 255, 255)
            pdf.rect(0, 0, 210, 210, style='F')
            
            pdf.set_xy(10, 10)
            pdf.set_font("Helvetica", "B", 16)
            pdf.set_text_color(60, 45, 55)
            pdf.cell(190, 8, f"Coloring Studio - Sheet {idx + 1}", align='C', ln=True)
            
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
                c_img.save(tmp.name)
                c_path = tmp.name
            pdf.image(c_path, x=15, y=22, w=180, h=175)
            os.remove(c_path)

    # 4. Activity Pages
    if include_acts:
        pdf.add_page()
        pdf.set_fill_color(252, 250, 245)
        pdf.rect(0, 0, 210, 210, style='F')
        
        pdf.set_xy(10, 12)
        pdf.set_font("Helvetica", "B", 18)
        pdf.set_text_color(60, 45, 55)
        pdf.cell(190, 8, "Story Games & Quiz", align='C', ln=True)
        pdf.ln(4)
        
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(80, 60, 70)
        pdf.set_x(15)
        pdf.cell(180, 6, "1. Magic Word Hunt", ln=True)
        
        words_list = book_data.get("word_search_words", ["ZIGGY", "FOREST", "MAGIC"])
        grid, placed_words = generate_word_search_grid(words_list, size=8)
        
        start_x = 18
        start_y = 34
        cell_size = 8.5
        pdf.set_font("Courier", "B", 12)
        pdf.set_draw_color(200, 190, 175)
        
        for r_idx, row in enumerate(grid):
            for c_idx, letter in enumerate(row):
                x = start_x + (c_idx * cell_size)
                y = start_y + (r_idx * cell_size)
                pdf.set_fill_color(255, 255, 255)
                pdf.rect(x, y, cell_size, cell_size, style='FD')
                pdf.set_xy(x, y + 1.2)
                pdf.cell(cell_size, cell_size - 1.2, letter, align='C')
                
        pdf.set_xy(95, 34)
        pdf.set_font("Helvetica", "B", 10.5)
        pdf.set_text_color(100, 80, 90)
        pdf.cell(90, 5, "WORDS TO FIND:", ln=True)
        pdf.set_font("Helvetica", "", 10)
        for w in placed_words:
            pdf.set_x(97)
            pdf.cell(90, 5, f"[  ]  {w}", ln=True)
            
        pdf.ln(12)
        pdf.set_xy(15, 115)
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(80, 60, 70)
        pdf.cell(180, 6, "2. Story Detective Quiz", ln=True)
        
        for q_idx, q in enumerate(book_data.get("trivia", [])):
            q_text = clean_pdf_text(q.get('question', ''))
            pdf.set_x(18)
            pdf.set_font("Helvetica", "B", 10.5)
            pdf.set_text_color(50, 40, 45)
            pdf.multi_cell(174, 5.5, f"Q{q_idx + 1}: {q_text}")
            pdf.set_font("Helvetica", "", 10)
            for opt in q.get("options", []):
                opt_text = clean_pdf_text(opt)
                pdf.set_x(24)
                pdf.cell(168, 5, f"(   )  {opt_text}", ln=True)
            pdf.ln(2)

    return bytes(pdf.output())

# --- Application Execution ---
if st.button("✨ Generate Deluxe Picture Book", type="primary"):
    if not gemini_key:
        st.error("Please enter your Gemini API Key in the sidebar.")
    elif not story_prompt.strip():
        st.error("Please describe your story idea.")
    else:
        with st.spinner(f"Writing {pages_count}-page picture book with scroll storytelling..."):
            try:
                book = generate_storybook_data(gemini_key, story_prompt, pages_count, age_group)
            except Exception as e:
                st.error(f"Error creating story: {e}")
                st.stop()

        st.success(f"✨ Created: **{book.get('title')}**")
        
        pages_list = book.get("pages", [])
        char_desc = book.get("character_description", "")
        
        # 1. Render Scene Artworks via Google Imagen 3
        raw_images = []
        progress_bar = st.progress(0)
        total_items = len(pages_list) + (2 if include_activities else 0)
        step = 0
        
        for idx, p in enumerate(pages_list):
            with st.spinner(f"Generating Pixar-quality artwork for page {idx + 1} with Imagen 3..."):
                img = generate_imagen_artwork(gemini_key, p.get("image_action_prompt"), char_desc)
                raw_images.append(img)
            step += 1
            progress_bar.progress(step / total_items)

        # 2. Composite Scrolls & Borders
        framed_images = []
        for idx, p in enumerate(pages_list):
            framed = apply_storybook_frame(raw_images[idx], p.get("snippets", []))
            framed_images.append(framed)

        # 3. Render Coloring Sheets
        coloring_images = []
        if include_activities:
            for idx, c_prompt in enumerate(book.get("coloring_prompts", [])[:2]):
                with st.spinner(f"Generating line-art coloring page {idx + 1}..."):
                    c_img = generate_imagen_artwork(gemini_key, c_prompt, char_desc, is_coloring=True)
                    coloring_images.append(c_img)
                step += 1
                progress_bar.progress(step / total_items)

        # 4. Generate Voice Audio
        audio_files = []
        if enable_audio:
            with st.spinner("Recording neural bedtime story narration..."):
                for idx, p in enumerate(pages_list):
                    tmp_audio = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
                    asyncio.run(generate_narration_audio(p.get("full_text_narration", ""), tmp_audio.name))
                    audio_files.append(tmp_audio.name)

        # 5. Live Showcase
        tab1, tab2, tab3 = st.tabs(["📖 Illustrated Book", "🖍️ Coloring Sheets", "🎮 Activities"])
        
        with tab1:
            for idx, framed_img in enumerate(framed_images):
                st.markdown(f"### Page {idx + 1}")
                st.image(framed_img, use_container_width=True)
                if enable_audio and idx < len(audio_files):
                    st.audio(audio_files[idx], format="audio/mp3")
                st.divider()
                
        with tab2:
            if coloring_images:
                cols = st.columns(len(coloring_images))
                for c_idx, c_pic in enumerate(coloring_images):
                    with cols[c_idx]:
                        st.image(c_pic, caption=f"Coloring Sheet {c_idx + 1}", use_container_width=True)
                        
        with tab3:
            if include_activities:
                col_a, col_b = st.columns(2)
                with col_a:
                    st.subheader("🧩 Word Search Keywords")
                    st.write(", ".join(book.get("word_search_words", [])))
                with col_b:
                    st.subheader("💡 Story Quiz")
                    for q in book.get("trivia", []):
                        st.write(f"**{q.get('question')}**")
                        st.write("Options:", ", ".join(q.get("options", [])))

        # 6. Build PDF
        with st.spinner("Compiling square picture book PDF..."):
            pdf_bytes = build_pdf(book, framed_images, coloring_images, include_activities)
            
        st.download_button(
            label="📥 Download Square Storybook PDF",
            data=pdf_bytes,
            file_name=f"{clean_pdf_text(book.get('title', 'storybook')).replace(' ', '_').lower()}.pdf",
            mime="application/pdf"
        )
