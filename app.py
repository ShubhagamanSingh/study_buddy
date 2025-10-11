import streamlit as st # type: ignore
from huggingface_hub import InferenceClient # type: ignore
from huggingface_hub.utils import HfHubHTTPError # type: ignore
from pymongo import MongoClient # type: ignore
import hashlib
from datetime import datetime

# --- Configuration ---
st.set_page_config(
    page_title="Study Buddy",
    page_icon="🎓",
    layout="wide"
)

# --- Custom CSS for Modern UI (consistent with other apps) ---
st.markdown("""
<style>
    .main {
        background-color: black;
    }
    .block-container {
        padding-top: 2rem;
    }
    .header-container {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 3rem 2rem;
        border-radius: 0 0 25px 25px;
        margin-bottom: 2rem;
        margin-top: -2rem;
        color: white;
        text-align: center;
    }
    .custom-card {
        background: white;
        padding: 2rem;
        border-radius: 20px;
        border: 1px solid #e0e0e0;
        box-shadow: 0 4px 20px rgba(0,0,0,0.08);
        margin-bottom: 1.5rem;
        display: none;    
    }
    .stButton button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        border-radius: 25px;
        padding: 0.75rem 2rem;
        font-weight: 600;
        font-size: 1rem;
        transition: all 0.3s ease;
        width: 100%;
    }
    .stButton button:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 25px rgba(102, 126, 234, 0.4);
    }
    /* Style for input widgets */
    .stTextInput input, .stTextArea textarea, .stNumberInput input, .stSelectbox div[data-baseweb="select"] {
        border-radius: 10px;
        border: 2px solid #e0e0e0;        
    }
    .stSelectbox div[data-baseweb="select"] > div {
        color: #fff; /* Ensure text inside selectbox is visible */
    }
    .stTextInput input:focus, .stTextArea textarea:focus, .stNumberInput input:focus {
        border-color: #667eea;
        box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
    }
    .info-message {
        background: linear-gradient(135deg, #2196F3 0%, #1976D2 100%);
        color: white;
        padding: 1.5rem;
        border-radius: 15px;
        text-align: center;
        margin: 1rem 0;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 44px;
        background-color: transparent;
    }
</style>
""", unsafe_allow_html=True)

# --- User Authentication and Data Management ---
# --- MongoDB Connection ---
@st.cache_resource
def get_mongo_client():
    """Establishes a connection to MongoDB and returns the collection object."""
    try:
        MONGO_URI = st.secrets["MONGO_URI"]
        DB_NAME = st.secrets["DB_NAME"]
        COLLECTION_NAME = st.secrets["COLLECTION_NAME"]
        client = MongoClient(MONGO_URI)
        return client[DB_NAME][COLLECTION_NAME]
    except Exception as e:
        st.error(f"Failed to connect to MongoDB: {e}")
        st.stop()

users_collection = get_mongo_client()

def hash_password(password):
    """Hashes a password for storing."""
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(stored_password, provided_password):
    """Verifies a provided password against a stored hash."""
    return stored_password == hash_password(provided_password)

def add_to_history(username, interaction_type, user_input, ai_response):
    """Adds a generated study interaction to the user's history."""
    history_entry = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type": interaction_type,
        "input": user_input,
        "response": ai_response
    }
    users_collection.update_one({"_id": username}, {"$push": {"history": {"$each": [history_entry], "$position": 0}}})

# Hugging Face token (securely stored in Streamlit secrets)
# Make sure to add HF_TOKEN to your Streamlit secrets
try:
    HF_TOKEN = st.secrets["HF_TOKEN"]
except FileNotFoundError:
    st.error("Streamlit secrets file not found. Please create a .streamlit/secrets.toml file with your HF_TOKEN.")
    st.stop()

client = InferenceClient("meta-llama/Meta-Llama-3-8B-Instruct", token=HF_TOKEN)

# --- System Prompts for different tools ---
SYSTEM_PROMPTS = {
    "Explainer": "You are an expert educator and study assistant. Your goal is to explain complex topics to students in a clear, simple, and engaging way. Use analogies and simple language. Format your response using Markdown.",
    "Summarizer": "You are an expert summarizer. Your goal is to condense study notes or long texts into key points for students. You must be concise and accurate. Format your response using Markdown.",
    "Quizzer": "You are an expert quiz master. Your goal is to create quizzes for students based on a topic or their notes. Create multiple-choice questions with a clear answer key at the end. Format your response using Markdown.",
    "Flashcard": "You are an expert flashcard creator. Your goal is to generate flashcards from a given topic or notes. Each flashcard should have a 'Term' and a 'Definition'. Format the output clearly using Markdown, with each flashcard separated by a horizontal rule (---)."
}

