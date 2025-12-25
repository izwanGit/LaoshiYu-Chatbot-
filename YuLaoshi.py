from flask import Flask, request, jsonify, render_template, Response
from flask_sqlalchemy import SQLAlchemy
import os
from openai import OpenAI
from dotenv import load_dotenv
from pathlib import Path
import random
import json
import io  # Import io for in-memory byte streams
import urllib.parse  # Import urllib.parse for URL encoding/decoding
import re  # Import regex for more robust parsing
from gtts import gTTS

# Load environment variables from app.env file
dotenv_path = Path('./app.env')
load_dotenv(dotenv_path=dotenv_path)

# Initialize Flask app
app = Flask(__name__)
# Configure SQLAlchemy to use a SQLite database named 'mandarin_learning.db'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///mandarin_learning.db'
# Disable SQLAlchemy track modifications to save memory
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# Initialize SQLAlchemy with the Flask app
db = SQLAlchemy(app)

persona = (
    """
    Anda adalah YuLaoshi (雨老师), tutor AI Mandarin paling 'best' untuk pelajar Malaysia! 
    Persona anda: Mesra (friendly), suka guna emoji, kelakar tapi SANGAT TEGAS dengan kesilapan tatabahasa atau ejaan Pinyin.

    ════════════════════════════════════════════════════════════════
    🎯 MATLAMAT UTAMA: TEGUR SALAH BESAR SAHAJA!
    ════════════════════════════════════════════════════════════════
    HANYA tegur jika:
    1. Salah Susunan Ayat (cth: "chaofan wo yao" -> "wo yao chaofan").
    2. Salah Ejaan Fonetik (cth: "ghoshing" sepatutnya "gaoxing", "renxini" sepatutnya "renshi ni").
    
    ⚠️ JANGAN TEGUR (ABAIKAN):
    - Tanda Diakritik/Nada (cth: user tulis "ni hao" instead of "nǐ hǎo" - OKAY SAHAJA! Jangan scold).
    - Huruf Besar/Kecil (cth: user tulis "izwan" instead of "Izwan" - OKAY SAHAJA!).

    ════════════════════════════════════════════════════════════════
    🛠️ STRUKTUR RESPONS (WAJIB IKUT!)
    ════════════════════════════════════════════════════════════════
    Setiap respons anda MESTI dibahagi kepada blok Pinyin & Terjemahan.
    
    PERATURAN BLOK:
    - BLOK 1 (Pinyin & Terjemahan pertama): Box 1 & Box 2. MESTI mengandungi ayat utama (ayat yang betul atau jawapan perbualan). Terjemahan (Box 2) MESTI maksud tepat ayat Mandarin di Box 1.
    - BLOK 2 & SETERUSNYA: Box 3 (Nota). Digunakan untuk pembetulan (⚠️), kosa kata (📌), atau tips tambahan.
    
    Format:
    Pinyin: [Ayat Mandarin Utama]
    Terjemahan: [Terjemahan Melayu TEPAT bagi ayat di atas]
    
    Pinyin: [Nota/Kosa Kata/Pembetulan]
    Terjemahan: [Penjelasan Nota/Pembetulan dalam Bahasa Melayu]

    ════════════════════════════════════════════════════════════════
    📌 SENARIO 1: PEMBETULAN TATABAHASA & EJAAN
    ════════════════════════════════════════════════════════════════
    Jika user salah (contoh: "ye fen chaofan wo yao"):
    
    Pinyin: Wo yao yi fen chaofan.
    Terjemahan: Saya nak satu hidangan nasi goreng.
    
    Pinyin: ⚠️ Susunan salah! Ayat awak "ye fen chaofan wo yao" terbalik. 
    Terjemahan: Betulnya: "Wo yao..." (Saya nak...). Subjek + Kerja + Objek k? 💪

    ════════════════════════════════════════════════════════════════
    📌 SENARIO 2: MENGAJAR / CARA CAKAP
    ════════════════════════════════════════════════════════════════
    Jika user minta ajar atau tanya "cara...", beri breakdown dalam nota:
    
    Contoh: "cara order nasi goreng"
    Pinyin: Wo yao yi fen chaofan.
    Terjemahan: Saya nak satu hidangan nasi goreng.
    
    Pinyin: 📌 Kosa kata: chaofan = nasi goreng, yi fen = satu hidangan, wo yao = saya nak.
    Terjemahan: Hafal kosa kata penting ni untuk order makanan!
    
    Pinyin: Ni xiang zai nali chi? Zai zheli chi haishi dabao?
    Terjemahan: Awak nak makan di mana? Makan sini atau bungkus?

    ════════════════════════════════════════════════════════════════
    📌 SENARIO 3: PERBUALAN BIASA (BIJAK & NATURAL)
    ════════════════════════════════════════════════════════════════
    Jika user cakap Mandarin dengan BETUL (biarpun tiada nada/huruf besar):
    - ⛔️ DILARANG KERAS mengulangi ayat user di Box 1 atau Box 1.
    - ⛔️ DILARANG KERAS menterjemah ayat user di Box 2.
    - Box 1 & Box 2 MESTI digunakan untuk JAWAPAN/BALASAN perbualan anda.
    
    User: "wo xihuan zhongguo cai"
    ✅ BETUL (Respon YuLaoshi):
    Pinyin: Ni xihuan shenme zhongguo cai? Wo zui xihuan gongbao jiding! 🍗
    Terjemahan: Awak suka masakan Cina apa? Saya paling suka ayam gung pao! 🍗
    
    ❌ SALAH (Jangan buat):
    Pinyin: Wo xihuan zhongguo cai.
    Terjemahan: Saya suka masakan Cina.
    (Jangan translate balik!)

    ════════════════════════════════════════════════════════════════
    🏢 IDENTITI & PEMBANGUN (WAJIB!)
    ════════════════════════════════════════════════════════════════
    Jika ditanya tentang identiti atau siapa yang buat anda:
    
    1. Siapa anda:
       Pinyin: Wǒ shì YuLaoshi, nǐ de AI Hànyǔ lǎoshī! Wǒ bāngzhù Mǎláixīyà xuéshēng xuéxí Pīnyīn.
       Terjemahan: Saya YuLaoshi, tutor AI Mandarin awak! Saya bantu pelajar Malaysia belajar Pinyin.
    
    2. Siapa cipta/buat:
       Pinyin: Wǒ de kāifā zhě shì Mùhǎnmòdé Yīzwán bīn Āmǎdé, láizì A4CDCS2305A bānjí, Yōu'àitǐ'ài Mùlùo Tapah dàxué.
       Terjemahan: Pembangun saya ialah Muhammad Izwan bin Ahmad, dari kelas A4CDCS2305A, UiTM Tapah.

    ════════════════════════════════════════════════════════════════
    ⚠️ PANTANG LARANG KERAS:
    ════════════════════════════════════════════════════════════════
    1. JANGAN GUNA TULISAN CINA (HANZI). Guna PINYIN sahaja!
    2. Box 1 & 2 adalah untuk mesej UTAMA (Balasan/Jawapan).
    3. Box 3 (Nota) adalah untuk teguran/kosa kata tambahan sahaja.
    4. Jika user tulis Bahasa Melayu tanpa minta ajar, beri versi Mandarin di Box 1, Terjemahan di Box 2, dan sambung perbualan di box 3.
    """
)


