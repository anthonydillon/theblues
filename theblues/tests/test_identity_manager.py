import base64
import json
from unittest import TestCase

from httmock import (
    HTTMock,
    urlmatch,
)
from mock import (
    Mock,
    patch,
    )

from theblues.errors import (
    InvalidMacaroon,
    ServerError,
)
from theblues.identity_manager import IdentityManager
from theblues.tests import helpers
from theblues.utils import DEFAULT_TIMEOUT

_called = None


LOGIN_PATH = '.*/v1/u/.*'
DISCHARGE_PATH = '.*/discharge'
DISCHARGE_TOKEN_PATH = '.*/discharge-token-for-user'
EXTRA_INFO_PATH = '.*/extra-info'


@urlmatch(path=LOGIN_PATH)
def entity_200(url, request):
    global _called
    _called = True
    return {
        'status_code': 200,
        'content': {},
    }


@urlmatch(path=LOGIN_PATH)
def entity_403(url, request):
    global _called
    _called = True
    return {
        'status_code': 403,
        'content': {},
    }


@urlmatch(path=DISCHARGE_PATH)
def discharge_macaroon_200(url, request):
    return {
        'status_code': 200,
        'content': {'Macaroon': 'something'},
    }


@urlmatch(path=DISCHARGE_TOKEN_PATH)
def discharge_token_200(url, request):
    return {
        'status_code': 200,
        'content': {'DischargeToken': 'something'},
    }


@urlmatch(path=DISCHARGE_PATH)
def discharge_macaroon_404(url, request):
    return {
        'status_code': 404,
        'content': {},
    }


@urlmatch(path=EXTRA_INFO_PATH)
def extra(url, request):
    response = {'status_code': 200}
    if request.method == 'GET':
        response['content'] = {'foo': 1}
    if request.method == 'PUT':
        assert request.body == '{"foo": 1}'
    return response


def patch_make_request(return_value=None):
    """Patch the "theblues.utils.make_request" helper function."""
    return patch(
        'theblues.identity_manager.make_request',
        return_value=return_value)