# --- AI & UI Component Functions ---

@st.cache_data(show_spinner=False) # Cache the AI response to avoid re-generating on widget interactions
def generate_ai_response(system_prompt, user_prompt):
    """
    Generates a response from the LLaMA model based on a system and user prompt.
    """
    messages = [
        {
            "role": "system",
            "content": system_prompt,
        },
        {"role": "user", "content": user_prompt},
    ]

    response_text = ""
    try:
        # Use chat_completion for conversational models like Llama-3
        for chunk in client.chat_completion(messages, max_tokens=2048, temperature=0.7, stream=True):
            # Add a check to ensure the choices list is not empty before accessing it
            if chunk.choices and chunk.choices[0].delta.content:
                response_text += chunk.choices[0].delta.content
    except HfHubHTTPError as e:
        # Specifically handle the 402 Payment Required error for monthly limits
        if e.response.status_code == 402:
            st.error("Sorry, we've reached our monthly usage limit for the AI model. Please check back later or contact the administrator.", icon="😔")
            return "The AI service is temporarily unavailable due to usage limits."
        st.error(f"An error occurred while communicating with the AI model: {e}", icon="💔")
        return "Sorry, I couldn't generate a response at this moment. Please try again later."
    except Exception as e:
        st.error(f"An error occurred while communicating with the AI model: {e}", icon="💔")
        return "Sorry, I couldn't generate a response at this moment. Please try again later."

    return response_text.strip()

