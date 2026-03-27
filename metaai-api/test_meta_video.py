from metaai_api import MetaAI
import json
import logging
import sys

# Configure logging to see progress
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)

# Extracted cookies from user input
cookies = {
    "datr": "bw-IaXiI_Pi1DIHlSMX3fa98",
    "abra_sess": "FrqF7evn5cwDFhIYDkxXVG5mbmlhWnptbFN3FuaWxZgNAA%3D%3D",
    "ecto_1_sess": "fec0fa5b-e17a-4386-b1d8-c28a49871b15.v1%3Av-TbR4prwMSv3daXwP08Va-5tJpcwt6ZIbNbgggs6TamrOCdOrM1fAt1b7qMnJmNBpLPQ20lrSqUqbqJd31dCaV8pqjqU99SbqKTlyVaBCSCmzUQdrMos9gjs1IMsX3KMgudHL2C3jVhcfEsdrq2irS8DNx0V0DvBTcISOKal3HHPY7-sEwdik8MU2uAfhOoWm_3rQ0j3rEsk0g0GcFxRB7xN2ge4M8dzK2yOLr-Oa_ASWYz5YNMq1h4bgsLtqkTREwGnvDTJiTBmkNMHrs6s7N47Lj1JYyXTIBAvJDCaCdowDM5f-kjcmmWRIfvfJngraGVv4ZjMW6senTNroEzm3eNKrGIFCzlTjs3_0YqWtGshzJBxCOXyC0z2Z1V-vYVLe_u9Morb6_mcEM6YvJN8oOTbrR5TKEJsemiGMsp0pwSSrwhOu2jNTt_sAO6j6PDuSPrIZ93voC7NPghHnpusFgXEjelz7X1Orx-HQXitEr0DJFIXCexkHsqFA-KiQqc%3AeCmVxr0vNO4-WbR9%3AwFtUKe4THWi3VvxYHgX6yQ.nwyvxYs9SMRiG1QX2k33y2FAo2FV-_wcbCWwG6G7BjA"
}

# Optional but provided cookies that might be helpful
cookies.update({
    "ps_l": "1",
    "wd": "1358x644",
    "dpr": "1",
    "ps_n": "1",
    "rd_challenge": "Q_6hBQMpRB5RfLPGO_007FOH4FyTK6Q_31prpb-ukj-wsm3CJk0Kt9c__YWVX4qTXoIJV1_5-ke6k19HbX8Wr2VxA8HvOA"
})

def main():
    print("Initializing MetaAI...")
    ai = MetaAI(cookies=cookies)
    
    prompt = "A beautiful sunset over the ocean with waves gently crashing on the shore"
    print(f"Generating video with prompt: '{prompt}'...")
    
    # generate_video_new is the recommended method in main.py
    try:
        result = ai.generate_video_new(prompt)
        
        if result["success"]:
            print("\n✅ Video generation initiated successfully!")
            print(f"Conversation ID: {result.get('conversation_id')}")
            
            video_urls = result.get("video_urls", [])
            if video_urls:
                print(f"Found {len(video_urls)} video(s):")
                for i, url in enumerate(video_urls, 1):
                    print(f"  {i}. {url}")
            else:
                print("No video URLs found in the initial response. Video might still be processing.")
                print(f"You can check progress at: https://www.meta.ai/prompt/{result.get('conversation_id')}")
                
            # Also try the older method if no URLs found, as it has built-in polling
            if not video_urls:
                print("\nRetrying with built-in polling method...")
                result_old = ai.generate_video(prompt)
                if result_old["success"]:
                    print(f"Video URLs: {result_old.get('video_urls')}")
        else:
            print("\n❌ Video generation failed.")
            print(f"Error: {result.get('error')}")
    except Exception as e:
        print(f"\n❌ Error: {e}")

if __name__ == "__main__":
    main()
