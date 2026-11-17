import pytest
from utils.security import validate_safe_url, sanitize_filename

def test_validate_safe_urls():
    # Legitimate public URLs
    safe_urls = [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4",
        "https://vimeo.com/123456"
    ]
    for url in safe_urls:
        is_safe, msg = validate_safe_url(url)
        assert is_safe is True, f"Failed for {url}: {msg}"

def test_block_ssrf_attacks():
    # Dangerous internal / private targets
    dangerous_urls = [
        "http://localhost:8080/admin",
        "http://127.0.0.1:22",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.1/secret",
        "http://192.168.1.1/router-config",
        "ftp://malicious.site/script.sh",
        "file:///etc/passwd"
    ]
    for url in dangerous_urls:
        is_safe, msg = validate_safe_url(url)
        assert is_safe is False, f"Should have blocked {url}"

def test_sanitize_filename():
    assert sanitize_filename("../../../etc/passwd") == "etc_passwd"
    assert sanitize_filename("Normal Video (1080p).mp4") == "Normal_Video__1080p_.mp4"
    assert sanitize_filename("") == "unnamed_file"
