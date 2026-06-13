"""Assemble browser recording JPG frames into an MP4 video."""
import os
import glob
import sys

try:
    import imageio.v3 as iio
except ImportError:
    os.system(f"{sys.executable} -m pip install imageio[pyav]")
    import imageio.v3 as iio

from PIL import Image
import numpy as np

frames_dir = r"C:\Users\shank\.gemini\antigravity-ide\browser_recordings\240afbe9-cbef-4d05-b49e-6f994ddee7e7"
output_path = r"d:\Paradox-vidyabot\docs\vidyabot_demo.mp4"

# Get all JPG frames sorted by timestamp
all_frame_files = sorted(glob.glob(os.path.join(frames_dir, "*.jpg")))
frame_files = []
for f in all_frame_files:
    try:
        t = int(os.path.splitext(os.path.basename(f))[0])
        if 1781376320 * 1e9 <= t <= 1781376460 * 1e9:
            frame_files.append(f)
    except ValueError:
        continue

print(f"Found {len(frame_files)} frames in target range")

if not frame_files:
    print("No frames found in target range!")
    sys.exit(1)

# Calculate FPS from timestamps (nanosecond timestamps in filenames)
timestamps = [int(os.path.splitext(os.path.basename(f))[0]) for f in frame_files]
if len(timestamps) > 1:
    deltas = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]
    avg_delta_ns = sum(deltas) / len(deltas)
    fps = min(30, max(1, round(1e9 / avg_delta_ns)))
else:
    fps = 10

total_duration = (timestamps[-1] - timestamps[0]) / 1e9 if len(timestamps) > 1 else 0
print(f"Duration: {total_duration:.1f}s, FPS: {fps}")

# Sample frames if needed, but since we have 1056 frames, we can write them all or sample them.
# Let's keep them all for high quality, or sample if the video is too long.
# At ~8 FPS, 1056 frames is ~133s which is fine. Let's write them all (step=1).
step = 1
selected_files = frame_files[::step]
print(f"Using {len(selected_files)} frames (step={step})")

# Read first frame to get dimensions
first = Image.open(selected_files[0]).convert("RGB")
w, h = first.size
# Ensure dimensions are even (required by h264)
w = w - (w % 2)
h = h - (h % 2)
print(f"Output size: {w}x{h}")

print("Writing MP4...")
with iio.imopen(output_path, "w", plugin="pyav") as writer:
    writer.init_video_stream("libx264", fps=fps)
    for i, fpath in enumerate(selected_files):
        frame = Image.open(fpath).convert("RGB").resize((w, h), Image.LANCZOS)
        writer.write_frame(np.array(frame))
        if (i + 1) % 100 == 0:
            print(f"  {i+1}/{len(selected_files)} frames written...")

file_size = os.path.getsize(output_path)
print(f"\nDone! Output: {output_path}")
print(f"Size: {file_size / 1024 / 1024:.1f} MB")
print(f"Duration: ~{len(selected_files) / fps:.1f}s at {fps} FPS")
