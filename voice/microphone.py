import sounddevice as sd
import soundfile as sf
from pathlib import Path
import tempfile


class MicrophoneRecorder:

    def __init__(self, sample_rate=16000):
        self.sample_rate = sample_rate

    def record(self, duration=5):
        """
        Records audio only when this method is explicitly called.
        """
        print("Microphone active. Speak now!")

        audio = sd.rec(
            int(duration * self.sample_rate),
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32"
        )

        sd.wait()

        print("Recording complete.")

        audio_file = (
            Path(tempfile.gettempdir())
            / "baby_dragon_recording.wav"
        )

        sf.write(
            str(audio_file),
            audio,
            self.sample_rate
        )

        return str(audio_file)