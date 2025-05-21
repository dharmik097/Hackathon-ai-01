from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import json
import requests
import random
import re
import uuid
import os
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Get API key from environment variable
HF_API_TOKEN = os.getenv("HUGGING_FACE_API_TOKEN")
if not HF_API_TOKEN:
    print("WARNING: No Hugging Face API token found. Set the HUGGING_FACE_API_TOKEN environment variable.")

# In-memory storage (for prototype)
knowledge_base = []
conversations = {}
analytics = {
    "total_queries": 0,
    "ai_resolved": 0,
    "human_resolved": 0,
    "learning_events": 0
}

# Sample knowledge for demo
sample_knowledge = [
    {
        "question": "How do I reset my password?",
        "answer": "To reset your password, click on the 'Forgot Password' link on the login page and follow the instructions sent to your email.",
        "timestamp": datetime.now().strftime("%Y-%m-%d")
    },
    {
        "question": "What payment methods do you accept?",
        "answer": "We accept Visa, Mastercard, American Express, and PayPal as payment methods.",
        "timestamp": datetime.now().strftime("%Y-%m-%d")
    },
    {
        "question": "How can I track my order?",
        "answer": "You can track your order by logging into your account and visiting the 'Order History' section, or by using the tracking number sent in your shipping confirmation email.",
        "timestamp": datetime.now().strftime("%Y-%m-%d")
    }
]

# Add sample knowledge
knowledge_base.extend(sample_knowledge)

# Hugging Face API endpoint
HF_API_URL = "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.2"

def get_ai_response(messages):
    """Get response from Hugging Face model"""
    # Format conversation for the model
    prompt = "You are a helpful customer support assistant.\n\n"
    
    for msg in messages:
        role = msg.get('role', '')
        content = msg.get('content', '')
        if role == 'user':
            prompt += f"User: {content}\n"
        elif role == 'assistant':
            prompt += f"Assistant: {content}\n"
    
    prompt += "Assistant: "
    
    headers = {"Authorization": f"Bearer {HF_API_TOKEN}"}
    payload = {"inputs": prompt, "parameters": {"max_length": 150}}
    
    try:
        response = requests.post(HF_API_URL, headers=headers, json=payload)
        result = response.json()
        
        # Extract generated text
        if isinstance(result, list) and len(result) > 0:
            generated_text = result[0].get('generated_text', '')
            # Extract only the assistant's response
            assistant_response = generated_text.split("Assistant: ")[-1].strip()
            return assistant_response
        else:
            return "I'm having trouble processing your request."
    except Exception as e:
        print(f"Error calling Hugging Face API: {e}")
        return "I'm having trouble connecting to my brain right now."

@app.route('/')
def index():
    """Serve the main HTML page"""
    return render_template('index.html')

@app.route('/api/session', methods=['GET'])
def create_session():
    """Create a new session ID"""
    session_id = str(uuid.uuid4())
    conversations[session_id] = []
    return jsonify({"sessionId": session_id})

@app.route('/api/chat', methods=['POST'])
def chat():
    """Handle chat messages from users"""
    data = request.json
    message = data.get('message', '')
    session_id = data.get('sessionId', 'default')
    
    # Initialize conversation if new
    if session_id not in conversations:
        conversations[session_id] = []
    
    # Add user message to conversation
    conversations[session_id].append({"role": "user", "content": message})
    
    # Update analytics
    analytics["total_queries"] += 1
    
    # Check knowledge base for similar questions
    known_solution = find_similar_question(message, knowledge_base)
    
    if known_solution:
        # Use known solution from knowledge base
        answer = known_solution["answer"]
        conversations[session_id].append({"role": "assistant", "content": answer})
        
        # Update analytics
        analytics["ai_resolved"] += 1
        
        return jsonify({"response": answer, "confidence": 0.9})
    
    # Get AI response
    ai_response = get_ai_response(conversations[session_id])
    
    # Calculate confidence (simplified for prototype)
    confidence = calculate_confidence(message, ai_response)
    
    # Add to conversation history
    conversations[session_id].append({"role": "assistant", "content": ai_response})
    
    # Determine if human help is needed
    if confidence < 0.5:
        return jsonify({
            "response": "I'm not confident in my answer. Let me connect you with a human agent who can help better.",
            "needsHuman": True,
            "confidence": confidence
        })
    
    # Update analytics for AI resolution
    analytics["ai_resolved"] += 1
    
    return jsonify({"response": ai_response, "confidence": confidence})

