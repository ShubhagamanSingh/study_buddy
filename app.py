import streamlit as st # type: ignore
from huggingface_hub import InferenceClient # type: ignore
from pymongo import MongoClient # type: ignore
import hashlib
from datetime import datetime

# --- Configuration ---
st.set_page_config(
    page_title="Study Buddy",
    page_icon="🎓",
    layout="wide"
)

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
    except Exception as e:
        st.error(f"An error occurred while communicating with the AI model: {e}", icon="💔")
        return "Sorry, I couldn't generate a response at this moment. Please try again later."

    return response_text.strip()

def display_ai_output(response_text):
    """Displays the AI-generated text with a copy button."""
    st.markdown("---")
    st.subheader("✨ AI Response")
    st.markdown(response_text)
    st.code(response_text, language="markdown")

def display_explainer_tool():
    """Renders the UI for the 'Explain a Topic' tool."""
    st.subheader("Explain a Topic")
    with st.form("explainer_form"):
        topic = st.text_input("What topic do you want to understand?", placeholder="e.g., Photosynthesis, Python Dictionaries, The Cold War")
        style = st.selectbox("How should I explain it?", ["Like I'm 10 years old", "In a simple paragraph", "With detailed bullet points"])
        submit = st.form_submit_button("✨ Explain It!", use_container_width=True)

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
        submit = st.form_submit_button("✨ Summarize It!", use_container_width=True)

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
        submit = st.form_submit_button("✨ Create Quiz!", use_container_width=True)

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
        submit = st.form_submit_button("✨ Create Flashcards!", use_container_width=True)

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
    st.header("Your Study History")
    user_data = users_collection.find_one({"_id": st.session_state.username})
    user_history = user_data.get("history", []) if user_data else []

    if not user_history:
        st.info("You have no saved interactions yet. Use a study tool to see your history here!")
    else:
        for i, entry in enumerate(user_history):
            expander_title = f"{entry['type']} from {entry['date']}"
            with st.expander(expander_title):
                st.write(f"**Interaction Type:** {entry['type']}")
                if isinstance(entry.get('input'), dict):
                    st.write("**Your Input:**")
                    for key, value in entry['input'].items():
                        st.caption(f"{key.replace('_', ' ').capitalize()}: {value}")
                elif entry.get('input'):
                     st.write(f"**Your Input:** {entry['input']}")

                st.markdown("---")
                st.write("**AI Response:**")
                st.markdown(entry["response"])

# --- Main App Interface ---
st.title("🎓 Study Buddy")

# --- Authentication UI ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""

if not st.session_state.logged_in:
    st.sidebar.title("Login / Register")
    choice = st.sidebar.radio("Choose an action", ["Login", "Register"])

    username = st.sidebar.text_input("Username")
    password = st.sidebar.text_input("Password", type="password")

    if choice == "Register":
        if st.sidebar.button("Register"):
            if username and password:
                # Check if user already exists
                if users_collection.find_one({"_id": username}):
                    st.sidebar.error("Username already exists.")
                else:
                    users_collection.insert_one({
                        "_id": username,
                        "password": hash_password(password),
                        "history": []
                    })
                    st.sidebar.success("Registration successful! Please log in.")
            else:
                st.sidebar.warning("Please enter a username and password.")

    if choice == "Login":
        if st.sidebar.button("Login"):
            if username and password:
                user_data = users_collection.find_one({"_id": username})
                if user_data and verify_password(user_data["password"], password):
                    st.session_state.logged_in = True
                    st.session_state.username = username
                    st.rerun() # Rerun the script to show the main app
                else:
                    st.sidebar.error("Invalid username or password.")
            else:
                st.sidebar.warning("Please enter your username and password.")

    st.info("Please log in or register to use your Study Buddy. Open the sidebar by clicking the top-left icon.", icon="👈")

# --- Main Application ---
if st.session_state.logged_in:
    st.sidebar.title(f"Welcome, {st.session_state.username}! 👋")
    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.rerun()

    # --- Main Application Tabs ---
    tool_tab, history_tab = st.tabs(["🧠 Study Tools", "📜 History"])

    with tool_tab:
        st.header("What would you like to do today?")

        # --- Tool Selection ---
        tool_choice = st.radio(
            "Select a tool:",
            ["Explain a Topic", "Summarize My Notes", "Generate a Quiz", "Generate Flashcards"],
            horizontal=True,
            label_visibility="collapsed"
        )

        # --- Display the selected tool's UI ---
        if tool_choice == "Explain a Topic":
            display_explainer_tool()
        elif tool_choice == "Summarize My Notes":
            display_summarizer_tool()
        elif tool_choice == "Generate a Quiz":
            display_quiz_tool()
        elif tool_choice == "Generate Flashcards":
            display_flashcard_tool()

    with history_tab:
        display_history()
