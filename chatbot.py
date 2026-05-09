import os
from urllib import response
import streamlit as st
from faster_whisper import WhisperModel
from streamlit_mic_recorder import mic_recorder
from dotenv import load_dotenv
from email.message import EmailMessage
from ddgs import DDGS
import requests
from bs4 import BeautifulSoup
from google import genai  # NEW: Using the modern SDK
from google.genai import types # For tool definitions
import time
import tempfile

# Load environment variables from the .env file
# Using os.path.dirname(__file__) ensures the file is found even if you run the script from a different folder.
current_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(current_dir, "secret.env")
load_dotenv(dotenv_path=env_path)

model = WhisperModel("base", device="cpu", compute_type="int8")

if "user_prompt_val" not in st.session_state:
    st.session_state.user_prompt_val = ""

if "confirm" not in st.session_state:
    st.session_state.confirm = None


audio = mic_recorder(
    start_prompt="Start Recording",
    stop_prompt="Stop Recording",
    key='recorder'
)

if "state2" not in st.session_state:
    st.session_state.state2 = "Not approved"

# Fetch the Gemini key you set in the terminal.
#gemini_key = os.getenv("supergkey")

# back-up key
gemini_key = os.getenv("geminikey2")

instruction = "If you need to search and then use a tool, perform the search first, summarize it, and then call the tool in a separate step."

placeholder = "Enter your question here..."

client = genai.Client(api_key=gemini_key, http_options={"api_version": "v1alpha"})


tools_list = [{"google_search_retrieval": {"dynamic_retrieval_config": {"mode": "unspecified", "dynamic_threshold": 0.0}}}]


# define special functions before the chat session is made.

def confirm_action(title, description, *args, **kwargs):
    st.warning(f"⚠️ {title}, YOU ARE ABOUT TO PERFORM THIS ACTION! ⚠️")
    st.write(description)

    col1, col2 = st.columns(2)

    if col1.button("✅ Confirm", key=f"{title}_confirm"):
        st.session_state.confirm = True
        st.rerun()
    

    if col2.button("❌ Cancel", key=f"{title}_cancel"):
        st.info("Cancelled")
        st.session_state.confirm = False

        
    
    return st.session_state.confirm  # No decision yet

def send_the_email(receiver: str, subject: str, body: str):
    """
    Sends a real email via Make.com.
    Matches Make.com mapping: subject, text, recipients
    """
    webhook_url = os.getenv("email")  # Ensure this is set in your .env file
    
    if not webhook_url:
        return "Error: Webhook URL not found"

    # FIX 1: Fixed the spelling of 'recipients'
    # FIX 2: Sending 'receiver' as a string, not a list [receiver]
    payload = {
        "subject": subject,
        "text": body,
        "recipients": receiver  
    }




    
    try:
        response = requests.post(webhook_url, json=payload)
        st.session_state.confirm = None  # Reset confirmation state after action
        
        if response.status_code in [200, 204]:
            return f"Success: Real email successfully sent to {receiver}"
        else:
            return f"Error: {response.status_code} - {response.text}"
            
    except Exception as e:
        return f"System Error: {str(e)}"
    
   





def internet_search(query: str):
    """Searches the internet for information. 2026 Optimized & Free."""
    print(f"DEBUG: Agent is searching for: {query}")
    try:
        # We use the 'lite' backend which is much harder to block
        # and doesn't require JavaScript.
        with DDGS() as ddgs:
            results = ddgs.text(query, max_results=5, backend="lite")
            
            if not results:
                return "Search failed: No results found for this query."

            formatted_results = []
            for r in results:
                # We extract the title, link, and a snippet (body)
                title = r.get('title', 'No Title')
                link = r.get('href', 'No Link')
                snippet = r.get('body', 'No snippet available')
                formatted_results.append(f"TITLE: {title}\nLINK: {link}\nINFO: {snippet}\n---")
            
            return "\n".join(formatted_results)
            
    except Exception as e:
        return f"System Error during search: {e}"

def website_diver(url: str):
    """Scrapes the text content from a website URL. 
    Use this when the user asks for details from a specific link or website."""

    try:

        # Headers should be a dictionary, not a string from an env file
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Referer': 'https://www.google.com/',
            'DNT': '1',
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        for script in soup(["script", "style"]):
            script.extract()

        text = soup.get_text(separator=' ')
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        clean_text = '\n'.join(chunk for chunk in chunks if chunk)

        return clean_text[:5000]
    except Exception as e:
        return f"Error: {e}"