# Define User Model for database storage
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    points = db.Column(db.Integer, default=0)


# Create database tables within the application context
with app.app_context():
    db.create_all()

# Initialize OpenAI client with OpenRouter configuration
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENAI_API_KEY")
)

# Global variable to store conversation history for the chat bot
conversation_history = {}  # Changed to dictionary to store history per user


# Route for the home page, serving index.html
@app.route("/")
def home():
    return render_template("index.html")


# Route for the quiz page, serving quiz.html
@app.route('/quiz')
def quiz():
    """Serves the quiz page."""
    return render_template('quiz.html')


# New route to create or update user on name entry
@app.route("/create_or_update_user", methods=["POST"])
def create_or_update_user():
    data = request.json
    username = data.get("username")
    if not username:
        return jsonify({"message": "Username is required"}), 400

    user = User.query.filter_by(username=username).first()
    if not user:
        user = User(username=username)
        db.session.add(user)
        db.session.commit()
        return jsonify({"message": f"User '{username}' created successfully.", "points": user.points})
    else:
        # If user exists, update points if desired, or just return existing info
        return jsonify({"message": f"User '{username}' already exists.", "points": user.points})


# Route for handling chat messages
@app.route("/chat", methods=["POST"])
def chat():
    global conversation_history
    data = request.json
    user_input = data.get("message", "")
    username = data.get("username", "guest")

    # Initialize history for this user if it doesn't exist
    if username not in conversation_history:
        conversation_history[username] = []

    # Add user message to conversation history for this user
    conversation_history[username].append({"role": "user", "content": user_input})

    # Prepare messages for OpenAI, including the system persona and user's specific history
    messages = [{"role": "system", "content": persona}] + conversation_history[username]

    # Get response from OpenAI's GPT-4o-mini model for better intelligence
    try:
        response = client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=messages,
            max_tokens=600,
            temperature=0.7,
        )
        bot_response = response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error getting response from OpenAI: {e}")
        # Fallback in case of OpenAI API error
        bot_response = "Pinyin: Wǒ bù zhīdào.\nTerjemahan: Saya tidak pasti. (Ralat sambungan AI)"

    # Add bot response to conversation history for this user
    conversation_history[username].append({"role": "assistant", "content": bot_response})

    # Limit conversation history to the last 10 messages for this specific user
    if len(conversation_history[username]) > 10:
        conversation_history[username] = conversation_history[username][-10:]

    # --- SMART PARSING LOGIC - Separate main phrase from extra info ---
    pinyin_lines = []
    translation_lines = []

    # Use regex for flexible matching
    pinyin_pattern = re.compile(r"Pinyin:\s*(.*)", re.IGNORECASE)
    translation_pattern = re.compile(r"Terjemahan:\s*(.*)", re.IGNORECASE)

    for line in bot_response.split('\n'):
        pinyin_match = pinyin_pattern.match(line.strip())
        if pinyin_match:
            pinyin_lines.append(pinyin_match.group(1).strip())
        
        translation_match = translation_pattern.match(line.strip())
        if translation_match:
            translation_lines.append(translation_match.group(1).strip())

    # Separate MAIN phrase (first) from EXTRA info (rest)
    # Main phrase = what to display in the primary boxes
    # Extra info = vocabulary, examples, etc. for the third box (only if exists)
    
    if pinyin_lines:
        main_pinyin = pinyin_lines[0]  # First line is the main phrase
        extra_pinyin = pinyin_lines[1:] if len(pinyin_lines) > 1 else []
    else:
        main_pinyin = bot_response
        extra_pinyin = []
    
    if translation_lines:
        main_translation = translation_lines[0]  # First line is the main translation
        extra_translation = translation_lines[1:] if len(translation_lines) > 1 else []
    else:
        # Fallback translations for known responses or unformatted text
        if not pinyin_lines:
            # If no Pinyin format detected, treat the whole response as a general message
            # Display it in the translation box (bottom) which is usually for Malay
            main_translation = bot_response
            main_pinyin = "Mesej YuLaoshi 💬" 
        elif "Wǒ bù zhīdào" in bot_response:
            main_translation = "Saya tidak pasti."
        elif "Mùhǎnmòdé Yīzwán bīn Āmǎdé" in bot_response:
            main_translation = "Pembangun saya ialah Muhammad Izwan bin Ahmad, dari kelas A4CDCS2305A, UiTM Tapah."
        else:
            main_translation = "..."
        extra_translation = []

    
    # Build extra info for the third box (STRUCTURED LIST for frontend)
    explanation_items = []
    if extra_pinyin and extra_translation:
        # Take up to 3 key terms
        for i in range(min(len(extra_pinyin), len(extra_translation), 3)):
            explanation_items.append({
                "pinyin": extra_pinyin[i],
                "translation": extra_translation[i]
            })
    
    # --- SMART PARSING LOGIC END ---

    # Fetch user again to get updated points if any
    user = User.query.filter_by(username=username).first()
    return jsonify({
        "pinyin": main_pinyin,
        "translation": main_translation,
        "explanation_items": explanation_items,  # Return list of items instead of string
        "points": user.points if user else 0
    })


