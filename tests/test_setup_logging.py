import importlib.util
import importlib.machinery
import sys
import types
from pathlib import Path


def test_setup_logging_creates_logfile(tmp_path, monkeypatch):
    class Dummy:
        def __init__(self, *args, **kwargs):
            pass

    # stub openai
    sys.modules['openai'] = types.SimpleNamespace(OpenAI=Dummy)

    # stub moviepy structures
    moviepy = types.ModuleType('moviepy')
    video = types.ModuleType('moviepy.video')
    video_io = types.ModuleType('moviepy.video.io')
    image_module = types.ModuleType('moviepy.video.io.ImageSequenceClip')
    image_module.ImageSequenceClip = Dummy
    video_io.ImageSequenceClip = image_module
    audio = types.ModuleType('moviepy.audio')
    audio_io = types.ModuleType('moviepy.audio.io')
    audio_module = types.ModuleType('moviepy.audio.io.AudioFileClip')
    audio_module.AudioFileClip = Dummy
    audio_io.AudioFileClip = audio_module
    moviepy.video = video
    moviepy.audio = audio
    sys.modules['moviepy'] = moviepy
    sys.modules['moviepy.video'] = video
    sys.modules['moviepy.video.io'] = video_io
    sys.modules['moviepy.video.io.ImageSequenceClip'] = image_module
    sys.modules['moviepy.audio'] = audio
    sys.modules['moviepy.audio.io'] = audio_io
    sys.modules['moviepy.audio.io.AudioFileClip'] = audio_module

    sys.modules['tqdm'] = types.SimpleNamespace(tqdm=lambda *a, **kw: None)

    loader = importlib.machinery.SourceFileLoader(
        'story_to_video', str(Path(__file__).resolve().parents[1] / 'story_to_video.py')
    )
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)

    module.__file__ = str(tmp_path / 'story_to_video.py')
    monkeypatch.chdir(tmp_path)

    module.setup_logging(False)

    assert (tmp_path / 'story-to-video' / 'run.log').exists()