def display_ai_output(response_text):
    """Displays the AI-generated text with a copy button."""
    st.markdown("""
    <div class="custom-card" style="background: #f9f9f9;">
        <h3 style="color: #fff;">✨ AI Response</h3>
    """, unsafe_allow_html=True)
    st.markdown(response_text, unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
    st.download_button("⬇️ Download Response", response_text, file_name="study_buddy_response.txt", use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

def display_explainer_tool():
    """Renders the UI for the 'Explain a Topic' tool."""
    st.subheader("Explain a Topic")
    with st.form("explainer_form"):
        topic = st.text_input("What topic do you want to understand?", placeholder="e.g., Photosynthesis, Python Dictionaries, The Cold War")
        style = st.selectbox("How should I explain it?", ["Like I'm 10 years old", "In a simple paragraph", "With detailed bullet points"])
        submit = st.form_submit_button("✨ Explain It!", use_container_width=True, type="primary")

    if submit and topic:
        user_prompt = f"Explain the topic: '{topic}' in the style of '{style}'."
        with st.spinner("Thinking... 🧠"):
            explanation = generate_ai_response(SYSTEM_PROMPTS["Explainer"], user_prompt)
            display_ai_output(explanation)
            # Save to history
            history_input = {"topic": topic, "style": style}
            add_to_history(st.session_state.username, "Explanation", history_input, explanation)
    elif submit:
        st.warning("Please enter a topic to explain.", icon="⚠️")

def display_summarizer_tool():
    """Renders the UI for the 'Summarize My Notes' tool."""
    st.subheader("Summarize My Notes")
    with st.form("summarizer_form"):
        notes = st.text_area("Paste your notes here:", height=250, placeholder="Paste a long article or your study notes...")
        length = st.selectbox("How long should the summary be?", ["A few key bullet points", "A short paragraph", "A detailed summary"])
        submit = st.form_submit_button("✨ Summarize It!", use_container_width=True, type="primary")

    if submit and notes:
        user_prompt = f"Summarize the following text into '{length}':\n\n{notes}"
        with st.spinner("Condensing your notes... ✍️"):
            summary = generate_ai_response(SYSTEM_PROMPTS["Summarizer"], user_prompt)
            display_ai_output(summary)
            # Save to history (don't save the full notes to DB to save space)
            history_input = {
                "summary_style": length,
                "original_length": f"{len(notes)} characters"
            }
            add_to_history(st.session_state.username, "Summary", history_input, summary)
    elif submit:
        st.warning("Please paste some notes to summarize.", icon="⚠️")

def display_quiz_tool():
    """Renders the UI for the 'Generate a Quiz' tool."""
    st.subheader("Generate a Quiz")
    with st.form("quiz_form"):
        topic_or_notes = st.text_area("What is the quiz about? (Enter a topic or paste notes)", height=200, placeholder="e.g., The Solar System, or paste your notes on cell biology here...")
        num_questions = st.slider("How many questions?", 3, 10, 5)
        submit = st.form_submit_button("✨ Create Quiz!", use_container_width=True, type="primary")

    if submit and topic_or_notes:
        user_prompt = f"Generate a quiz with {num_questions} multiple-choice questions based on the following information:\n\n{topic_or_notes}\n\nProvide an answer key at the very end, clearly separated from the questions."
        with st.spinner("Building your quiz... 📝"):
            quiz = generate_ai_response(SYSTEM_PROMPTS["Quizzer"], user_prompt)
            display_ai_output(quiz)
            # Save to history
            history_input = {
                "topic": topic_or_notes[:100] + '...' if len(topic_or_notes) > 100 else topic_or_notes,
                "questions": num_questions
            }
            add_to_history(st.session_state.username, "Quiz", history_input, quiz)
    elif submit:
        st.warning("Please provide a topic or notes for the quiz.", icon="⚠️")

def display_flashcard_tool():
    """Renders the UI for the 'Generate Flashcards' tool."""
    st.subheader("Generate Flashcards")
    with st.form("flashcard_form"):
        topic_or_notes = st.text_area("What are the flashcards about? (Enter a topic or paste notes)", height=200, placeholder="e.g., Key terms from Biology Chapter 5, or paste your notes here...")
        num_flashcards = st.slider("How many flashcards?", 3, 15, 5)
        submit = st.form_submit_button("✨ Create Flashcards!", use_container_width=True, type="primary")

    if submit and topic_or_notes:
        user_prompt = f"Generate {num_flashcards} flashcards from the following information. For each flashcard, provide a 'Term' and a 'Definition'.\n\nInformation:\n{topic_or_notes}"
        with st.spinner("Creating your flashcards... 🃏"):
            flashcards = generate_ai_response(SYSTEM_PROMPTS["Flashcard"], user_prompt)
            display_ai_output(flashcards)
            # Save to history
            history_input = {"topic": topic_or_notes[:100] + '...' if len(topic_or_notes) > 100 else topic_or_notes, "count": num_flashcards}
            add_to_history(st.session_state.username, "Flashcards", history_input, flashcards)
    elif submit:
        st.warning("Please provide a topic or notes for the flashcards.", icon="⚠️")

def display_history():
    """Renders the user's interaction history."""
    st.markdown('<div class="custom-card">', unsafe_allow_html=True)
    st.markdown('<h2 style="text-align: center; color: #fff;">Your Study History</h2>', unsafe_allow_html=True)
    user_data = users_collection.find_one({"_id": st.session_state.username})
    user_history = user_data.get("history", []) if user_data else []

    if not user_history:
        st.info("You have no saved interactions yet. Use a study tool to see your history here!", icon="📚")
    else:
        for i, entry in enumerate(user_history):
            expander_title = f"{entry['type']} from {entry['date']}"
            with st.expander(expander_title):
                st.markdown(f"**Interaction Type:** {entry['type']}")
                if isinstance(entry.get('input'), dict):
                    st.markdown("**Your Input:**")
                    for key, value in entry['input'].items():
                        st.caption(f"{key.replace('_', ' ').capitalize()}: {value}")
                elif entry.get('input'):
                     st.markdown(f"**Your Input:** {entry['input']}")

                st.markdown("---")
                st.markdown("**AI Response:**")
                st.markdown(entry["response"])
    st.markdown('</div>', unsafe_allow_html=True)

def display_modern_header():
    """Display modern header with gradient"""
    st.markdown("""
    <div class="header-container">
        <h1 style="margin:0; font-size: 3rem; font-weight: 700;">🎓 AI Study Buddy</h1>
        <p style="margin:0; font-size: 1.3rem; opacity: 0.9; margin-top: 0.5rem;">
        Your personal AI tutor for explaining, summarizing, and quizzing.
        </p>
    </div>
    """, unsafe_allow_html=True)

def display_modern_auth():
    """Display modern authentication in sidebar"""
    with st.sidebar:
        st.markdown("""
        <div style="text-align: center; margin-bottom: 2rem;">
            <h2 style="color: #667eea; margin: 0;">Study Buddy</h2>
            <p style="color: #666; margin: 0;">AI Tutor</p>
        </div>
        """, unsafe_allow_html=True)

        if not st.session_state.logged_in:
            tab1, tab2 = st.tabs(["🔐 Login", "📝 Register"])

            with tab1:
                username = st.text_input("Username", key="login_user")
                password = st.text_input("Password", type="password", key="login_pass")
                
                if st.button("Login", use_container_width=True):
                    if username and password:
                        user_data = users_collection.find_one({"_id": username})
                        if user_data and verify_password(user_data["password"], password):
                            st.session_state.logged_in = True
                            st.session_state.username = username
                            st.rerun()
                        else:
                            st.error("Invalid username or password")
                    else:
                        st.warning("Please enter username and password")

            with tab2:
                username = st.text_input("Username", key="reg_user")
                password = st.text_input("Password", type="password", key="reg_pass")
                confirm_password = st.text_input("Confirm Password", type="password", key="reg_confirm_pass")
                if st.button("Register", use_container_width=True):
                    if username and password:
                        if password == confirm_password:
                            if users_collection.find_one({"_id": username}):
                                st.error("Username already exists")
                            else:
                                users_collection.insert_one({
                                    "_id": username,
                                    "password": hash_password(password),
                                    "history": []
                                })
                                st.success("Registration successful! Please login.")
                        else:
                            st.error("Passwords do not match")
                    else:
                        st.warning("Please fill all fields")
        else:
            st.markdown(f"""
            <div class="custom-card" style="background: #f0f2f6;">
                <h4 style="color: #667eea; margin: 0;">Welcome back!</h4>
                <p style="margin: 0.5rem 0; color: #666;">{st.session_state.username}</p>
            </div>
            """, unsafe_allow_html=True)

            if st.button("Logout", use_container_width=True):
                st.session_state.logged_in = False
                st.session_state.username = ""
                st.rerun()

# --- Main App Interface ---
display_modern_header()

# --- Authentication UI ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""

display_modern_auth()

if not st.session_state.logged_in:
    st.markdown("""
    <div class="custom-card">
        <h2 style="text-align: center; color: #fff; margin-bottom: 2rem;">Welcome to Your AI Study Buddy! 👋</h2>
        <p style="text-align: center; font-size: 1.2rem; color: #666; line-height: 1.6;">
        Unlock your learning potential with AI-powered tools. Explain complex topics, summarize long notes, create quizzes, and generate flashcards instantly.
        </p>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("""
    <div class="info-message">
        <p style="margin: 0; font-size: 1.1rem;">
        👈 <strong>Get Started:</strong> Please login or register in the sidebar to begin!
        </p>
    </div>
    """, unsafe_allow_html=True)

# --- Main Application ---
if st.session_state.logged_in:
    # --- Main Application Tabs ---
    tool_tab, history_tab = st.tabs(["🧠 Study Tools", "📜 History"])

    with tool_tab:
        st.markdown('<div class="custom-card">', unsafe_allow_html=True)
        st.markdown('<h2 style="text-align: center; color: #fff;">What would you like to do today?</h2>', unsafe_allow_html=True)

        # --- Tool Selection in a more modern way ---
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔬 Explain a Topic", use_container_width=True):
                st.session_state.tool_choice = "Explain a Topic"
            if st.button("📝 Generate a Quiz", use_container_width=True):
                st.session_state.tool_choice = "Generate a Quiz"
        with col2:
            if st.button("✍️ Summarize Notes", use_container_width=True):
                st.session_state.tool_choice = "Summarize My Notes"
            if st.button("🃏 Create Flashcards", use_container_width=True):
                st.session_state.tool_choice = "Generate Flashcards"

        st.markdown('</div>', unsafe_allow_html=True)

        # --- Display the selected tool's UI in its own card ---
        if 'tool_choice' in st.session_state:
            st.markdown('<div class="custom-card">', unsafe_allow_html=True)
            if st.session_state.tool_choice == "Explain a Topic":
                display_explainer_tool()
            elif st.session_state.tool_choice == "Summarize My Notes":
                display_summarizer_tool()
            elif st.session_state.tool_choice == "Generate a Quiz":
                display_quiz_tool()
            elif st.session_state.tool_choice == "Generate Flashcards":
                display_flashcard_tool()
            st.markdown('</div>', unsafe_allow_html=True)

    with history_tab:
        display_history()