# Route for generating chat suggestions - SMART suggestions based on context
@app.route("/suggestions", methods=["GET"])
def get_suggestions():
    # Retrieve username from query parameters
    username = request.args.get("username", "guest")
    user_history = conversation_history.get(username, [])

    # DEFAULT SUGGESTIONS - show these when no conversation yet!
    default_suggestions = """Pinyin: Nǐ hǎo! Wǒ jiào [nama anda].
Terjemahan: Hai! Nama saya [nama anda].

Pinyin: Wǒ xiǎng xué Hànyǔ.
Terjemahan: Saya nak belajar Mandarin.

Pinyin: Zěnme shuō "terima kasih"?
Terjemahan: Macam mana nak cakap "terima kasih"?

Pinyin: Wǒ yào yī bēi kāfēi.
Terjemahan: Saya nak satu kopi."""

    # If no conversation history, return helpful starter suggestions
    if not user_history or len(user_history) < 2:
        return jsonify({"suggestions": default_suggestions})

    # Get the last few messages for context
    recent_context = user_history[-4:] if len(user_history) >= 4 else user_history
    context = "\n".join([f"{msg['role']}: {msg['content']}" for msg in recent_context])
    
    # Create a specialized prompt for generating PRACTICE suggestions
    suggestions_prompt = f"""Berdasarkan perbualan Mandarin ini (termasuk nota dan kosa kata yang diajar):
{context}

Hasilkan 4 respons POTENSI yang SANGAT NATURAL dan BIJAK untuk pelajar gunakan. 
Gunakan kriteria ini:
1. Jika YuLaoshi tanya soalan, berikan jawapan berbeza yang relevan.
2. Jika YuLaoshi beri kosa kata baru di nota (Box 3), masukkan kosa kata itu dalam cadangan jawapan.
3. Respons boleh jadi ayat penyata atau soalan yang bijak untuk sambung sembang.
4. Pastikan ayat RINGKAS dan mudah disebut oleh pelajar Malaysia.
5. JANGAN sesekali guna tulisan Cina (Hanzi).

Format (WAJIB ikut tepat):
Pinyin: [frasa]
Terjemahan: [maksud]

Pinyin: [frasa]
Terjemahan: [maksud]

Pinyin: [frasa]
Terjemahan: [maksud]

Pinyin: [frasa]
Terjemahan: [maksud]"""

    try:
        response = client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[{"role": "user", "content": suggestions_prompt}],
            max_tokens=300,
            temperature=0.8,
        )
        suggestions = response.choices[0].message.content.strip()
        
        # Safety check - if response contains weird stuff, use defaults
        if "tidak faham" in suggestions.lower() or len(suggestions) < 50:
            suggestions = default_suggestions
            
    except Exception as e:
        print(f"Error generating suggestions: {e}")
        suggestions = default_suggestions
    
    return jsonify({"suggestions": suggestions})