def send_discord_message(content: str):
    """Sends a message to Discord via Webhook. (use this only when user specifies discord)"""

    webhook_url = os.getenv("discord")

    data = {"username": "Godly Agent", "content": content}

    try:
        response = requests.post(webhook_url, json=data)
        if response.status_code == 204:
            return "Success: Message sent to Discord."
        else:
            return f"Error: {response.text}"
    except Exception as e:
        return f"Error: {e}"
    


        

    
    
# THE GOLDLY AGENT AND HIS TOOLS AKA. CHAT SESSION 🧠🔥🏆

if "chat_session" not in st.session_state:
    st.session_state.chat_session = client.chats.create(
    model="gemini-2.5-flash",
    config=types.GenerateContentConfig(
        tools=[internet_search, 
               website_diver,
                 send_discord_message, 
                 send_the_email
                 ],
        # We MUST use automatic function calling to handle the loops in ONE session
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=False),
        system_instruction="Search Google first, then use your tools to act on the info."
        
        )
)


def chat(prompt):
    response = st.session_state.chat_session.send_message(prompt)

    parts = response.candidates[0].content.parts
    result = response.text

    for part in parts:

        function_call = getattr(part, "function_call", None)

        if function_call is None:
            continue

        name = function_call.name
        args     = dict(function_call.args)

        if name in ["internet_search", "website_diver"]:
            result = globals()[name](**args)

        elif name in ["send_the_email", "send_discord_message"]:
            st.session_state.pending_action = {
    "name": name,
    "args": args
}

            return "Waiting for confirmation..."

    return result
    
    
st.set_page_config(page_title="Chatbot", page_icon=":robot:", layout="wide")


if "ai_memory" not in st.session_state:
    st.session_state.ai_memory = ""

st.title("Chatbot")
if "pending_action" in st.session_state:

    action = st.session_state.pending_action

    st.warning("⚠️ Confirm Action")

    st.write(action)

    col1, col2 = st.columns(2)

    if col1.button("✅ Confirm"):

        name = action["name"]
        args = action["args"]

        result = globals()[name](**args)

        st.success(result)

        del st.session_state.pending_action

        st.rerun()

    if col2.button("❌ Cancel"):

        st.info("Cancelled")

        del st.session_state.pending_action

        st.rerun()


if st.session_state.state2 == "Approved":

# 2. THE OUTPUT BOX
# We tell this box: "Your content is whatever is inside ai_memory"
    user_msg = st.text_area("Prompt area", placeholder="Enter message", height=200, value=st.session_state.user_prompt_val)

    with st.container(border=True):
        st.write("**AI Response:**")
        st.write(st.session_state.ai_memory)

    st.write("**© by Sidharth Gupta, 2026**")

# 4. THE BUTTONS
    col1, col2 = st.columns(2)

    with col1:
        if st.button("Speak"):
            if audio:
                audio_hash = hash(audio['bytes'])
    
                if "last_audio_hash" not in st.session_state or st.session_state.last_audio_hash != audio_hash:
                    with st.spinner("Writing down what you said..."):
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp_file:
                            tmp_file.write(audio['bytes'])
                            tmp_file_path = tmp_file.name

                        try:
                            segments, info = model.transcribe(tmp_file_path, beam_size=5)
                            transcript = " ".join([segment.text for segment in segments])
                
                # Update the state
                            st.session_state.user_prompt_val = transcript.strip()
                # Remember this recording so we don't transcribe it again in a loop
                            st.session_state.last_audio_hash = audio_hash
                
                            st.rerun()
                        finally:
                            if os.path.exists(tmp_file_path):
                                os.remove(tmp_file_path)
        
        
    with col2:
        if st.button("Send"):
            if user_msg:
                with st.spinner("Agent is thinking..."):
                # Call your chat function
                    response2 = chat(user_msg)
                
                # SAVE the result to the memory we linked above
                    st.session_state.ai_memory += f"User: {user_msg}\n\nAI: {response2}\n\n{'-'*50}\n\n"
                
                # REFRESH the page so the box at the top updates
                    st.rerun()





if st.session_state.state2 == "Not approved":
    pas = st.text_input("Enter Password", placeholder="Enter Secret Password")

    if st.button("Check"):
        if pas == "supersecret180315@outlook.com180315_202929":
            st.session_state.state2 = "Approved"
            st.rerun()
        else:
            st.error("Access Denied", icon="🚫")
            

        


