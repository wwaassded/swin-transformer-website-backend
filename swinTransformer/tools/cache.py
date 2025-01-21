import time

from swin import settings
from django_redis import get_redis_connection
from swinTransformer.models import OriginalImage


def get_cached_page(user_id: int, page_number: int):
    conn = get_redis_connection('default')
    cached_key = f'page_cache:{user_id}-{page_number}-{settings.DEFAULT_LINES_PER_PAGE}'
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


def get_user_image_number(user_id: int):
    conn = get_redis_connection('default')
    page_number_key = f'{user_id}'
    image_number = conn.get(page_number_key)
    if image_number is None:
        image_number = len(OriginalImage.objects.filter(user_id=user_id) or [])
        conn.set(page_number_key, image_number)
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
            if page >= page_number:
                conn.zrem(sort_cached_key, page)
                page_cached_key = f'page_cache:{user_id}-{page}-{settings.DEFAULT_LINES_PER_PAGE}'
                conn.delete(page_cached_key)
