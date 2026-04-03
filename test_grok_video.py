import requests
import json
import time
import os

def test_grok_video():
    url = "http://localhost:8000/v1/chat/completions"
    
    payload = {
        "model": "grok-imagine-1.0-video",
        "messages": [
            {
                "role": "user",
                "content": "A simple stick figure running fast in a white void, cinematic lighting, 4k"
            }
        ],
        "video": {
            "aspect_ratio": "16:9"
        }
    }
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer grok2api" # Default app_key from config.toml
    }
    
    print(f"Sending request to {url}...")
    try:
        # Enable streaming
        response = requests.post(url, headers=headers, json=payload, timeout=600, stream=True)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code != 200:
            print(f"Error: {response.text}")
            return

        print("Receiving stream...")
        for line in response.iter_lines():
            if line:
                line_text = line.decode('utf-8')
                if line_text.startswith('data: '):
                    data_str = line_text[6:]
                    if data_str == '[DONE]':
                        print("\n[DONE]")
                        break
                    try:
                        data = json.loads(data_str)
                        if 'choices' in data and len(data['choices']) > 0:
                            delta = data['choices'][0].get('delta', {})
                            content = delta.get('content', '')
                            if content:
                                print(content, end='', flush=True)
                    except json.JSONDecodeError:
                        pass
        print("\nStream finished.")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    # Wait a bit for the server to fully start
    print("Waiting for server to initialize...")
    time.sleep(5)
    test_grok_video()
