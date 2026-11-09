from voice.microphone import MicrophoneRecorder
from voice.speech_to_text import SpeechToText
from pathlib import Path


def main():
    recorder = MicrophoneRecorder()
    dragon = SpeechToText()

    print("Baby Dragon is ready!")
    input("Press ENTER to start a 5-second recording...")

    audio_file = recorder.record(duration=5)

    try:
        print("\nUnderstanding your speech...")
        result = dragon.transcribe(audio_file)

        print("\nRecognized text:", result["text"])
        print("Detected language:", result["language"])
        print("Confidence:", result["language_probability"])

    finally:
        Path(audio_file).unlink(missing_ok=True)
        print("\nTemporary recording deleted.")


if __name__ == "__main__":
    main()