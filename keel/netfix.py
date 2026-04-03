import contextlib
import io


def apply_tls_patch() -> None:
    try:
        from tls_requests.models.libraries import TLSLibrary

        _orig = TLSLibrary.download.__func__

        @classmethod
        def _quiet_download(cls, version=None):
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                return _orig(cls, version)

        TLSLibrary.download = _quiet_download
    except Exception:
        pass
