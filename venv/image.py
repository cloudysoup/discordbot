from PIL import Image
import google.generativeai as genai
import requests
from io import BytesIO

# Configure the API key
genai.configure(api_key="AIzaSyD0SWihqcTCevwQxzvZXUggcG_tnPBBI6Q")

# Create an image URL
image_url = 'https://media.discordapp.net/attachments/1266915114322231330/1337309415367376896/image.png?ex=67a7a2b2&is=67a65132&hm=d77e7c2af072265616ff9c2e66282c40c0542717a6f13ab140e8ad23b97a0650&format=webp&quality=lossless'

# Download and open the image
response = requests.get(image_url)
image = Image.open(BytesIO(response.content))

# Initialize the model and generate content
model = genai.GenerativeModel('gemini-2.0-flash')
config={
    'response_mime_type': 'application/json',
    'response_schema': list[str],
},
response = model.generate_content(
    ["Parse the usernames from this video game image. Return results as an array of strings", 
    image]
)

print(response.text)