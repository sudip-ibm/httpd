import pytest

from .env import H2Conf, H2TestEnv


@pytest.mark.skipif(condition=H2TestEnv.is_unsupported, reason="mod_http2 not supported here")
class TestInvalidHeaders:

    @pytest.fixture(autouse=True, scope='class')
    def _class_scope(self, env):
        H2Conf(env).add_vhost_cgi().install()
        assert env.apache_restart() == 0

    # let the hecho.py CGI echo chars < 0x20 in field name
    # for almost all such characters, the stream returns a 500
    # cr is handled special
    def test_h2_200_01(self, env):
        url = env.mkurl("https", "cgi", "/hecho.py")
        for x in range(1, 32):
            data = f'name=x%{x:02x}x&value=yz'
            r = env.curl_post_data(url, data)
            if x in [13]:
                assert 0 == r.exit_code, f'unexpected exit code for char 0x{x:02}'
                assert 200 == r.response["status"], f'unexpected status for char 0x{x:02}'
            else:
                assert 0 == r.exit_code, f'"unexpected exit code for char 0x{x:02}'
                assert 500 == r.response["status"], f'posting "{data}" unexpected status, {r}'

    # let the hecho.py CGI echo chars < 0x20 in field value
    # for almost all such characters, the stream returns a 500
    # cr and lf are handled special
    def test_h2_200_02(self, env):
        url = env.mkurl("https", "cgi", "/hecho.py")
        for x in range(1, 32):
            if 9 != x:
                r = env.curl_post_data(url, "name=x&value=y%%%02x" % x)
                if x in [10, 13]:
                    assert 0 == r.exit_code, "unexpected exit code for char 0x%02x" % x
                    assert 200 == r.response["status"], "unexpected status for char 0x%02x" % x
                else:
                    assert 0 == r.exit_code, "unexpected exit code for char 0x%02x" % x
                    assert 500 == r.response["status"], "unexpected status for char 0x%02x" % x

    # let the hecho.py CGI echo 0x10 and 0x7f in field name and value
    def test_h2_200_03(self, env):
        url = env.mkurl("https", "cgi", "/hecho.py")
        for h in ["10", "7f"]:
            r = env.curl_post_data(url, "name=x%%%s&value=yz" % h)
            assert 0 == r.exit_code, "unexpected exit code for char 0x%02x" % h
            assert 500 == r.response["status"], "unexpected status for char 0x%02x" % h
            r = env.curl_post_data(url, "name=x&value=y%%%sz" % h)
            assert 0 == r.exit_code, "unexpected exit code for char 0x%02x" % h
            assert 500 == r.response["status"], "unexpected status for char 0x%02x" % h

    # test header field lengths check, LimitRequestLine (default 8190)
    def test_h2_200_10(self, env):
        url = env.mkurl("https", "cgi", "/")
        val = "1234567890"  # 10 chars
        for i in range(3):  # make a 10000 char string
            val = "%s%s%s%s%s%s%s%s%s%s" % (val, val, val, val, val, val, val, val, val, val)
        # LimitRequestLine 8190 ok, one more char -> 431
        r = env.curl_get(url, options=["-H", "x: %s" % (val[:8187])])
        assert r.response["status"] == 200
        r = env.curl_get(url, options=["-H", "x: %sx" % (val[:8188])])
        assert 431 == r.response["status"]
        # same with field name
        r = env.curl_get(url, options=["-H", "y%s: 1" % (val[:8186])])
        assert r.response["status"] == 200
        r = env.curl_get(url, options=["-H", "y%s: 1" % (val[:8188])])
        assert 431 == r.response["status"]

    # test header field lengths check, LimitRequestFieldSize (default 8190)
    def test_h2_200_11(self, env):
        url = env.mkurl("https", "cgi", "/")
        val = "1234567890"  # 10 chars
        for i in range(3):  # make a 10000 char string
            val = "%s%s%s%s%s%s%s%s%s%s" % (val, val, val, val, val, val, val, val, val, val)
        # LimitRequestFieldSize 8190 ok, one more char -> 400 in HTTP/1.1
        # (we send 4000+4185 since they are concatenated by ", " and start with "x: "
        r = env.curl_get(url, options=["-H", "x: %s" % (val[:4000]),  "-H", "x: %s" % (val[:4185])])
        assert r.response["status"] == 200
        r = env.curl_get(url, options=["--http1.1", "-H", "x: %s" % (val[:4000]),  "-H", "x: %s" % (val[:4189])])
        assert 400 == r.response["status"]
        r = env.curl_get(url, options=["-H", "x: %s" % (val[:4000]),  "-H", "x: %s" % (val[:4191])])
        assert 431 == r.response["status"]

    # test header field count, LimitRequestFields (default 100)
    # see #201: several headers with same name are mered and count only once
    def test_h2_200_12(self, env):
        url = env.mkurl("https", "cgi", "/")
        opt = []
        # curl sends 3 headers itself (user-agent, accept, and our AP-Test-Name)
        for i in range(97):
            opt += ["-H", "x: 1"]
        r = env.curl_get(url, options=opt)
        assert r.response["status"] == 200
        r = env.curl_get(url, options=(opt + ["-H", "y: 2"]))
        assert r.response["status"] == 200

    # test header field count, LimitRequestFields (default 100)
    # different header names count each
    def test_h2_200_13(self, env):
        url = env.mkurl("https", "cgi", "/")
        opt = []
        # curl sends 3 headers itself (user-agent, accept, and our AP-Test-Name)
        for i in range(97):
            opt += ["-H", f"x{i}: 1"]
        r = env.curl_get(url, options=opt)
        assert r.response["status"] == 200
        r = env.curl_get(url, options=(opt + ["-H", "y: 2"]))
        assert 431 == r.response["status"]

    # test "LimitRequestFields 0" setting, see #200
    def test_h2_200_14(self, env):
        conf = H2Conf(env)
        conf.add("""
            LimitRequestFields 20
            """)
        conf.add_vhost_cgi()
        conf.install()
        assert env.apache_restart() == 0
        url = env.mkurl("https", "cgi", "/")
        opt = []
        for i in range(21):
            opt += ["-H", "x{0}: 1".format(i)]
        r = env.curl_get(url, options=opt)
        assert 431 == r.response["status"]
        conf = H2Conf(env)
        conf.add("""
            LimitRequestFields 0
            """)
        conf.add_vhost_cgi()
        conf.install()
        assert env.apache_restart() == 0
        url = env.mkurl("https", "cgi", "/")
        opt = []
        for i in range(100):
            opt += ["-H", "x{0}: 1".format(i)]
        r = env.curl_get(url, options=opt)
        assert r.response["status"] == 200

    # the uri limits
    def test_h2_200_15(self, env):
        conf = H2Conf(env)
        conf.add("""
            LimitRequestLine 48
            """)
        conf.add_vhost_cgi()
        conf.install()
        assert env.apache_restart() == 0
        url = env.mkurl("https", "cgi", "/")
        r = env.curl_get(url)
        assert r.response["status"] == 200
        url = env.mkurl("https", "cgi", "/" + (48*"x"))
        r = env.curl_get(url)
        assert 414 == r.response["status"]
        # nghttp sends the :method: header first (so far)
        # trigger a too long request line on it
        # the stream will RST and we get no response
        url = env.mkurl("https", "cgi", "/")
        opt = ["-H:method: {0}".format(100*"x")]
        r = env.nghttp().get(url, options=opt)
        assert r.exit_code == 0, r
        assert not r.response

    # invalid chars in method
    def test_h2_200_16(self, env):
        if not env.h2load_is_at_least('1.45.0'):
            pytest.skip(f'nhttp2 version too old')
        conf = H2Conf(env)
        conf.add_vhost_cgi()
        conf.install()
        assert env.apache_restart() == 0
        url = env.mkurl("https", "cgi", "/hello.py")
        opt = ["-H:method: GET /hello.py"]
        r = env.nghttp().get(url, options=opt)
        assert r.exit_code == 0, r
        assert r.response is None
        url = env.mkurl("https", "cgi", "/proxy/hello.py")
        r = env.nghttp().get(url, options=opt)
        assert r.exit_code == 0, r
        assert r.response is None
