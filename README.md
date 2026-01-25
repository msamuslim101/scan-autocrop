# Intelligent Scan Auto-Crop Pipeline

A practical, production-focused project to automatically crop scanned images using **classical computer vision**.

This project focuses on **reliability, determinism, and scalability**, inspired by professional archival tools.

---

## 🎯 Project Goal

To build a **robust batch image cropping system** that:

- Works on scanned photos & documents
- Handles uneven lighting and borders
- Avoids cutting faces or important content
- Works without GPU or heavy AI models
- Can be safely used in automation pipelines

---

## ❌ What This Project Does NOT Do

- ❌ No AI guessing or hallucination
- ❌ No vision LLM dependency
- ❌ No "magic" black-box cropping
- ❌ No heavy GPU usage

This is a **deterministic system** relying on proven computer vision techniques.

---

## ✅ What This Project Does

✔ Uses OpenCV-based image processing  
✔ Detects only the **outermost boundary**  
✔ Ignores internal image content  
✔ Works on batch-scanned images  
✔ Uses fallback logic for safety  

---

## 🧠 Core Insight

> **Do not detect the photo.  
> Detect the background.**

This is the standard principle used in professional document digitization pipelines.

---

## 🛠 Core Technique

### 1. Preprocessing
- Grayscale conversion
- Gaussian blur to reduce scanner noise

### 2. Smart Thresholding
- **Otsu's Binarization**: Automatically calculates the optimal threshold value to separate the foreground (photo) from the background (scanner bed).

### 3. Structural Cleanup
- **Morphological Operations**: Uses closing and dilation to fill small gaps and solidify the detected regions.

### 4. Contour Detection
- `RETR_EXTERNAL`: Specifically retrieves only the extreme outer contours, ignoring any internal details like faces or text within the photo.

### 5. Safe Cropping Logic
- Largest contour selection
- Aspect ratio validation
- Bounding-box fallback if the contour is irregular

---

## 🧯 Safety & Reliability

This pipeline uses **multi-level fallback logic**:

1. **Primary**: Try external contour crop (Exact shape)
2. **Fallback**: If unstable, switch to bounding-box crop (Rectangular safety)
3. **Fail-safe**: If still unsafe, keep original image (Zero data loss)

This guarantees no accidental cropping of important details.

---

## 📚 Credits & Acknowledgements

This project relies on standard open-source libraries:

- **[OpenCV](https://opencv.org/)**: For all image processing and computer vision tasks.
- **[NumPy](https://numpy.org/)**: For high-performance matrix and array operations.

Logic and methods used (Otsu's Thresholding, Canny Edge Detection) are standard algorithms in the field of Computer Vision.

---

## 📜 License

MIT — free to use, modify, and improve.
