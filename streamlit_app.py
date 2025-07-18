import streamlit as st
import uuid
import json
import requests
from datetime import datetime
from openai import OpenAI
import time

# Config 2.0
# --- CONFIG ---
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
DROPBOX_FOLDER = "/transcripts"

APP_KEY = st.secrets["DROPBOX_APP_KEY"]
APP_SECRET = st.secrets["DROPBOX_APP_SECRET"]
REFRESH_TOKEN = st.secrets["DROPBOX_REFRESH_TOKEN"]

# --- TOKEN REFRESH ---
def get_fresh_dropbox_token():
    response = requests.post(
        "https://api.dropboxapi.com/oauth2/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": REFRESH_TOKEN
        },
        auth=(APP_KEY, APP_SECRET)
    )
    response.raise_for_status()
    return response.json()["access_token"]

# --- GET ACCESS TOKEN ---
DROPBOX_TOKEN = get_fresh_dropbox_token()

#Old Config, Revert to if needed but just static token
# --- CONFIG ---
#client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
#DROPBOX_TOKEN = st.secrets["DROPBOX_TOKEN"]

TOPICS = [
    "Problem Solving",
    "Leadership",
    "Strategic Thinking",
    "Work Ethic",
    "Communication"
]

BASE_PROMPTS = {
    "Problem Solving": "Tell me about a time you were faced with a complex or unfamiliar problem. How did you approach solving it, and what was the result?",
    "Leadership": "Describe a situation where you took initiative or led a group, even if it wasn’t in a formal leadership role. What was the outcome?",
    "Strategic Thinking": "Tell me about a time you had to make a decision that required thinking beyond the immediate task. How did you consider the bigger picture?",
    "Work Ethic": "Give an example of a time you had to push through a difficult challenge or long hours to get something done. What motivated you?",
    "Communication": "Tell me about a time when you had to explain something complex to someone with less knowledge of the topic. How did you do it?"
}

# --- CHECK INTERVIEW LIMIT ---
def has_reached_limit():
    headers = {
        "Authorization": f"Bearer {DROPBOX_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {
        "path": "/interview_transcripts"
    }
    response = requests.post("https://api.dropboxapi.com/2/files/list_folder", headers=headers, json=data)
    if response.status_code == 200:
        entries = response.json().get("entries", [])
        transcript_files = [f for f in entries if f['.tag'] == 'file' and f['name'].startswith("transcript_")]
        return len(transcript_files) >= 10000
    else:
        st.error("Unable to verify interview count from Dropbox.")
        return True

if has_reached_limit():
    st.title("Interview Limit Reached")
    st.error("The application has reached its maximum of 10,000 interviews and is now shut down.")
    st.stop()

# --- SESSION STATE ---
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
    st.session_state.topic_index = 0
    st.session_state.messages = {topic: [] for topic in TOPICS}
    st.session_state.force_next_prompt = False
    st.session_state.awaiting_reply = False
    st.session_state.last_user_input = ""

current_topic = TOPICS[st.session_state.topic_index]

# --- GPT UTILITY ---
def chat_with_gpt(topic_history, topic):
    messages = [{"role": "system", "content": f"You are an interview bot assessing a candidate's {topic} skills. Ask thoughtful, follow-up questions, and when you're satisfied, say 'Thank you, let's move on.'"}]
    messages += topic_history
    response = client.chat.completions.create(
        model="gpt-4",
        messages=messages,
        temperature=0.7
    )
    return response.choices[0].message.content

# --- DROPBOX UPLOAD ---
def upload_to_dropbox(json_data, filename="transcript.json"):
    DROPBOX_TOKEN=get_fresh_dropbox_token()
    dropbox_path = f"/interview_transcripts/{filename}"
    headers = {
        "Authorization": f"Bearer {DROPBOX_TOKEN}",
        "Content-Type": "application/octet-stream",
        "Dropbox-API-Arg": json.dumps({
            "path": dropbox_path,
            "mode": "add",
            "autorename": True,
            "mute": False
        })
    }
    response = requests.post(
        "https://content.dropboxapi.com/2/files/upload",
        headers=headers,
        data=json.dumps(json_data).encode("utf-8")
    )
    return response.status_code == 200

# --- RENDER CHAT ---
st.title("AI Interview Screener")
st.write(f"### Topic: {current_topic}")

for msg in st.session_state.messages[current_topic]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# --- INITIAL PROMPT ---
if not st.session_state.messages[current_topic]:
    initial_prompt = BASE_PROMPTS[current_topic]
    st.session_state.messages[current_topic].append({"role": "assistant", "content": initial_prompt})
    st.rerun()

# --- HANDLE GPT RESPONSE ---
if st.session_state.awaiting_reply and st.session_state.last_user_input:
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            reply = chat_with_gpt(st.session_state.messages[current_topic], current_topic)
    st.session_state.messages[current_topic].append({"role": "assistant", "content": reply})
    st.session_state.awaiting_reply = False
    st.session_state.last_user_input = ""

    if "let's move on" in reply.lower():
        st.session_state.topic_index += 1
        if st.session_state.topic_index >= len(TOPICS):
            filename = f"transcript_{st.session_state.session_id}.json"
            data = {
                "session_id": st.session_state.session_id,
                "timestamp": datetime.utcnow().isoformat(),
                "transcript": st.session_state.messages
            }
            if upload_to_dropbox(data, filename):
                st.success("Interview complete. Transcript saved to Dropbox. Thank you!")
            else:
                st.error("Interview complete, but failed to save transcript to Dropbox.")
            st.stop()
        else:
            next_topic = TOPICS[st.session_state.topic_index]
            st.session_state.messages[next_topic].append({"role": "assistant", "content": BASE_PROMPTS[next_topic]})
    st.rerun()

# --- CHAT INPUT ---
user_input = st.chat_input("Your response")

if user_input:
    st.session_state.messages[current_topic].append({"role": "user", "content": user_input})
    st.session_state.last_user_input = user_input
    st.session_state.awaiting_reply = True
    st.rerun()
