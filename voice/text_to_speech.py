import pyttsx3


class TextToSpeech:

    def __init__(self):
        self.rate = 150
        self.volume = 1.0

    def speak(self, text):

        if not isinstance(text, str) or not text.strip():
            return

        engine = pyttsx3.init("sapi5")

        engine.setProperty("rate", self.rate)
        engine.setProperty("volume", self.volume)

        engine.say(text)
        engine.runAndWait()

        engine.stop()
        del engine


if __name__ == "__main__":
    dragon = TextToSpeech()

    dragon.speak("First message. I am listening.")

    input("Press ENTER for second message...")

    dragon.speak("Second message. I heard you clearly.")