import os
import base64
from io import BytesIO
from together import Together
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class APIClient:
    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv("TOGETHER_API_KEY")
        if not self.api_key:
            raise ValueError("Together API Key is missing. Please set TOGETHER_API_KEY in .env or pass it to constructor.")
        
        self.client = Together(api_key=self.api_key)
        # Default model
        self.model = "meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8"

    def analyze_image(self, image, prompt="You are a code analysis interview assistant. Analyze the code and provide a solution or explanation. concisely."):
        """
                
        Args:
            image: PIL Image object.
            prompt: Text prompt for the AI.
            
        Returns:
            String response from the AI.
        """
        try:
            # Convert PIL image to base64
            buffered = BytesIO()
            image.save(buffered, format="PNG")
            img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
            
            # Construct the messages payload
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{img_str}"
                            },
                        },
                    ],
                }
            ]

            stream = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=True,
            )

            # Accumulate the response
            response_text = ""
            for chunk in stream:
                if hasattr(chunk, 'choices') and chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    if delta and delta.content:
                        response_text += delta.content
            
            return response_text

        except Exception as e:
            return f"Error analyzing image: {str(e)}"

    def send_text_prompt(self, prompt):
        """
        Send a text-only prompt to the LLM without an image.
        
        Args:
            prompt: Text prompt for the AI.
            
        Returns:
            String response from the AI.
        """
        try:
            # Construct the messages payload
            messages = [
                {
                    "role": "user",
                    "content": prompt + "concisely.",
                }
            ]

            stream = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=True,
            )

            # Accumulate the response
            response_text = ""
            for chunk in stream:
                if hasattr(chunk, 'choices') and chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    if delta and delta.content:
                        response_text += delta.content
            
            return response_text

        except Exception as e:
            return f"Error sending prompt: {str(e)}"

if __name__ == "__main__":
    # Simple test (requires valid key and an image)
    try:
        from PIL import Image
        client = APIClient()
        print("API Client initialized successfully.")
    except Exception as e:
        print(f"Initialization failed: {e}")
