"""Shared Picamera2 configuration for CLI capture and the existing Pi HTTP server."""
import configparser
import io
import os
import time
from typing import Optional

try:
    from picamera2 import Picamera2
    _ON_PI = True
except (ImportError, RuntimeError):
    _ON_PI = False


def _load_config():
    cfg = configparser.ConfigParser()
    cfg.read(os.path.join(os.path.dirname(__file__), 'config.ini'))
    return cfg


class CameraSession:
    """One configured camera supplies fresh preview frames and full-size stills."""
    def __init__(self, cfg=None):
        self.cfg = cfg if cfg is not None else _load_config()
        self.cam = None
        from hardware_runtime import simulated
        self.simulated = simulated(self.cfg)
        self.focus = self.cfg.get('camera', 'FOCUS_MODE', fallback='manual').lower()
        if self.focus not in ('manual', 'auto', 'continuous'):
            raise ValueError('camera.FOCUS_MODE must be manual, auto, or continuous')
        if self.simulated:
            return
        if not _ON_PI:
            raise RuntimeError('Picamera2 unavailable; install Raspberry Pi OS camera packages')
        from libcamera import controls
        self.cam = Picamera2()
        try:
            modes = {'manual': controls.AfModeEnum.Manual, 'auto': controls.AfModeEnum.Auto,
                     'continuous': controls.AfModeEnum.Continuous}
            camera_controls = {'AfMode': modes[self.focus]}
            # Leave the lens at its initial position unless explicitly configured,
            # matching the successful terminal --autofocus-mode manual test.
            lens = self.cfg.get('camera', 'LENS_POSITION', fallback='').strip()
            if self.focus == 'manual' and lens:
                camera_controls['LensPosition'] = float(lens)
            self.cam.configure(self.cam.create_still_configuration(
                main={'size': (self.cfg.getint('camera', 'RESOLUTION_WIDTH', fallback=1920),
                               self.cfg.getint('camera', 'RESOLUTION_HEIGHT', fallback=1080)),
                      'format': 'BGR888'}, controls=camera_controls, buffer_count=3, queue=False))
            self.cam.start()
            time.sleep(self.cfg.getfloat('camera', 'AUTOFOCUS_WAIT', fallback=1.5))
        except Exception:
            self.close()
            raise

    def frame(self, preview=False):
        from PIL import Image
        buf = io.BytesIO()
        if self.simulated:
            image = Image.new('RGB', (1280, 960), color=(240, 230, 210))
            if preview:
                image.thumbnail((640, 360))
            image.save(buf, format='JPEG', quality=75 if preview else 90)
        else:
            if not preview and self.focus == 'auto' and not self.cam.autofocus_cycle():
                raise RuntimeError('Camera autofocus failed; check lighting and sample distance')
            self.cam.capture_file(buf, format='jpeg')
            if preview:
                buf.seek(0)
                with Image.open(buf) as image:
                    image.thumbnail((640, 360))
                    small = io.BytesIO()
                    image.save(small, format='JPEG', quality=70)
                return small.getvalue()
        return buf.getvalue()

    def close(self):
        if self.cam is not None:
            self.cam.close()
            self.cam = None


def capture_image(save_path: Optional[str] = None) -> bytes:
    session = CameraSession()
    try:
        data = session.frame()
        if save_path:
            with open(save_path, 'wb') as stream:
                stream.write(data)
        return data
    finally:
        session.close()


def camera_ready():
    session = CameraSession()
    try:
        session.frame(preview=True)  # Readiness means actual frames, not just enumeration.
        return True
    finally:
        session.close()


if __name__ == '__main__':
    import sys
    from hardware_runtime import run_hardware
    out = sys.argv[1] if len(sys.argv) > 1 else 'test_capture.jpg'
    data = run_hardware('capture', timeout=20)
    with open(out, 'wb') as stream:
        stream.write(data)
    print(f'Captured {len(data):,} bytes → {out}')
