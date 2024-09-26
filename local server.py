import os
import requests
import base64
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from dotenv import load_dotenv
import logging
from PIL import Image
import io

load_dotenv()

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.DEBUG)

LMSTUDIO_API_URL = "http://localhost:1234/v1/chat/completions"

SYSTEM_PROMPT = """You are an AI assistant with advanced vision capabilities. Analyze images and respond to queries about them with detailed, accurate, and insightful information. Focus on key elements, colors, composition, and notable features. Provide comprehensive answers drawing from your knowledge base."""

MAX_IMAGE_SIZE = (1024, 1024)  # Maximum dimensions for the image

def process_image(image_data):
    image_bytes = base64.b64decode(image_data)
    image = Image.open(io.BytesIO(image_bytes))
    
    if image.mode == 'RGBA':
        image = image.convert('RGB')
    
    if image.size[0] > MAX_IMAGE_SIZE[0] or image.size[1] > MAX_IMAGE_SIZE[1]:
        image.thumbnail(MAX_IMAGE_SIZE, Image.LANCZOS)
    
    buffered = io.BytesIO()
    image.save(buffered, format="JPEG", quality=95)
    return base64.b64encode(buffered.getvalue()).decode('utf-8')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    try:
        if not request.is_json:
            app.logger.error("Request data is not JSON")
            return jsonify({"error": "Request must be JSON"}), 400

        data = request.get_json()
        user_message = data.get('message', '').strip()
        image = data.get('image')
        conversation_history = data.get('conversation_history', [])

        app.logger.info(f"Received request. Message: {user_message}, Image: {'Yes' if image else 'No'}")

        if not conversation_history:
            conversation_history = [{"role": "system", "content": SYSTEM_PROMPT}]

        if image:
            try:
                processed_image = process_image(image)
                conversation_history.append({
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{processed_image}"}},
                        {"type": "text", "text": user_message or "Describe this image in detail."}
                    ]
                })
            except Exception as e:
                app.logger.error(f"Error processing image: {str(e)}")
                return jsonify({"error": f"Error processing image: {str(e)}"}), 400
        else:
            conversation_history.append({"role": "user", "content": user_message})

        # Limit conversation history to last 5 exchanges plus the system message
        if len(conversation_history) > 21:
            conversation_history = [conversation_history[0]] + conversation_history[-10:]

        headers = {"Content-Type": "application/json"}
        payload = {
            "messages": conversation_history,
            "temperature": 0.7,
            "max_tokens": 1000,
            "stream": False
        }

        app.logger.info(f"Sending request to LM Studio API. Payload: {payload}")
        response = requests.post(LMSTUDIO_API_URL, headers=headers, json=payload, timeout=60)

        if response.status_code == 200:
            app.logger.info(f"Received response from LM Studio API: {response.json()}")
            generated_text = response.json()['choices'][0]['message']['content']
            conversation_history.append({"role": "assistant", "content": generated_text})
            return jsonify({"output": generated_text.strip(), "conversation_history": conversation_history})
        else:
            app.logger.error(f"Error from LM Studio API. Status code: {response.status_code}, Response: {response.text}")
            return jsonify({"error": f"Failed to get response from the model. Status code: {response.status_code}"}), 500
    except requests.Timeout:
        app.logger.error("Request to LM Studio API timed out")
        return jsonify({"error": "Request to AI model timed out. Please try again."}), 504
    except Exception as e:
        app.logger.error(f"Unexpected error: {str(e)}")
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)