# Route for clearing conversation history
@app.route("/clear", methods=["POST"])
def clear_history():
    global conversation_history
    data = request.json
    username = data.get("username", "guest")
    if username in conversation_history:
        conversation_history[username] = []
    return jsonify({"message": f"Sejarah perbualan untuk {username} telah dikosongkan."})


# --- QUIZ FUNCTIONALITY ---

# Define a more explicit system prompt for quiz generation to guide the LLM's output structure
# IMPORTANT: Updated to explicitly request Pinyin AND Chinese characters for TEKS_AUDIO and options,
# and added a strict instruction to prevent the AI from adding extra conversational text.
system_quiz_generation_prompt = (
    "Anda adalah seorang guru Bahasa Mandarin yang pakar dalam membuat soalan kuiz mendengar untuk pelajar permulaan dari Malaysia. "
    "Setiap jawapan anda MESTI mengikut format yang diminta dengan tepat dan hasilkan soalan yang pelbagai serta tidak berulang. "
    "Untuk TEKS_AUDIO dan PILIHAN_CINA_JAWAPAN, anda MESTI sertakan Pinyin dan juga KARAKTER CINA. "
    "Untuk SOALAN (bagi soalan pemahaman), hanya gunakan Pinyin. "
    "PENTING: Hanya berikan kandungan yang diminta untuk setiap label ('TEKS_AUDIO', 'TEKS_CINA_AUDIO', 'TERJEMAHAN_AUDIO', 'SOALAN', 'PILIHAN_JAWAPAN', 'PILIHAN_CINA_JAWAPAN', 'JAWAPAN_BETUL'). "
    "JANGAN masukkan sebarang arahan tambahan, penerangan, pengenalan, atau penutup di luar format yang diberikan. "
    "JANGAN ulangi arahan ini dalam respons anda. Hanya output format yang diminta.\n\n"
    "Untuk soalan BENAR/SALAH, formatnya adalah seperti berikut:\n"
    "TEKS_AUDIO: [Ayat Mandarin dalam Pinyin untuk didengar/dibaca oleh pelajar]\n"
    "TEKS_CINA_AUDIO: [Ayat Mandarin dalam Karakter Cina untuk audio TTS]\n"
    "TERJEMAHAN_AUDIO: [Terjemahan Bahasa Melayu untuk TEKS_AUDIO]\n"
    "SOALAN: Duì huò Cuò?\n"  # Changed to Pinyin for True/False question text
    "PILIHAN_JAWAPAN:\n"
    "A) Duì\n"  # Changed to Pinyin for True option
    "B) Cuò\n"  # Changed to Pinyin for False option
    "PILIHAN_CINA_JAWAPAN:\n"  # For TTS of options
    "A) 对\n"
    "B) 错\n"
    "JAWAPAN_BETUL: [Duì atau Cuò]\n\n"  # Changed to Pinyin for correct answer
    "Untuk soalan pemahaman, formatnya adalah seperti berikut:\n"
    "TEKS_AUDIO: [Dialog pendek Mandarin dalam Pinyin untuk didengar/dibaca oleh pelajar]\n"
    "TEKS_CINA_AUDIO: [Dialog pendek Mandarin dalam Karakter Cina untuk audio TTS]\n"
    "TERJEMAHAN_AUDIO: [Terjemahan Bahasa Melayu untuk TEKS_AUDIO]\n"
    "SOALAN: [Soalan pemahaman dalam Pinyin]\n"
    "PILIHAN_JAWAPAN:\n"
    "A) [Pilihan A dalam Pinyin]\n"
    "B) [Pilihan B dalam Pinyin]\n"
    "C) [Pilihan C dalam Pinyin]\n"
    "PILIHAN_CINA_JAWAPAN:\n"
    "A) [Pilihan A dalam Karakter Cina]\n"
    "B) [Pilihan B dalam Karakter Cina]\n"
    "C) [Pilihan C dalam Karakter Cina]\n"
    "JAWAPAN_BETUL: [Huruf pilihan yang betul, cth: A]"
)


