from clipper.config import Config
from clipper.transcribe import transcribe
from clipper.score import score


video = r"C:\Users\ASUS\Downloads\YTDown.com_YouTube_Take-Profit-Show-Cara-Gaji-UMR-Dapat-1-M_Media_cCrFMcKqS0M_001_1080p.mp4"


cfg = Config()

print("=" * 60)
print("CONFIG")
print("Whisper :", cfg.whisper_model)
print("Ollama  :", cfg.model)
print("=" * 60)


print("Loading transcript...")
transcript = transcribe(video, cfg)

print(
    "Words:",
    len(transcript["words"])
)

print("=" * 60)
print("Sending transcript to Ollama...")
print("=" * 60)


clips = score(transcript, cfg)


print("=" * 60)
print("RESULT CLIPS")
print("=" * 60)


for i, clip in enumerate(clips, 1):
    print()
    print("CLIP", i)
    print("Start :", clip["start"])
    print("End   :", clip["end"])
    print("Title :", clip["title"])
    print("Hook  :", clip["hook"])
    print("Score :", clip["score"])