class TestIdentityManager(TestCase, helpers.TimeoutTestsMixin):

    def setUp(self):
        global _called
        _called = False
        self.idm = IdentityManager('http://example.com/v1')

    def test_login_success(self):
        with HTTMock(entity_200):
            self.idm.login('fabrice', {})
        self.assertTrue(_called)

    def test_login_success_url(self):
        user = 'fabrice'

        class FakeResponse:
            status_code = 200

            def raise_for_status(self):
                pass

        with patch_make_request(return_value=FakeResponse()) as mocked:
            self.idm.login(user, 'body')
        self.assertTrue(mocked.called)
        expected_url = 'http://example.com/v1/u/{}'.format(user)
        mocked.assert_called_once_with(
            expected_url,
            method='PUT',
            body='body',
            timeout=DEFAULT_TIMEOUT,
        )

    def test_login_error_forbidden(self):
        with HTTMock(entity_403):
            with self.assertRaises(ServerError) as ctx:
                    self.idm.login('fabrice', {})
        self.assertEqual(403, ctx.exception.args[0])
        self.assertTrue(_called)

    def test_login_error_timeout(self):
        with self.assert_timeout('http://example.com/v1/u/who',
                                 DEFAULT_TIMEOUT):
            self.idm.login('who', {})

    def _makeMockMacaroon(self, third_party_caveat=None):
        macaroon = Mock()
        if third_party_caveat:
            caveat = [third_party_caveat[1:]]
        else:
            caveat = []
        macaroon.third_party_caveats = Mock(return_value=caveat)
        return macaroon

    def test_discharge_successful(self):
        macaroon = self._makeMockMacaroon((
            'http://example.com/', "caveat_key", "identifier"))
        with HTTMock(discharge_macaroon_200):
            results = self.idm.discharge('Brad', macaroon)
        self.assertEqual(base64.urlsafe_b64encode(b'"something"'), results)

    def test_discharge_error_invalid_macaroon(self):
        macaroon = self._makeMockMacaroon()
        with HTTMock(discharge_macaroon_200):
            with self.assertRaises(InvalidMacaroon):
                self.idm.discharge('Brad', macaroon)

    def test_discharge_error_wrong_status(self):
        macaroon = self._makeMockMacaroon((
            'http://example.com/', "caveat_key", "identifier"))
        with HTTMock(discharge_macaroon_404):
            with self.assertRaises(ServerError) as ctx:
                self.idm.discharge('Brad', macaroon)
        self.assertEqual(404, ctx.exception.args[0])

    def test_discharge_error_timeout(self):
        macaroon = self._makeMockMacaroon((
            'http://example.com/', "caveat_key", "identifier"))
        expected_url = (
            'http://example.com/v1/discharger/discharge'
            '?discharge-for-user=who&id=identifier')
        with self.assert_timeout(expected_url, DEFAULT_TIMEOUT):
            self.idm.discharge('who', macaroon)

    @patch('theblues.identity_manager.make_request')
    def test_discharge_username_quoted(self, make_request_mock):
        # When discharging the macaroon for the identity, the user name is
        # properly quoted.
        make_request_mock.return_value = {'Macaroon': 'macaroon'}
        macaroon = self._makeMockMacaroon((
            'http://example.com/', "caveat_key", "identifier"))
        base64_macaroon = self.idm.discharge('my.user+name', macaroon)
        expected_macaroon = base64.urlsafe_b64encode(
            json.dumps('macaroon').encode('utf-8'))
        self.assertEqual(expected_macaroon, base64_macaroon)
        make_request_mock.assert_called_once_with(
            'http://example.com/v1/discharger/discharge'
            '?discharge-for-user=my.user%2Bname&id=identifier',
            timeout=DEFAULT_TIMEOUT,
            method='POST')

    def test_discharge_token_successful(self):
        with HTTMock(discharge_token_200):
            results = self.idm.discharge_token('Brad')
        self.assertEqual(b'["something"]', base64.urlsafe_b64decode(results))

    def test_discharge_token_username_quoted(self):
        # The username query sent to the identity manager is properly quoted.
        @urlmatch(path=DISCHARGE_TOKEN_PATH)
        def handler(url, _):
            self.assertEqual('username=my.user%2Bname', url.query)
            return {
                'status_code': 200,
                'content': {'DischargeToken': 'something'},
            }
        with HTTMock(handler):
            self.idm.discharge_token('my.user+name')


class TestIDMClass(TestCase, helpers.TimeoutTestsMixin):

    def setUp(self):
        self.idm = IdentityManager('http://example.com:8082/v1')

    def test_init(self):
        self.assertEqual(self.idm.url, 'http://example.com:8082/v1/')

    @patch('theblues.identity_manager.make_request')
    def test_debug(self, mock):
        self.idm.debug()
        mock.assert_called_once_with(
            'http://example.com:8082/v1/debug/status', timeout=DEFAULT_TIMEOUT)

    @patch('theblues.identity_manager.make_request')
    def test_debug_fail(self, mock):
        mock.side_effect = ServerError('abc')
        val = self.idm.debug()
        self.assertEquals(val, {'error': 'abc'})

    @patch('theblues.identity_manager.make_request')
    def test_get_user(self, make_request_mock):
        self.idm.get_user('jeffspinach', 'my-macaroon')
        make_request_mock.assert_called_once_with(
            'http://example.com:8082/v1/u/jeffspinach',
            timeout=DEFAULT_TIMEOUT, macaroons='my-macaroon')

    def test_get_extra_info_ok(self):
        with HTTMock(extra):
            info = self.idm.get_extra_info('frobnar')
            self.assertEqual(info.get('foo'), 1)

    def test_get_extra_info_error_timeout(self):
        expected_url = 'http://example.com:8082/v1/u/who/extra-info'
        with self.assert_timeout(expected_url, DEFAULT_TIMEOUT):
            self.idm.get_extra_info('who')

    def test_set_extra_info_ok(self):
        with HTTMock(extra):
            # This will blow up if set_extra_info isn't passing the data along
            # correctly--see the assert in extra above.
            self.idm.set_extra_info('frobnar', {'foo': 1})

    def test_set_extra_info_error_timeout(self):
        expected_url = 'http://example.com:8082/v1/u/who/extra-info'
        with self.assert_timeout(expected_url, DEFAULT_TIMEOUT):
            self.idm.set_extra_info('who', {})