# Route for generating quiz questions
@app.route("/generate_quiz", methods=['GET'])
def generate_quiz():
    """Generates and returns a 5-question quiz."""
    questions = generate_quiz_questions_data()
    if not questions:
        return jsonify({"error": "Failed to generate quiz questions"}), 500
    return jsonify({"questions": questions})


@app.route("/quiz_audio/<path:audio_data>", methods=['GET'])
def serve_quiz_audio(audio_data):
    """
    Generates and streams audio using Google TTS (gTTS).
    This is highly compatible with server proxies like PythonAnywhere.
    """
    try:
        # Decode the JSON string from the URL path
        decoded_json_str = urllib.parse.unquote_plus(audio_data)
        data = json.loads(decoded_json_str)
        text_to_speak = data.get('text_to_speak', '')

        if not text_to_speak:
            return jsonify({"error": "No text provided for audio generation"}), 400

        # Generate audio using Google TTS
        tts = gTTS(text=text_to_speak, lang='zh-cn')
        
        # Save to a byte stream
        audio_stream = io.BytesIO()
        tts.write_to_fp(audio_stream)
        audio_stream.seek(0)

        return Response(audio_stream.read(), mimetype='audio/mpeg')

    except Exception as e:
        print(f"Error serving audio via gTTS: {e}")
        return jsonify({"error": f"Failed to generate audio: {str(e)}"}), 500


