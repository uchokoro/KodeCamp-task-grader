import datetime as dt
import pytest

from task_grader.lms.lms_client import (
    LMSClient,
    SubmissionMeta,
    SubmissionCategory,
)

# --- Minimal fake HTTP helpers ------------------------------------------------


class FakeResponse:
    def __init__(
        self, *, ok=True, status_code=200, json_data=None, text="", params=None
    ):
        self.ok = ok
        self.status_code = status_code
        self._json_data = json_data
        self.text = text
        self.params = params or {}

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if not self.ok or self.status_code >= 400:
            import requests

            raise requests.exceptions.HTTPError(f"{self.status_code} error")


class FakeSession:
    """
    A tiny stand-in for requests.Session that returns queued responses
    for .post/.get/.delete and records the last call for assertions.
    """

    def __init__(self, *, post=None, get=None, delete=None):
        self.headers = {}
        self._post_q = list(post or [])
        self._get_q = list(get or [])
        self._delete_q = list(delete or [])
        self.last_post = None
        self.last_get = None
        self.last_delete = None

    def post(self, url, data=None, json=None):
        self.last_post = {
            "url": url,
            "data": data,
            "json": json,
            "headers": dict(self.headers),
        }
        if not self._post_q:
            raise AssertionError("No queued POST response")
        return self._post_q.pop(0)

    def get(self, url, params=None):
        self.last_get = {
            "url": url,
            "params": params or {},
            "headers": dict(self.headers),
        }
        if not self._get_q:
            raise AssertionError("No queued GET response")
        return self._get_q.pop(0)

    def delete(self, url):
        self.last_delete = {"url": url, "headers": dict(self.headers)}
        if not self._delete_q:
            raise AssertionError("No queued DELETE response")
        return self._delete_q.pop(0)


# --- Fixtures -----------------------------------------------------------------


@pytest.fixture
def creds():
    return {
        "base_url": "https://lms.example.com/api",
        "email": "alice@example.com",
        "password": "s3cret",
    }


@pytest.fixture
def monkey_session(monkeypatch):
    """
    Helper to replace requests.Session constructor with our FakeSession instance.
    Yields (fake_session, install_fn) so tests can inject queues per test.
    """
    container = {}

    def install(fake):
        monkeypatch.setattr("task_grader.lms.lms_client.requests.Session", lambda: fake)
        container["session"] = fake
        return fake

    yield install


# --- Login / Logout / Token ---------------------------------------------------


def test_login_success_sets_token_and_header(monkey_session, creds):
    # token expires in future
    future = (dt.datetime.now() + dt.timedelta(hours=1)).isoformat()
    token_payload = {"access_token": "abc.def", "expires": future}
    fake = FakeSession(
        post=[FakeResponse(ok=True, status_code=200, json_data=token_payload)]
    )
    monkey_session(fake)

    client = LMSClient(**creds)
    client.login()

    token = client.get_token()
    assert token and token["token_string"] == "abc.def"
    assert "Authorization" in client.get_session().headers
    assert client.get_session().headers["Authorization"] == "Bearer abc.def"
    assert fake.last_post["url"] == f"{creds['base_url']}/login"
    # Expect form-encoded (data=...), not json
    assert fake.last_post["data"] == {
        "grant_type": "password",
        "username": creds["email"],
        "password": creds["password"],
    }
    assert fake.last_post["json"] is None


def test_login_failure_raises(monkey_session, creds):
    fake = FakeSession(post=[FakeResponse(ok=False, status_code=422, text="bad req")])
    monkey_session(fake)
    client = LMSClient(**creds)
    with pytest.raises(RuntimeError) as exc:
        client.login()
    assert "Login failed" in str(exc.value)
    assert "422" in str(exc.value)


def test_login_missing_or_expired_token_raises(monkey_session, creds):
    past = (dt.datetime.now() - dt.timedelta(minutes=1)).isoformat()
    payloads = [
        {"access_token": None, "expires": None},
        {"access_token": "x", "expires": past},  # expired
    ]
    for payload in payloads:
        fake = FakeSession(post=[FakeResponse(json_data=payload)])
        monkey_session(fake)
        client = LMSClient(**creds)
        with pytest.raises(RuntimeError):
            client.login()


