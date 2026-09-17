from clipper.config import Config
from clipper.transcribe import transcribe


video = r"C:\Users\ASUS\Downloads\YTDown.com_YouTube_Take-Profit-Show-Cara-Gaji-UMR-Dapat-1-M_Media_cCrFMcKqS0M_001_1080p.mp4"

cfg = Config()

print("MODEL:", cfg.whisper_model)
print("DEVICE:", cfg.whisper_device)

result = transcribe(video, cfg)

print("=" * 60)
print("TEXT RESULT:")
print(result["text"])

print("=" * 60)
print("FIRST WORDS:")

for w in result["words"][:30]:
    print(
        w["start"],
        "-",
        w["end"],
        ":",
        w["word"]
    )