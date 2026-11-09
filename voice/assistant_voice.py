from pathlib import Path

from voice.microphone import MicrophoneRecorder
from voice.speech_to_text import SpeechToText
from voice.text_to_speech import TextToSpeech
from shared.ollama_client import OllamaClient


class BabyDragonVoice:

    def __init__(self):
        self.microphone = MicrophoneRecorder()
        self.recognizer = SpeechToText()
        self.speaker = TextToSpeech()
        self.ai = OllamaClient()

    def listen_and_reply(self, on_state=None):
        """on_state(name) is called with: talking, listening, thinking, idle.
        It is optional, so this still works on its own without the 3D dragon."""

        def state(name):
            if on_state:
                on_state(name)

        state("talking")
        self.speaker.speak("I am listening. Please speak.")

        state("listening")
        audio_file = self.microphone.record(duration=5)

        try:
            state("thinking")
            result = self.recognizer.transcribe(audio_file)

            recognized_text = result["text"].strip()
            language = result["language"]

            print("\nYou said:", recognized_text)
            print("Detected language:", language)

            if not recognized_text:
                print("No speech was recognized.")
                state("talking")
                self.speaker.speak("Sorry, I could not understand.")
                return

            print("Dragon is preparing a reply...")

            reply = self.ai.generate_reply(recognized_text)

            print("\nDragon:", reply)

            state("talking")
            self.speaker.speak(reply)

            print("Dragon finished speaking.")

        finally:
            Path(audio_file).unlink(missing_ok=True)
            state("idle")


if __name__ == "__main__":

    dragon = BabyDragonVoice()

    input("Press ENTER when you are ready to talk...")

    dragon.listen_and_reply()
