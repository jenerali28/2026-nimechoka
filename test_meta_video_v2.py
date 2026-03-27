import sys
import os
import json
import logging

# Set up logging to see what's happening
logging.basicConfig(level=logging.INFO)

# Add the src directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.getcwd(), 'metaai-api/src')))

from metaai_api import VideoGenerator

# The cookie string provided by the user
cookie_string = "datr=bw-IaXiI_Pi1DIHlSMX3fa98;ecto_1_sess=fec0fa5b-e17a-4386-b1d8-c28a49871b15.v1%3ADb6pL9Uix23W1Ng9LMKG_qvjzpD7Xr8VsR6q-pFgdlrlu_qbBHL-SmiEYogk-BUYdYcP34ydkgpYeYYVVanK8ybk2uWVyx0Y8nON0yCe8QvdPEMEMj_Y1evzt-h53BoogZ74cdhK70y_K5tgHQv8z5s12bIqmEEczy17z_0uI6dWbE9N6E9stqHhgu5D8W-53TviKav1_WbjhMjg_2lCV5I3Xnfp_jMM92_w_zdrgIYgUfI6bOCts0-w6KdR0V6Ax_EAesv0r0dbJL2Zm-BX09MJ2hGuLi-pMXOHU_6_5v-cQwYsXiPD9mv3FjV2zqojYCK7J8-VKBDr40kmVdAybmBEVlnc3a1_t042N7aY-8L3HVxhf7rrhee-1RuyAcSeB2BZzUxb6rnSwF9fXvccsfqv9smWGRy7yx-qxFOCSFzPtwwgMJbeE9pCHZAfDyKAzbKxWF91ZQ4Ax6ruyS8Rayq0cXe4-qfOmy4HE9jHcUMd5N-ESxdpSren_TmWVo1d%3AlwtRJJj3geMYdtrA%3AagxWr4iAx-pHG_DCSQaozQ.FRCv5pQ-3NKwnv85mRXqcPuGWeWjq7hweS2vTT5npgI;ps_l=1;wd=1358x644;abra_sess=FrqF7evn5cwDFhIYDkxXVG5mbmlhWnptbFN3FuaWxZgNAA%3D%3D;dpr=1;ps_n=1;rd_challenge=Q_6hBQNY5mWo7vKO_VcYROgqz0jg6Ogdrya_1XMEBR3gvfMY_pUQcbO2-bNTTJmFu4RWuyVexBpDlnYCNKLqR5W3kEo"

# Test prompt
prompt = "A majestic lion walking through the African savanna at sunset"
print(f"Testing video generation with VideoGenerator class and prompt: {prompt}")

try:
    # Use quick_generate which handles token fetching and the multi-step process
    result = VideoGenerator.quick_generate(
        cookies_str=cookie_string,
        prompt=prompt,
        verbose=True
    )
    
    print(f"Full result: {json.dumps(result, indent=2)}")
    
    if result["success"]:
        print("✅ Video generated successfully!")
        print(f"   Conversation ID: {result.get('conversation_id')}")
        print(f"   Video URLs: {len(result.get('video_urls', []))}")
        for i, url in enumerate(result.get('video_urls', []), 1):
            print(f"   {i}. {url}")
    else:
        print("❌ Failed to generate video")
        if "error" in result:
            print(f"   Error: {result['error']}")
except Exception as e:
    print(f"❌ An error occurred: {e}")
    import traceback
    traceback.print_exc()