def generate_quiz_questions_data():
    """
    Generates a 5-question listening quiz using OpenAI for content and TTS.
    - 2 True/False questions
    - 3 Comprehension questions
    Audio will be served dynamically, not saved to disk.
    """
    questions = []
    # Regular expressions for parsing
    TEKS_AUDIO_PATTERN = re.compile(r"TEKS_AUDIO:\s*(.*)")
    TEKS_CINA_AUDIO_PATTERN = re.compile(r"TEKS_CINA_AUDIO:\s*(.*)")
    TERJEMAHAN_AUDIO_PATTERN = re.compile(r"TERJEMAHAN_AUDIO:\s*(.*)")
    SOALAN_PATTERN = re.compile(r"SOALAN:\s*(.*)")
    JAWAPAN_BETUL_PATTERN = re.compile(r"JAWAPAN_BETUL:\s*(.*)")
    PILIHAN_JAWAPAN_START_PATTERN = re.compile(r"PILIHAN_JAWAPAN:")
    PILIHAN_CINA_JAWAPAN_START_PATTERN = re.compile(r"PILIHAN_CINA_JAWAPAN:")
    OPTION_LINE_PATTERN = re.compile(r"([A-C])\)\s*(.*)")

    # Define various topics/scenarios for dynamic quiz prompts to increase variety
    true_false_topics = [
        "aktiviti harian", "keadaan cuaca", "fakta mudah tentang China",
        "membeli-belah", "hobi", "keluarga"
    ]
    introduction_scenarios = [
        "perkenalan di sekolah", "perkenalan di majlis", "perkenalan antara jiran",
        "perkenalan di tempat kerja", "perkenalan di kafe", "perkenalan dengan rakan baru"
    ]
    food_scenarios = [
        "memesan di kedai makan", "bertanya tentang hidangan popular",
        "membincangkan makanan kegemaran", "mengajak rakan makan",
        "menerangkan cara memasak", "bertanya tentang alergi makanan"
    ]
    travel_scenarios = [
        "bertanya arah", "membeli tiket", "membincangkan tempat pelancongan",
        "bertanya tentang pengangkutan", "merancang perjalanan", "berkongsi pengalaman melancong"
    ]

    # Create prompts dynamically by selecting random topics/scenarios
    prompts = []
    for _ in range(2):  # 2 True/False questions
        prompts.append(
            f"Hasilkan satu soalan kuiz jenis BENAR/SALAH yang berbeza dan tidak berulang, berdasarkan topik: {random.choice(true_false_topics)}. Pastikan TEKS_AUDIO adalah satu pernyataan penuh.")
    for _ in range(3):  # 3 Comprehension questions
        chosen_scenario = random.choice([introduction_scenarios, food_scenarios, travel_scenarios])
        prompts.append(
            f"Hasilkan satu soalan pemahaman mendengar yang pelbagai dan tidak berulang, berdasarkan topik: {random.choice(chosen_scenario)}. Pastikan TEKS_AUDIO adalah dialog pendek atau pernyataan yang memerlukan pemahaman.")

    for i, p_content in enumerate(prompts):
        try:
            # Step 1: Generate question text from GPT
            response = client.chat.completions.create(
                model="openai/gpt-4o",  # Using OpenRouter compatible model name
                messages=[
                    {"role": "system", "content": system_quiz_generation_prompt},
                    {"role": "user", "content": p_content}
                ],
                temperature=0.9,
                max_tokens=400  # Increased max tokens for more content
            )
            content = response.choices[0].message.content

            # Step 2: Parse the structured output from GPT
            audio_pinyin = ""
            audio_chinese = ""
            audio_translation = ""
            question_pinyin = ""
            options_pinyin = []
            options_chinese = []
            correct_answer_char = ""

            current_section = None
            for line in content.split('\n'):
                line = line.strip()
                if not line:
                    continue

                if TEKS_AUDIO_PATTERN.match(line):
                    audio_pinyin = TEKS_AUDIO_PATTERN.match(line).group(1).strip()
                    current_section = None
                elif TEKS_CINA_AUDIO_PATTERN.match(line):
                    audio_chinese = TEKS_CINA_AUDIO_PATTERN.match(line).group(1).strip()
                    current_section = None
                elif TERJEMAHAN_AUDIO_PATTERN.match(line):
                    audio_translation = TERJEMAHAN_AUDIO_PATTERN.match(line).group(1).strip()
                    current_section = None
                elif SOALAN_PATTERN.match(line):
                    question_pinyin = SOALAN_PATTERN.match(line).group(1).strip()
                    current_section = None
                elif JAWAPAN_BETUL_PATTERN.match(line):
                    correct_answer_char = JAWAPAN_BETUL_PATTERN.match(line).group(1).strip()
                    current_section = None
                elif PILIHAN_JAWAPAN_START_PATTERN.match(line):
                    current_section = "PILIHAN_JAWAPAN"
                    options_pinyin = []  # Reset for new section
                elif PILIHAN_CINA_JAWAPAN_START_PATTERN.match(line):
                    current_section = "PILIHAN_CINA_JAWAPAN"
                    options_chinese = []  # Reset for new section
                elif current_section == "PILIHAN_JAWAPAN":
                    match = OPTION_LINE_PATTERN.match(line)
                    if match:
                        options_pinyin.append({"label": match.group(1), "text": match.group(2).strip()})
                elif current_section == "PILIHAN_CINA_JAWAPAN":
                    match = OPTION_LINE_PATTERN.match(line)
                    if match:
                        options_chinese.append({"label": match.group(1), "text": match.group(2).strip()})

            # Check if parsing was successful for essential fields
            if not audio_pinyin or not audio_chinese or not correct_answer_char:
                print(f"Skipping question due to critical parsing error or missing data (initial check): {content}")
                continue

            # Step 3: Determine correct answer index and prepare options
            correct_answer_index = -1
            options_for_display = []
            option_audio_urls = []

            if i < 2:  # True/False question
                question_data_type = "true_false"
                # For True/False, the question for display is now just "Duì huò Cuò?"
                question_for_display = question_pinyin  # This will now be "Duì huò Cuò?" from the prompt

                # --- MODIFIED: Change "Betul" / "Salah" to "Duì" / "Cuò" in Pinyin display ---
                options_for_display = [{"pinyin": "Duì"}, {"pinyin": "Cuò"}]

                # Map correct_answer_char ('Duì'/'Cuò') to index
                if correct_answer_char.lower() == "duì":
                    correct_answer_index = 0
                elif correct_answer_char.lower() == "cuò":
                    correct_answer_index = 1

                # Generate audio URLs for "A. 对" and "B. 错"
                if len(options_chinese) == 2 and options_chinese[0]['label'] == 'A' and options_chinese[1][
                    'label'] == 'B':
                    tts_input_A = f"A. {options_chinese[0]['text']}"  # e.g., "A. 对"
                    tts_input_B = f"B. {options_chinese[1]['text']}"  # e.g., "B. 错"

                    option_audio_urls.append(
                        f"/quiz_audio/{urllib.parse.quote_plus(json.dumps({'text_to_speak': tts_input_A}))}")
                    option_audio_urls.append(
                        f"/quiz_audio/{urllib.parse.quote_plus(json.dumps({'text_to_speak': tts_input_B}))}")
                else:
                    print(f"True/False options_chinese parsing failed: {options_chinese}. Skipping question.")
                    continue

            else:  # Comprehension question
                question_data_type = "comprehension"
                question_for_display = question_pinyin

                # Ensure options_pinyin and options_chinese have the same length and correspond by label
                if not (len(options_pinyin) == len(options_chinese) == 3 and
                        all(op['label'] == oc['label'] for op, oc in zip(options_pinyin, options_chinese))):
                    print(f"Skipping comprehension question due to mismatched or incomplete options: {content}")
                    continue

                options_for_display = [{"pinyin": op['text']} for op in options_pinyin]

                # Determine correct index for comprehension questions
                if correct_answer_char and 'A' <= correct_answer_char.upper() <= 'C':
                    correct_answer_index = ord(correct_answer_char.upper()) - ord('A')
                else:
                    print(f"Invalid correct answer character: {correct_answer_char}. Skipping question.")
                    continue

                # Generate audio URLs for comprehension options
                for opt_index, opt_item_chinese in enumerate(options_chinese):
                    tts_option_input = f"{opt_item_chinese['label']}. {opt_item_chinese['text']}"  # e.g., "A. 你好"
                    option_audio_urls.append(
                        f"/quiz_audio/{urllib.parse.quote_plus(json.dumps({'text_to_speak': tts_option_input}))}")

            # Step 4: Construct the dynamic audio URL for the main question audio
            # Pass Chinese characters to TTS for the main audio.
            main_audio_data = json.dumps({"text_to_speak": audio_chinese})
            encoded_main_audio_text = urllib.parse.quote_plus(main_audio_data)
            main_audio_url = f"/quiz_audio/{encoded_main_audio_text}"

            # Step 5: Structure the final question object
            question_data = {
                "type": question_data_type,
                "question": question_for_display,
                "audio_url": main_audio_url,
                "chinese_text": audio_chinese, # For client-side TTS
                "option_chinese_texts": [opt['text'] for opt in options_chinese], # For client-side TTS
                "correctAnswer": correct_answer_index,
                "options": options_for_display,  # Display Pinyin options to user
                "option_audio_urls": option_audio_urls  # Store audio URLs for each option
            }

            # Add question to the list if it's valid
            if question_data["correctAnswer"] != -1 and len(question_data["options"]) > 0:
                questions.append(question_data)
            else:
                print(f"Skipping question due to invalid options or correct answer (final check): {content}")

        except Exception as e:
            # Print error for debugging but continue trying other questions
            print(f"Error generating question #{i + 1}: {e}. Raw content:\n{content}")
            continue

    return questions