@app.route('/api/tickets', methods=['GET'])
def get_tickets():
    """Get all tickets that need human assistance"""
    tickets = []
    for session_id, convo in conversations.items():
        if len(convo) >= 2:
            last_message = convo[-1]
            if last_message["role"] == "assistant" and "human agent" in last_message["content"]:
                tickets.append({
                    "sessionId": session_id,
                    "conversation": convo
                })
    
    return jsonify({"tickets": tickets})

@app.route('/api/human-response', methods=['POST'])
def human_response():
    """Handle human agent responses to tickets"""
    data = request.json
    session_id = data.get('sessionId', 'default')
    question = data.get('question', '')
    answer = data.get('answer', '')
    
    if session_id not in conversations:
        return jsonify({"success": False, "error": "Session not found"})
    
    conversation = conversations[session_id]
    
    # Find the user message index
    user_msg_index = -1
    for i, msg in enumerate(conversation):
        if msg["role"] == "user" and msg["content"] == question:
            user_msg_index = i
            break
    
    # Get AI's answer if available
    ai_answer = ""
    if user_msg_index >= 0 and user_msg_index + 1 < len(conversation):
        ai_answer = conversation[user_msg_index + 1]["content"]
    
    # Learn from human response
    learned = learn_from_human_response(question, ai_answer, answer)
    
    # Update conversation with human answer
    if user_msg_index >= 0 and user_msg_index + 1 < len(conversation):
        conversation[user_msg_index + 1] = {"role": "assistant", "content": answer}
    else:
        conversation.append({"role": "assistant", "content": answer})
    
    # Update analytics
    analytics["human_resolved"] += 1
    if learned:
        analytics["learning_events"] += 1
    
    return jsonify({"success": True, "learned": learned})

@app.route('/api/analytics', methods=['GET'])
def get_analytics():
    """Get system analytics"""
    return jsonify(analytics)

def find_similar_question(query, kb):
    """Find similar questions in knowledge base"""
    for item in kb:
        similarity = calculate_similarity(query, item["question"])
        if similarity > 0.7:  # High similarity threshold
            return item
    return None

def calculate_similarity(str1, str2):
    """Calculate better similarity between two strings"""
    # Convert to lowercase and split into words
    words1 = set(re.findall(r'\w+', str1.lower()))
    words2 = set(re.findall(r'\w+', str2.lower()))
    
    if not words1 or not words2:
        return 0
    
    # Remove common stop words
    stop_words = {'a', 'an', 'the', 'and', 'or', 'but', 'is', 'are', 'was', 'were', 
                 'in', 'on', 'at', 'to', 'for', 'with', 'by', 'about', 'like', 'from'}
    
    words1 = words1.difference(stop_words)
    words2 = words2.difference(stop_words)
    
    # Calculate Jaccard similarity
    intersection = len(words1.intersection(words2))
    union = len(words1.union(words2))
    
    if union == 0:
        return 0
        
    return intersection / union

def calculate_confidence(query, response):
    """Calculate confidence score"""
    # Check if similar question exists in knowledge base
    for item in knowledge_base:
        similarity = calculate_similarity(query, item["question"])
        if similarity > 0.8:
            return 0.95  # High confidence
        elif similarity > 0.5:
            return 0.7  # Medium confidence
    
    # Check response length - very short responses might indicate confusion
    if len(response) < 20:
        return 0.3
    
    # Random confidence for demo (between 0.2 and 0.7)
    return random.uniform(0.2, 0.7)

def learn_from_human_response(question, ai_answer, human_answer):
    """Learn from human responses"""
    # Compare AI and human answers
    similarity = calculate_similarity(ai_answer, human_answer)
    
    # If answers are different enough, add to knowledge base
    if similarity < 0.7:
        knowledge_base.append({
            "question": question,
            "answer": human_answer,
            "ai_answer": ai_answer,
            "timestamp": datetime.now().strftime("%Y-%m-%d")
        })
        print(f"Learned new solution for: '{question}'")
        return True
    return False

if __name__ == '__main__':
    app.run(debug=True, port=5000)