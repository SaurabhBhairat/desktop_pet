"""
listen.py - records your voice until you stop talking (instead of a fixed 5 seconds).

It waits up to 8 seconds for you to start, records while you speak, and stops after about
1.3 seconds of silence (or 25 seconds in total). The loudness limit adapts to your room's noise.
"""
import tempfile

BLOCK_SECONDS = 0.1


class SilenceDetector:
    """Feed it the loudness of each 0.1 s block; it answers 'continue' or 'stop'."""

    def __init__(self, wait_for_speech=8.0, max_total=25.0, trailing_silence=1.3, min_threshold=0.012):
        self.wait_for_speech = wait_for_speech
        self.max_total = max_total
        self.trailing_silence = trailing_silence
        self.min_threshold = min_threshold
        self.elapsed = 0.0
        self.silence_run = 0.0
        self.heard_speech = False
        self._noise = []
        self.threshold = min_threshold

    def feed(self, rms):
        self.elapsed += BLOCK_SECONDS
        if len(self._noise) < 3 and not self.heard_speech:          # first 0.3 s: measure the room noise
            self._noise.append(rms)
            if len(self._noise) == 3:
                self.threshold = max(self.min_threshold, 3.0 * (sum(self._noise) / 3.0))
            return "continue"
        if rms > self.threshold:
            self.heard_speech = True
            self.silence_run = 0.0
        else:
            self.silence_run += BLOCK_SECONDS
        if self.heard_speech and self.silence_run >= self.trailing_silence:
            return "stop"
        if not self.heard_speech and self.elapsed >= self.wait_for_speech:
            return "stop"
        if self.elapsed >= self.max_total:
            return "stop"
        return "continue"


def record_until_silence(samplerate=16000):
    """Returns (path_to_wav, heard_speech). Needs sounddevice, soundfile and numpy (already installed)."""
    import numpy as np
    import sounddevice as sd
    import soundfile as sf

    detector = SilenceDetector()
    block = int(samplerate * BLOCK_SECONDS)
    chunks = []
    with sd.InputStream(samplerate=samplerate, channels=1, dtype="float32", blocksize=block) as stream:
        while True:
            data, _overflow = stream.read(block)
            chunks.append(data.copy())
            if detector.feed(float(np.sqrt(np.mean(np.square(data))))) == "stop":
                break
    audio = np.concatenate(chunks) if chunks else np.zeros((1, 1), dtype="float32")
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    sf.write(tmp.name, audio, samplerate)
    return tmp.name, detector.heard_speech