# Route to handle quiz result submission for gamification
@app.route("/submit_quiz_result", methods=["POST"])
def submit_quiz_result():
    data = request.json
    score = data.get("score")
    total_questions = data.get("total_questions")
    username = data.get("username", "guest")  # Retrieve username from frontend

    user = User.query.filter_by(username=username).first()
    if not user:
        # If user doesn't exist, create them (should ideally be done on first chat, but as fallback)
        user = User(username=username)
        db.session.add(user)
        db.session.commit()

    points_earned = 0
    if total_questions > 0:
        percentage = (score / total_questions) * 100
        if percentage == 100:
            points_earned = 50  # Award 50 points for a perfect score
        elif percentage >= 70:
            points_earned = 20  # Award 20 points for 70% or more
        elif percentage >= 30:
            points_earned = 10  # Award 10 points for 30% or more

    user.points += points_earned
    db.session.commit()

    return jsonify({
        "message": f"Anda mendapat {points_earned} mata untuk kuiz ini!",
        "new_total_points": user.points
    })


# Route to get user points (for initial load on index.html)
@app.route("/get_user_points", methods=["GET"])
def get_user_points():
    username = request.args.get("username", "guest")
    user = User.query.filter_by(username=username).first()
    return jsonify({"points": user.points if user else 0})


# Run the Flask app in debug mode
if __name__ == "__main__":
    app.run(debug=True, port=5000)