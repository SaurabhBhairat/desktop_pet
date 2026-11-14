import threading
from pathlib import Path

from voice.dragon_chat import DragonChat, speakable
from voice.microphone import MicrophoneRecorder
from voice.speech_to_text import SpeechToText
from voice.text_to_speech import TextToSpeech


class BabyDragonVoice:

    def __init__(self):
        self.microphone = MicrophoneRecorder()
        self.recognizer = SpeechToText()
        self.speaker = TextToSpeech()
        self.chat = DragonChat()                 # remembers the chat and facts about you
        threading.Thread(target=self.chat.warm_up, daemon=True).start()   # load the model in the background

    @staticmethod
    def _flag(fn):
        return True if fn is None else bool(fn())

    def _deliver(self, text, on_text, voice_on, bubble_on):
        """Show the answer (bubble) and/or say it, depending on the dragon's settings."""
        if on_text:
            on_text(text)                        # the full answer; the dragon window decides about the bubble
        if self._flag(voice_on):
            spoken = speakable(text, bubble_on=self._flag(bubble_on))
            if spoken:
                self.speaker.speak(spoken)

    def _ask(self, question, on_text, bubble_on):
        """Asks the brain. With the bubble on, the answer appears while it is being written."""
        live = on_text is not None and self._flag(bubble_on)
        if live:
            on_text("Thinking...")
        return self.chat.reply(question, on_partial=on_text if live else None)

    def _record(self):
        """Records until you stop talking. Falls back to the old fixed 5 seconds if that fails."""
        try:
            from voice.listen import record_until_silence
            print("Microphone active. Speak now!")
            path, heard = record_until_silence()
            print("Recording complete.")
            return path, heard
        except Exception as exc:
            print("Smart recording not available (%s); using 5 seconds." % exc)
            return self.microphone.record(duration=5), True

    def listen_and_reply(self, on_state=None, on_text=None, voice_on=None, bubble_on=None):
        """Voice question. on_state(name): talking, listening, thinking, idle.
        on_text(text): the answer, for the bubble.  voice_on()/bubble_on(): how answers should be delivered.
        All are optional, so this still works on its own without the 3D dragon."""

        def state(name):
            if on_state:
                on_state(name)

        if self._flag(voice_on):
            state("talking")
            self.speaker.speak("I am listening.")

        state("listening")
        audio_file, heard = self._record()

        try:
            state("thinking")
            recognized_text = ""
            if heard:
                result = self.recognizer.transcribe(audio_file)
                recognized_text = result["text"].strip()
                print("\nYou said:", recognized_text)
                print("Detected language:", result["language"])

            if not recognized_text:
                print("No speech was recognized.")
                state("talking")
                self._deliver("Sorry, I did not hear anything. Try again a little closer to the microphone.",
                              on_text, voice_on, bubble_on)
                return

            print("Dragon is preparing a reply...")
            reply = self._ask(recognized_text, on_text, bubble_on)
            print("\nDragon:", reply)

            state("talking")
            self._deliver(reply, on_text, voice_on, bubble_on)
            print("Dragon finished.")

        finally:
            Path(audio_file).unlink(missing_ok=True)
            state("idle")

    def reply_to_text(self, text, on_state=None, on_text=None, voice_on=None, bubble_on=None):
        """Typed question: same answer path as the voice one, without the microphone."""

        def state(name):
            if on_state:
                on_state(name)

        try:
            state("thinking")
            print("\nYou typed:", text[:200] + ("..." if len(text) > 200 else ""))
            reply = self._ask(text, on_text, bubble_on)
            print("\nDragon:", reply)
            state("talking")
            self._deliver(reply, on_text, voice_on, bubble_on)
        finally:
            state("idle")


if __name__ == "__main__":

    dragon = BabyDragonVoice()

    input("Press ENTER when you are ready to talk...")

    dragon.listen_and_reply()
