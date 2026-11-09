from faster_whisper import WhisperModel
from pathlib import Path


# Baby Dragon's local Whisper model
PROJECT_ROOT = Path(__file__).resolve().parent.parent

MODEL_FOLDER = (
    PROJECT_ROOT
    / "assets"
    / "whisper_model"
    / "models--Systran--faster-whisper-small"
    / "snapshots"
    / "536b0662742c02347bc0e980a01041f333bce120"
)


class SpeechToText:

    def __init__(self):
        self.model = WhisperModel(
            str(MODEL_FOLDER),
            device="cpu",
            compute_type="int8"
        )

    def transcribe(self, audio_file):
        segments, info = self.model.transcribe(
            audio_file,
            beam_size=5,
            vad_filter=True
        )

        text = " ".join(
            segment.text.strip()
            for segment in segments
        )

        return {
            "text": text,
            "language": info.language,
            "language_probability": info.language_probability
        }