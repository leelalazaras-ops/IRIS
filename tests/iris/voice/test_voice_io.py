"""
Unit tests for the voice I/O module.
"""

import unittest
from unittest.mock import patch, MagicMock, ANY

# Import the module to test
from src.iris.voice.voice_io import listen_for_speech, speak_text

class TestVoiceIO(unittest.TestCase):

    @patch('src.iris.voice.voice_io.sr')
    def test_listen_for_speech_success(self, mock_sr):
        # Set up exception classes on the mock
        mock_sr.WaitTimeoutError = type('WaitTimeoutError', (Exception,), {})
        mock_sr.UnknownValueError = type('UnknownValueError', (Exception,), {})
        mock_sr.RequestError = type('RequestError', (Exception,), {})

        # Mock the recognizer and microphone
        mock_recognizer = MagicMock()
        mock_sr.Recognizer.return_value = mock_recognizer
        mock_microphone = MagicMock()
        mock_sr.Microphone.return_value = mock_microphone

        # Mock the listen method to return some audio data
        mock_recognizer.listen.return_value = b'audio data'

        # Mock the recognize_sphinx method to return a string
        mock_recognizer.recognize_sphinx.return_value = "hello world"

        # Call the function
        result = listen_for_speech(timeout=2, phrase_time_limit=5)

        # Assertions
        self.assertEqual(result, "hello world")
        mock_recognizer.adjust_for_ambient_noise.assert_called_once()
        mock_recognizer.listen.assert_called_once_with(ANY, timeout=2, phrase_time_limit=5)
        mock_recognizer.recognize_sphinx.assert_called_once_with(b'audio data')

    @patch('src.iris.voice.voice_io.sr')
    def test_listen_for_speech_wait_timeout(self, mock_sr):
        # Set up exception classes on the mock
        mock_sr.WaitTimeoutError = type('WaitTimeoutError', (Exception,), {})
        mock_sr.UnknownValueError = type('UnknownValueError', (Exception,), {})
        mock_sr.RequestError = type('RequestError', (Exception,), {})

        mock_recognizer = MagicMock()
        mock_sr.Recognizer.return_value = mock_recognizer
        mock_microphone = MagicMock()
        mock_sr.Microphone.return_value = mock_microphone

        # Simulate a timeout when listening
        mock_recognizer.listen.side_effect = mock_sr.WaitTimeoutError()

        result = listen_for_speech()

        self.assertIsNone(result)

    @patch('src.iris.voice.voice_io.sr')
    def test_listen_for_speech_unknown_value(self, mock_sr):
        # Set up exception classes on the mock
        mock_sr.WaitTimeoutError = type('WaitTimeoutError', (Exception,), {})
        mock_sr.UnknownValueError = type('UnknownValueError', (Exception,), {})
        mock_sr.RequestError = type('RequestError', (Exception,), {})

        mock_recognizer = MagicMock()
        mock_sr.Recognizer.return_value = mock_recognizer
        mock_microphone = MagicMock()
        mock_sr.Microphone.return_value = mock_microphone

        mock_recognizer.listen.return_value = b'audio data'
        mock_recognizer.recognize_sphinx.side_effect = mock_sr.UnknownValueError()

        result = listen_for_speech()

        self.assertIsNone(result)

    @patch('src.iris.voice.voice_io.sr')
    def test_listen_for_speech_request_error(self, mock_sr):
        # Set up exception classes on the mock
        mock_sr.WaitTimeoutError = type('WaitTimeoutError', (Exception,), {})
        mock_sr.UnknownValueError = type('UnknownValueError', (Exception,), {})
        mock_sr.RequestError = type('RequestError', (Exception,), {})

        mock_recognizer = MagicMock()
        mock_sr.Recognizer.return_value = mock_recognizer
        mock_microphone = MagicMock()
        mock_sr.Microphone.return_value = mock_microphone

        mock_recognizer.listen.return_value = b'audio data'
        mock_recognizer.recognize_sphinx.side_effect = mock_sr.RequestError("some error")

        result = listen_for_speech()

        self.assertIsNone(result)

    @patch('src.iris.voice.voice_io.sr')
    def test_listen_for_speech_unexpected_error(self, mock_sr):
        # Set up exception classes on the mock
        mock_sr.WaitTimeoutError = type('WaitTimeoutError', (Exception,), {})
        mock_sr.UnknownValueError = type('UnknownValueError', (Exception,), {})
        mock_sr.RequestError = type('RequestError', (Exception,), {})

        mock_recognizer = MagicMock()
        mock_sr.Recognizer.return_value = mock_recognizer
        mock_microphone = MagicMock()
        mock_sr.Microphone.return_value = mock_microphone

        mock_recognizer.listen.side_effect = Exception("unexpected")

        result = listen_for_speech()

        self.assertIsNone(result)

    @patch('src.iris.voice.voice_io.pyttsx3')
    def test_speak_text_success(self, mock_pyttsx3):
        mock_engine = MagicMock()
        mock_pyttsx3.init.return_value = mock_engine

        result = speak_text("hello world")

        self.assertTrue(result)
        mock_pyttsx3.init.assert_called_once()
        mock_engine.say.assert_called_once_with("hello world")
        mock_engine.runAndWait.assert_called_once()

    @patch('src.iris.voice.voice_io.pyttsx3')
    def test_speak_text_empty_string(self, mock_pyttsx3):
        result = speak_text("")
        self.assertFalse(result)
        mock_pyttsx3.init.assert_not_called()

    @patch('src.iris.voice.voice_io.pyttsx3')
    def test_speak_text_whitespace(self, mock_pyttsx3):
        result = speak_text("   ")
        self.assertFalse(result)
        mock_pyttsx3.init.assert_not_called()

    @patch('src.iris.voice.voice_io.pyttsx3')
    def test_speak_text_error(self, mock_pyttsx3):
        mock_pyttsx3.init.side_effect = Exception("TTS error")

        result = speak_text("hello world")

        self.assertFalse(result)

    def test_listen_for_speech_library_not_installed(self):
        # Temporarily set sr to None to simulate not installed
        import src.iris.voice.voice_io as voice_io
        original_sr = voice_io.sr
        voice_io.sr = None
        try:
            result = listen_for_speech()
            self.assertIsNone(result)
        finally:
            voice_io.sr = original_sr

    def test_speak_text_library_not_installed(self):
        import src.iris.voice.voice_io as voice_io
        original_pyttsx3 = voice_io.pyttsx3
        voice_io.pyttsx3 = None
        try:
            result = speak_text("hello")
            self.assertFalse(result)
        finally:
            voice_io.pyttsx3 = original_pyttsx3

if __name__ == '__main__':
    unittest.main()