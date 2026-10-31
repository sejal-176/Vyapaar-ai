import cv2, pytesseract, fastapi, sqlalchemy, pandas, numpy
from PIL import Image, ImageDraw

img = Image.new("RGB", (500, 120), "white")
ImageDraw.Draw(img).text((20, 40), "Paid Rs 250 UTR 123456789012", fill="black")
img.save("ocr_test.png")

text = pytesseract.image_to_string(cv2.imread("ocr_test.png"))
print("OCR output:", text.strip())
print("OpenCV:", cv2.__version__)
print("All imports OK")