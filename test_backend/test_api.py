# # FaceFinderW/test_backend/test_api.py

# import requests

# url = "http://127.0.0.1:8000/detect-faces-image/"
# file_path = "test_backend/test_face.jpg"

# with open(file_path, "rb") as f:
#     response = requests.post(url, files={"file": f})

# # Save the response as an image
# with open("output.png", "wb") as out_file:
#     out_file.write(response.content)

# print("Annotated image saved as output.png")

import requests

url = "http://127.0.0.1:8000/api/search"

files = {
    "reference": open("reference.jpg", "rb"),
    "zipfile": open("dataset_photos.zip", "rb")
}

data = {
    "threshold": 0.6,  # similarity threshold, adjust if needed
    "mode": "individually"  # can also use "together"
}

response = requests.post(url, files=files, data=data)
matches = response.json()["matches"]

for m in matches:
    print(f"Found in {m['filename']} → score: {m['score']:.2f}, saved: {m['saved_path']}")
