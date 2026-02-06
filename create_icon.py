from PIL import Image, ImageDraw

# Create a simple icon
img = Image.new('RGBA', (256, 256), (30, 30, 30, 255))
draw = ImageDraw.Draw(img)
# Draw a simple 'C' character
draw.arc((50, 50, 206, 206), 45, 315, fill=(0, 122, 204, 255), width=20)
img.save('icon.ico', format='ICO', sizes=[(256, 256)])
