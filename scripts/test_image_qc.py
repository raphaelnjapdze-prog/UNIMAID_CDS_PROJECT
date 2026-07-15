from PIL import Image
from utils.image_quality_control import assess_image_quality

img = Image.open("path/to/your/specimen.jpg")
report = assess_image_quality(img)
print("Passed:", report["passed"])
print("Reason:", report["reason"])
# To save the processed image if you want to inspect enhancement:
if report["processed_image"] is not None:
    report["processed_image"].save("processed_specimen.jpg")