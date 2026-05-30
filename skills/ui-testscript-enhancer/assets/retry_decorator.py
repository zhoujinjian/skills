import functools
import time
import os
from typing import Callable


def retry_on_failure(
    max_retries: int = 3,
    delay: float = 1.0,
    screenshot: bool = True,
    exceptions: tuple = (Exception,),
):
    """操作级重试装饰器

    用法:
        @retry_on_failure(max_retries=3, delay=1.0)
        def click_login(self) -> "HomePage":
            self._login_button.click()
            return HomePage(self.page)
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            last_error = None
            for attempt in range(max_retries):
                try:
                    return func(self, *args, **kwargs)
                except exceptions as e:
                    last_error = e
                    if screenshot and hasattr(self, "page") and hasattr(self, "take_screenshot"):
                        try:
                            self.take_screenshot(
                                f"retry_{func.__name__}_attempt{attempt + 1}"
                            )
                        except Exception:
                            pass
                    if attempt < max_retries - 1:
                        time.sleep(delay * (attempt + 1))
            raise last_error

        return wrapper

    return decorator


def retry_with_refresh(max_retries: int = 2, delay: float = 2.0):
    """页面级重试：失败后刷新页面再试

    用法:
        @retry_with_refresh(max_retries=2)
        def submit_form(self):
            self._submit.click()
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            last_error = None
            for attempt in range(max_retries):
                try:
                    return func(self, *args, **kwargs)
                except Exception as e:
                    last_error = e
                    if attempt < max_retries - 1 and hasattr(self, "recover_page"):
                        self.recover_page()
                        time.sleep(delay)
            raise last_error

        return wrapper

    return decorator
