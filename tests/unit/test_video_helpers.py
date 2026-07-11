import pytest
from orbit.tools.video_tools import _validate_url, _parse_time, BLOCKED_HOSTS, SUPPORTED_EXTS
class TestValidateUrl:
    def test_https(self): _validate_url("https://youtube.com/watch?v=abc")
    def test_http(self): _validate_url("http://example.com/v.mp4")
    def test_no_scheme(self):
        with pytest.raises(ValueError): _validate_url("youtube.com/v")
    def test_localhost(self):
        with pytest.raises(ValueError): _validate_url("http://127.0.0.1/admin")
    def test_localhost_https(self):
        with pytest.raises(ValueError): _validate_url("https://localhost:8080/t")
    def test_private_192(self):
        with pytest.raises(ValueError): _validate_url("http://192.168.1.1/t")
    def test_private_10(self):
        with pytest.raises(ValueError): _validate_url("http://10.0.0.1/api")
    def test_private_172(self):
        with pytest.raises(ValueError): _validate_url("http://172.16.0.1/t")
    def test_ipv6(self):
        with pytest.raises(ValueError): _validate_url("http://[::1]:8080/t")
class TestParseTime:
    def test_sec(self): assert _parse_time("90")==90.0
    def test_minsec(self): assert _parse_time("1:30")==90.0
    def test_hms(self): assert _parse_time("1:00:00")==3600.0
    def test_spaces(self): assert _parse_time(" 5:00 ")==300.0
    def test_zero(self): assert _parse_time("0")==0.0
class TestConstants:
    def test_exts(self): assert ".jpg" in SUPPORTED_EXTS; assert ".pdf" in SUPPORTED_EXTS
    def test_blocked(self): assert "127." in BLOCKED_HOSTS; assert "192.168." in BLOCKED_HOSTS
