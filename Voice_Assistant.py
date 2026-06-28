"""
A basic Python voice assistant.

Responds to greetings, tells the time/date, and searches the web —
all in one file. Works in typed-text mode out of the box (no
microphone needed), and can optionally use real voice if you install
the audio libraries and have a mic/speakers.

Usage:
    python Voice_Assistant.py            # typed text
    python Voice_Assistant.py --voice    # real mic/speaker (needs extra libraries — see below)

Required Modules:
SpeechRecognition>=3.10
pyttsx3>=2.90
PyAudio>=0.2.13
"""
import argparse
import datetime
import re
import webbrowser
from urllib.parse import quote_plus

try:
    import speech_recognition as sr
    SR_AVAILABLE = True
except ImportError:
    SR_AVAILABLE = False

try:
    import pyttsx3
    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False

ASSISTANT_NAME = "Assistant"
EXIT_WORDS = {"exit", "quit", "stop", "goodbye", "bye"}

class SpeechIO:
    def __init__(self, use_voice=True):
        self.use_voice = use_voice and SR_AVAILABLE and TTS_AVAILABLE
        self.recognizer = None
        self.microphone = None
        self.tts_engine = None

        if use_voice and not self.use_voice:
            missing = []
            if not SR_AVAILABLE:
                missing.append("speech_recognition/pyaudio")
            if not TTS_AVAILABLE:
                missing.append("pyttsx3")
            print(f"[Voice libraries not available ({', '.join(missing)}); "
                  f"using typed text instead. See requirements.txt.]")

        if self.use_voice:
            try:
                self.recognizer = sr.Recognizer()
                self.microphone = sr.Microphone()
                self.tts_engine = pyttsx3.init()
            except Exception as e:
                print(f"[Voice hardware setup failed ({e}); falling back to text mode.]")
                self.use_voice = False

    def listen(self, prompt="You: "):
        if self.use_voice:
            try:
                with self.microphone as source:
                    self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                    print("Listening...")
                    audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=8)
                text = self.recognizer.recognize_google(audio)
                print(f"You said: {text}")
                return text
            except sr.WaitTimeoutError:
                print("(didn't hear anything)")
                return ""
            except sr.UnknownValueError:
                print("(sorry, couldn't understand that)")
                return ""
            except sr.RequestError as e:
                print(f"[Speech recognition service unavailable ({e}); "
                      f"switching to text input for the rest of this session.]")
                self.use_voice = False
                return input(prompt)
            except Exception as e:
                print(f"[Microphone error: {e}; switching to text input.]")
                self.use_voice = False
                return input(prompt)
        try:
            return input(prompt)
        except EOFError:
            return "exit"

    def say(self, text):
        print(f"Assistant: {text}")
        if self.use_voice and self.tts_engine:
            try:
                self.tts_engine.say(text)
                self.tts_engine.runAndWait()
            except Exception as e:
                print(f"[Text-to-speech error: {e}]")

def parse_intent(text):
    t = text.lower().strip()
    if not t:
        return "empty", {}

    if t in EXIT_WORDS:
        return "exit", {}

    if len(t.split()) <= 3 and any(g in t for g in ("hello", "hi there", "hey")):
        return "greeting", {}

    if t in ("help", "what can you do", "what can you do?"):
        return "help", {}

    if "time" in t:
        return "time", {}

    if "date" in t or "what day" in t:
        return "date", {}

    m = re.search(r"search (?:the web )?for (.+)", t)
    if m:
        return "web_search", {"query": m.group(1).strip(" ?.")}

    return "unknown", {"text": t}


# ============================================================
# Commands
# ============================================================
def handle_greeting():
    return "Hello! How can I help you today?"


def handle_time():
    now = datetime.datetime.now().strftime("%I:%M %p")
    return f"The current time is {now}."


def handle_date():
    today = datetime.datetime.now().strftime("%A, %B %d, %Y")
    return f"Today's date is {today}."


def handle_web_search(query):
    if not query:
        return "What would you like me to search for?"
    url = f"https://www.google.com/search?q={quote_plus(query)}"
    try:
        opened = webbrowser.open(url)
    except Exception:
        opened = False
    if opened:
        return f"Searching the web for '{query}'. I've opened the results in your browser."
    return f"I couldn't open a browser here. You can search manually: {url}"


HELP_TEXT = (
    "I can: say hello, tell the time, tell the date, and search the web for you.\n"
    "Try: 'hello', 'what time is it?', 'what's the date?', 'search for python tutorials'.\n"
    "Say 'exit' anytime to quit."
)

class Assistant:
    def __init__(self, use_voice=False):
        self.io = SpeechIO(use_voice=use_voice)

    def greet(self):
        self.io.say(f"Hi, I'm {ASSISTANT_NAME}. Say 'help' to see what I can do, "
                     f"or 'exit' to quit.")

    def run(self):
        self.greet()
        while True:
            text = self.io.listen()
            if not text:
                continue
            intent, entities = parse_intent(text)
            if intent == "exit":
                self.io.say("Goodbye!")
                break
            self.io.say(self._dispatch(intent, entities))

    def _dispatch(self, intent, entities):
        if intent == "greeting":
            return handle_greeting()
        if intent == "time":
            return handle_time()
        if intent == "date":
            return handle_date()
        if intent == "help":
            return HELP_TEXT
        if intent == "web_search":
            return handle_web_search(entities.get("query", ""))
        return ("I can only say hello, tell the time/date, or search the web right now. "
                "Try 'help' to see examples.")

def main():
    parser = argparse.ArgumentParser(description="A basic Python voice assistant.")
    parser.add_argument(
        "--voice", action="store_true",
        help="Use the microphone/speakers instead of typed text "
             "(requires speech_recognition, pyaudio, and pyttsx3)",
    )
    args = parser.parse_args()

    assistant = Assistant(use_voice=args.voice)
    try:
        assistant.run()
    except KeyboardInterrupt:
        print("\nGoodbye!")


if __name__ == "__main__":
    main()
