import json
import time

from swin import settings
from django_redis import get_redis_connection
from swinTransformer.models import OriginalImage


def get_cached_page(user_id: int, page_number: int):
    conn = get_redis_connection('default')
    cached_key = f'page_cache:{user_id}-{page_number}-{settings.DEFAULT_LINES_PER_PAGE}'
    sort_cached_key = f'sorted_set:{user_id}'
    current_time = time.time()
    conn.zadd(sort_cached_key, {page_number: current_time})  # 更新缓存的页面的score
    return conn.get(cached_key)


def cache_user_page(user_id: int, page_number: int, page_content: str, all_image_number: int):
    page_cached_key = f'page_cache:{user_id}-{page_number}-{settings.DEFAULT_LINES_PER_PAGE}'
    sort_cached_key = f'sorted_set:{user_id}'
    conn = get_redis_connection('default')
    current_time = time.time()
    conn.set(page_cached_key, page_content)
    conn.set(f'{user_id}', all_image_number)
    conn.zadd(sort_cached_key, {page_number: current_time})
    page_count = conn.zcard(sort_cached_key)
    if page_count > settings.MAX_PAGES_PER_USER:
        oldest_pages = conn.zrange(sort_cached_key, 0, 0)
        if oldest_pages is not None:
            oldest_page_number = oldest_pages[0]
            conn.delete(f'page_cache:{user_id}-{oldest_page_number}-{settings.DEFAULT_LINES_PER_PAGE}')
            conn.zrem(sort_cached_key, oldest_page_number)


def delete_user_page(user_id: int, page_number: int):
    conn = get_redis_connection('default')
    page_cached_key = f'page_cache:{user_id}-{page_number}-{settings.DEFAULT_LINES_PER_PAGE}'
    sort_cached_key = f'sorted_set:{user_id}'
    conn.delete(page_cached_key)
    conn.zrem(sort_cached_key, page_number)


def get_user_image_number(user_id: int) -> int:
    conn = get_redis_connection('default')
    page_number_key = f'{user_id}'
    bytes_data = conn.get(page_number_key)
    if bytes_data is None:
        bytes_data = len(OriginalImage.objects.filter(user_id=user_id) or [])
        conn.set(page_number_key, bytes_data)
    str_data = bytes_data.decode('utf-8')
    image_number = int(str_data)
    return image_number


def set_user_image_number(user_id: int, image_number: int):
    conn = get_redis_connection('default')
    page_number_key = f'{user_id}'
    conn.set(page_number_key, image_number)


def delete_all_page_after_than(user_id: int, page_number: int):
    conn = get_redis_connection('default')
    sort_cached_key = f'sorted_set:{user_id}'
    sorted_page_number = conn.zrange(sort_cached_key, 0, -1, withscores=False)
    if sorted_page_number is not None:
        for page in sorted_page_number:
            page = int(page.decode('utf-8'))
            if page >= page_number:
                conn.zrem(sort_cached_key, page)
                page_cached_key = f'page_cache:{user_id}-{page}-{settings.DEFAULT_LINES_PER_PAGE}'
                conn.delete(page_cached_key)


def cache_unverified_user(token: str, username: str, password: str, email: str) -> bool:
    conn = get_redis_connection('default')
    unverified_user_key = f'unverified:{token}'
    caching_dict = {
        'username': username,
        'password': password,
        'email': email,
    }
    return conn.set(
        unverified_user_key,
        json.dumps(caching_dict),
        ex=settings.EMAIL_VALIDATION_EXPIRE_TIME
    )


def store_user_verification(username: str, password: str, verification: str):
    conn = get_redis_connection('default')
    verification_store_key = f'verification:{username}-{password}'
    return conn.set(
        verification_store_key,
        verification,
        ex=settings.EMAIL_VALIDATION_EXPIRE_TIME
    )


def get_user_verification(username: str, password: str) -> str:
    conn = get_redis_connection('default')
    verification_store_key = f'verification:{username}-{password}'
    return conn.get(verification_store_key)


def verify_user(token: str) -> str:
    conn = get_redis_connection('default')
    unverified_user_key = f'unverified:{token}'
    result = conn.get(unverified_user_key)
    # TODO result 的类型需要调试确定一下
    return result


def clear_verification(username: str, password: str):
    """
    :param username:
    :param password:
    用户已经验证过了
    讲清楚缓存中的无用信息
    """
    conn = get_redis_connection('default')
    verification_store_key = f'verification:{username}-{password}'
    verification_token = conn.get(verification_store_key)
    if verification_token is not None:
        conn.delete(verification_store_key)
        unverified_user_key = f'unverified:{verification_token}'
        conn.delete(unverified_user_key)
