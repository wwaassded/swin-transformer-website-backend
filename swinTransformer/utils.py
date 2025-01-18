import subprocess
import time

from swin import settings
from swinTransformer.constant import nginx_image_dir, nginx_image_url_root
from swinTransformer.constant import swin_transformer_checkpoint, swin_transformer_working_dir
from django_redis import get_redis_connection


def process_image(original_img_name: str) -> str:
    local_original_img_name = nginx_image_dir + original_img_name
    file_name = original_img_name.split('.')
    local_segmented_img_file_name = file_name[0] + '_segmented' + '.' + file_name[1]
    local_segmented_img_name = nginx_image_dir + local_segmented_img_file_name
    code = swinTransformerHandler(local_original_img_name, local_segmented_img_name)
    if code == 0:
        segmented_image_url = nginx_image_url_root + local_segmented_img_file_name
        return segmented_image_url
    else:
        return ''


def swinTransformerHandler(original_image: str, output_image: str) -> int:
    result = subprocess.run(['python',
                             settings.SWIN_TRANSFORMER,
                             '--checkpoint', swin_transformer_checkpoint,
                             '--img', original_image,
                             '--outfile', output_image],
                            cwd=swin_transformer_working_dir
                            )
    return result.returncode


def get_cached_page(user_id: int, page_number: int):
    conn = get_redis_connection('default')
    cached_key = f'page_cache:{user_id}-{page_number}-{settings.DEFAULT_LINES_PER_PAGE}'
    return conn.get(cached_key)


def cache_user_page(user_id: int, page_number: int, page_content: str):
    page_cached_key = f'page_cache:{user_id}-{page_number}-{settings.DEFAULT_LINES_PER_PAGE}'
    sort_cached_key = f'sorted_set:{user_id}'
    conn = get_redis_connection('default')
    current_time = time.time()
    conn.set(page_cached_key, page_content)
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
