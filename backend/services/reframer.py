import os
import cv2
import logging
from typing import Tuple, Optional
import numpy as np

logger = logging.getLogger(__name__)

class VideoReframer:
    def __init__(self):
        # Load OpenCV face detector
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        self.face_cascade = cv2.CascadeClassifier(cascade_path)

    def detect_primary_face_x(
        self,
        video_path: str,
        start_time: float,
        end_time: float,
        samples: int = 8
    ) -> Optional[float]:
        """
        Samples frames between start_time and end_time, detects faces,
        and returns the normalized average center X coordinate [0.0 - 1.0].
        """
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return None

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
        height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)

        if width == 0 or height == 0:
            cap.release()
            return None

        face_centers_x = []
        sample_times = np.linspace(start_time, end_time, num=samples)

        for t in sample_times:
            frame_no = int(t * fps)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
            ret, frame = cap.read()
            if not ret or frame is None:
                continue

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            # Detect faces
            faces = self.face_cascade.detectMultiScale(
                gray, scaleFactor=1.2, minNeighbors=4, minSize=(60, 60)
            )
            if len(faces) > 0:
                # Pick the largest face in frame (the main speaker)
                largest_face = max(faces, key=lambda b: b[2] * b[3])
                fx, fy, fw, fh = largest_face
                center_x = (fx + fw / 2.0) / width
                face_centers_x.append(center_x)

        cap.release()

        if face_centers_x:
            # Return median for robustness against outliers
            return float(np.median(face_centers_x))
        return None

    def get_ffmpeg_filter(
        self,
        video_path: str,
        start_time: float,
        end_time: float,
        layout_mode: str = "smart_crop",
        target_aspect_ratio: str = "9:16"
    ) -> str:
        """
        Returns the FFmpeg video filter graph based on the chosen layout and target ratio.
        """
        if target_aspect_ratio == "16:9":
            return "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2"

        if target_aspect_ratio == "1:1":
            return "crop=ih:ih:(iw-ih)/2:0,scale=1080:1080"

        # Default: 9:16 (1080x1920) Shorts / Reels
        if layout_mode == "blurred_background":
            return (
                "split[v1][v2];"
                "[v1]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:5[bg];"
                "[v2]scale=1080:-1[fg];"
                "[bg][fg]overlay=(W-w)/2:(H-h)/2"
            )

        if layout_mode == "split_screen":
            # Stack top half and bottom half or dual crops
            return (
                "split[top][bot];"
                "[top]crop=iw/2:ih:0:0,scale=1080:960[t_scaled];"
                "[bot]crop=iw/2:ih:iw/2:0,scale=1080:960[b_scaled];"
                "[t_scaled][b_scaled]vstack"
            )

        # Smart Crop (Face Detection)
        cap = cv2.VideoCapture(video_path)
        orig_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 1920)
        orig_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 1080)
        cap.release()

        crop_w = int(orig_h * 9.0 / 16.0)

        # If already portrait, just scale
        if orig_w <= crop_w:
            return "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2"

        # Detect face center
        face_x = self.detect_primary_face_x(video_path, start_time, end_time)
        if face_x is not None:
            center_px = int(face_x * orig_w)
            x_offset = max(0, min(center_px - crop_w // 2, orig_w - crop_w))
        else:
            # Fallback to center crop
            x_offset = (orig_w - crop_w) // 2

        # Ensure x_offset is even for codecs
        if x_offset % 2 != 0:
            x_offset -= 1

        return f"crop={crop_w}:{orig_h}:{x_offset}:0,scale=1080:1920"