def test_logout_clears_header_and_token(monkey_session, creds, capsys):
    future = (dt.datetime.now() + dt.timedelta(hours=1)).isoformat()
    token_payload = {"access_token": "tokenZ", "expires": future}
    # Successful login, then successful logout (204)
    fake = FakeSession(
        post=[FakeResponse(json_data=token_payload)],
        delete=[FakeResponse(status_code=204)],
    )
    monkey_session(fake)

    client = LMSClient(**creds)
    client.login()
    assert client.get_token() is not None
    client.logout()
    assert client.get_token() is None
    # Authorization header removed
    assert "Authorization" not in client.get_session().headers


def test_logout_warns_on_failure_but_does_not_raise(monkey_session, creds, capsys):
    future = (dt.datetime.now() + dt.timedelta(hours=1)).isoformat()
    token_payload = {"access_token": "ok", "expires": future}
    # Force a failing logout
    fake = FakeSession(
        post=[FakeResponse(json_data=token_payload)],
        delete=[FakeResponse(ok=False, status_code=500, text="boom")],
    )
    monkey_session(fake)
    client = LMSClient(**creds)
    client.login()
    client.logout()  # should not raise
    out = capsys.readouterr().out
    assert "[WARN] Logout failed" in out


def test_is_token_valid_true_when_endpoint_ok_and_email_matches(monkey_session, creds):
    future = (dt.datetime.now() + dt.timedelta(hours=1)).isoformat()
    token_payload = {"access_token": "tok", "expires": future}
    # First call is login; second is test-access-token
    fake = FakeSession(
        post=[
            FakeResponse(json_data=token_payload),
            FakeResponse(json_data={"email": creds["email"]}),
        ]
    )
    monkey_session(fake)
    client = LMSClient(**creds)
    client.login()
    assert client.is_token_valid() is True


def test_is_token_valid_false_when_no_token_or_header(monkey_session, creds):
    fake = FakeSession()
    monkey_session(fake)
    client = LMSClient(**creds)
    assert client.is_token_valid() is False


def test_is_token_valid_false_on_endpoint_error_or_email_mismatch(
    monkey_session, creds
):
    future = (dt.datetime.now() + dt.timedelta(hours=1)).isoformat()
    token_payload = {"access_token": "tok", "expires": future}

    # Case 1: endpoint not ok
    fake1 = FakeSession(
        post=[
            FakeResponse(json_data=token_payload),
            FakeResponse(ok=False, status_code=401),
        ]
    )
    monkey_session(fake1)
    client = LMSClient(**creds)
    client.login()
    assert client.is_token_valid() is False

    # Case 2: email mismatch
    fake2 = FakeSession(
        post=[
            FakeResponse(json_data=token_payload),
            FakeResponse(json_data={"email": "wrong@example.com"}),
        ]
    )
    monkey_session(fake2)
    client = LMSClient(**creds)
    client.login()
    assert client.is_token_valid() is False


# --- get_task_submissions -----------------------------------------------------


def _sample_submissions_payload():
    return {
        "submissions": [
            {
                "id": 7,
                "student_id": 101,
                "updated_at": "2025-11-10T12:00:00",
                "task": {"due_date": "2025-11-12T23:59:59"},
                "submission_urls": ["https://docs.google.com/document/d/ABC123/edit"],
                "status": "submitted",
                "score": 0.0,
            },
            {
                "id": 8,
                "student_id": 202,
                "updated_at": "2025-11-10T15:30:00",
                "task": {"due_date": "2025-11-12T23:59:59"},
                "submission_urls": ["https://docs.google.com/document/d/XYZ999/edit"],
                "status": "graded",
                "score": 4.5,
            },
        ],
        "students": [
            {"id": 101, "profile": {"first_name": "Adaobi", "last_name": "Ezelioha"}},
            {"id": 202, "profile": {"first_name": "Chinedu", "last_name": "Okafor"}},
        ],
    }


