"""
Voice I/O for IRIS: speech-to-text and text-to-speech.

Uses SpeechRecognition with PocketSphinx for offline STT and pyttsx3 for offline TTS.
"""

import logging
from typing import Optional

# Try to import the required libraries. If they are not available, we set them to None
# and handle gracefully in the functions.
try:
    import speech_recognition as sr
except ImportError:
    sr = None

try:
    import pyttsx3
except ImportError:
    pyttsx3 = None

logger = logging.getLogger(__name__)

def listen_for_speech(timeout: int = 5, phrase_time_limit: int = 10) -> Optional[str]:
    """
    Listen for speech from the microphone and convert to text using PocketSphinx.

    Args:
        timeout: Seconds to wait for speech to start before raising an error.
        phrase_time_limit: Maximum seconds to allow for a phrase.

    Returns:
        Recognized text as a string, or None if speech was not recognized or an error occurred.
    """
    if sr is None:
        logger.error("SpeechRecognition library is not installed. Install it with: pip install SpeechRecognition")
        return None

    recognizer = sr.Recognizer()
    microphone = sr.Microphone()

    try:
        with microphone as source:
            logger.debug("Adjusting for ambient noise...")
            recognizer.adjust_for_ambient_noise(source, duration=1)
            logger.debug(f"Listening for speech (timeout={timeout}, phrase_time_limit={phrase_time_limit})...")
            audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
        logger.debug("Recognizing speech using PocketSphinx...")
        # Use PocketSphinx for offline recognition
        text = recognizer.recognize_sphinx(audio)
        logger.debug(f"Recognized text: {text}")
        return text
    except sr.WaitTimeoutError:
        logger.debug("Listening timed out while waiting for phrase to start.")
        return None
    except sr.UnknownValueError:
        logger.debug("Speech was unintelligible.")
        return None
    except sr.RequestError as e:
        logger.error(f"PocketSphinx error: {e}")
        return None
    except Exception as e:  # noqa: BLE001
        logger.error(f"Unexpected error in speech recognition: {e}")
        return None

def speak_text(text: str) -> bool:
    """
    Convert text to speech using pyttsx3.

    Args:
        text: The text to speak.

    Returns:
        True if speech was successfully initiated, False otherwise.
    """
    if pyttsx3 is None:
        logger.error("pyttsx3 library is not installed. Install it with: pip install pyttsx3")
        return False

    if not text or not text.strip():
        logger.debug("Empty text provided to speak_text.")
        return False

    try:
        # Initialize the TTS engine
        engine = pyttsx3.init()
        # Optionally, set properties (rate, volume, etc.) if needed
        # For example: engine.setProperty('rate', 150)
        engine.say(text)
        engine.runAndWait()
        logger.debug(f"Spoke text: {text}")
        return True
    except Exception as e:
        logger.error(f"Error in text-to-speech: {e}")
        return False