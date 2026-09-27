import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

def transient(exc):
    if isinstance(exc, (requests.Timeout, requests.ConnectionError)):
        return True
    return isinstance(exc, requests.HTTPError) and exc.response is not None and (exc.response.status_code == 429 or exc.response.status_code >= 500)

def retry_with_backoff(max_attempts=3, base_delay=1):
    return retry(stop=stop_after_attempt(max_attempts), wait=wait_exponential(multiplier=base_delay, max=30), retry=retry_if_exception(transient), reraise=True)