def test_get_task_submissions_logs_in_if_needed_and_parses(monkey_session, creds):
    future = (dt.datetime.now() + dt.timedelta(hours=1)).isoformat()
    token_payload = {"access_token": "tok", "expires": future}

    fake = FakeSession(
        post=[
            FakeResponse(json_data=token_payload),  # login
            FakeResponse(
                json_data={"email": creds["email"]}
            ),  # test-access-token (from is_token_valid)
        ],
        get=[FakeResponse(json_data=_sample_submissions_payload())],
    )
    monkey_session(fake)

    client = LMSClient(**creds)
    # Force path where is_token_valid() triggers login:
    # First call to is_token_valid() sees no token -> login runs, then test-access-token runs
    results = client.get_task_submissions(
        task_id="prompt-refinement",
        workspace_slug="kodecamp",
        category=SubmissionCategory.ALL,
        offset=10,
        limit=5,
    )

    # Correct endpoint and query params
    assert fake.last_get["url"] == f"{creds['base_url']}/kodecamp/submissions"
    assert fake.last_get["params"] == {"offset": 10, "limit": 5}

    # Parsed objects
    assert isinstance(results, list) and len(results) == 2
    first = results[0]
    assert isinstance(first, SubmissionMeta)
    assert first.task_id == "prompt-refinement"
    assert first.submission_id == "7"
    assert first.trainee_id == "101"
    assert first.trainee_name == "Adaobi Ezelioha"
    assert first.solution_urls == ["https://docs.google.com/document/d/ABC123/edit"]
    assert first.submission_status == "submitted"
    assert first.score == 0.0


def test_get_task_submissions_filters_by_category(monkey_session, creds):
    future = (dt.datetime.now() + dt.timedelta(hours=1)).isoformat()
    token_payload = {"access_token": "tok", "expires": future}

    sample_payload = _sample_submissions_payload()

    fake = FakeSession(
        post=[
            FakeResponse(json_data=token_payload),  # login (first call)
            FakeResponse(
                json_data={"email": creds["email"]}
            ),  # test-access-token (second call)
        ],
        get=[
            FakeResponse(json_data=sample_payload),  # GET for first call (SUBMITTED)
            FakeResponse(json_data=sample_payload),  # GET for second call (GRADED)
        ],
    )
    monkey_session(fake)

    client = LMSClient(**creds)

    # First call: filter submitted
    only_submitted = client.get_task_submissions(
        "task-x", "ws", category=SubmissionCategory.SUBMITTED
    )
    assert len(only_submitted) == 1
    assert only_submitted[0].submission_status == "submitted"

    # Second call: filter graded
    only_graded = client.get_task_submissions(
        "task-x", "ws", category=SubmissionCategory.GRADED
    )
    assert len(only_graded) == 1
    assert only_graded[0].submission_status == "graded"


def test_get_task_submissions_validates_shape_and_raises(monkey_session, creds):
    future = (dt.datetime.now() + dt.timedelta(hours=1)).isoformat()
    token_payload = {"access_token": "tok", "expires": future}
    # Missing keys
    bad_payloads = [
        {},  # not a dict with keys
        {"submissions": [], "students": None},
        {"submissions": None, "students": []},
    ]

    for payload in bad_payloads:
        fake = FakeSession(
            post=[
                FakeResponse(json_data=token_payload),
                FakeResponse(json_data={"email": creds["email"]}),
            ],
            get=[FakeResponse(json_data=payload)],
        )
        monkey_session(fake)
        client = LMSClient(**creds)
        with pytest.raises(RuntimeError):
            client.get_task_submissions("t1", "ws")


# --- from_env -----------------------------------------------------------------


def test_from_env_success(monkeypatch):
    monkeypatch.setenv("LMS_BASE_URL", "https://lms.example.com/api")
    monkeypatch.setenv("LMS_EMAIL", "dev@example.com")
    monkeypatch.setenv("LMS_PASSWORD", "pw")
    client = LMSClient.from_env()
    assert isinstance(client, LMSClient)
    assert client.base_url == "https://lms.example.com/api"
    assert client.email == "dev@example.com"


def test_from_env_missing_raises(monkeypatch):
    # Clear any existing variables
    for key in ("LMS_BASE_URL", "LMS_EMAIL", "LMS_PASSWORD"):
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(RuntimeError) as exc:
        LMSClient.from_env()
    # Don't assert exact text (your message mentions LMS_USERNAME); just ensure it's our error.
    assert "LMS_" in str(exc.value)
