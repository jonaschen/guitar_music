from app.services.rate_limit import SubmissionRateLimiter


def test_submission_rate_limiter_blocks_and_expires_old_attempts():
    limiter = SubmissionRateLimiter(limit=2, window_seconds=10)

    assert limiter.allow("client", now=100) == (True, 0)
    assert limiter.allow("client", now=105) == (True, 0)
    allowed, retry_after = limiter.allow("client", now=106)
    assert allowed is False
    assert retry_after == 4
    assert limiter.allow("client", now=111) == (True, 0)


def test_submission_rate_limiter_can_be_disabled():
    limiter = SubmissionRateLimiter(limit=0, window_seconds=10)
    assert all(limiter.allow("client", now=float(index))[0] for index in range(20))
