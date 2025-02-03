import os

from django.http import JsonResponse, HttpResponse, Http404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db import transaction

from swinTransformer.tools.constant import nginx_image_dir, nginx_image_url_root
from swinTransformer.tools.cache import *
from swinTransformer.tasks import swin_transformer_process_image

from swinTransformer.models import OriginalImage
from swinTransformer.models import SegmentedImage


@require_http_methods(['POST'])
@csrf_exempt
def upload_file(request):
    """
    :param request: HttpRequest
    :return JsonResponse--- {
                isSuccessful: 处理是否成功
                source_image_id: 图片对的编号 用于后续的查询以及删除等操作
                source_image_url: 用户上传的图片的访问地址
                segmented_image_url: 分割后的图片的访问地址
                message: 具体的描述信息
            }
            TODO: 将swinTransformer分割图片的过程丢给celery来异步执行 避免耗时操作对主线程造成影响
            TODO: 前端也应该做出相应的改变如 以轮询的方式判断图片分割是否结束, django应该提供用于判断任务是否完成的api
    """

    file = request.FILES['picture']
    user_id = json.loads(request.COOKIES.get('identification')).get('id')
    file_path = os.path.join(nginx_image_dir, file.name)
    try:
        with open(file_path, 'wb+') as destination:
            for chunk in file.chunks():
                destination.write(chunk)
    except IOError as e:
        print(f'Error:{e}')
        return JsonResponse({'isSuccessful': False, 'message': 'io error on server'})
    source_image_url = nginx_image_url_root + file.name  # 用户上传照片的url地址
    result = swin_transformer_process_image.delay(user_id, source_image_url, file.name)
    task_id = result.id
    return JsonResponse({
        'isSuccessful': True,
        'task_id': task_id,
    })


def removeImageFromArray(lst):
    try:
        removed_image_name = lst[0].image_path.split('/')[-1]
        os.remove(f'{nginx_image_dir}{removed_image_name}')
    except FileNotFoundError:
        print('file not found')
    except PermissionError:
        print('do not have permission')
    except Exception as e:
        print('error on deleting a file', e)


@require_http_methods(['POST'])
@csrf_exempt
def deleteImage(request):
    data = json.loads(request.body)
    user_id = json.loads(request.COOKIES.get('identification')).get('id')
    original_image_id = data.get('original_image_id')
    image_page_number = data.get('image_page_number')
    if original_image_id <= 0:
        return JsonResponse({'isSuccessful': False, 'message': 'original_image_id can not be under 0'})
    # 数据库操作
    target_segmented_image = SegmentedImage.objects.filter(original_image_id=original_image_id)
    if len(target_segmented_image) != 1:
        return JsonResponse({'isSuccessful': False, 'message': 'something wrong in data base'})
    removeImageFromArray(target_segmented_image)
    target_segmented_image.delete()
    target_original_image = OriginalImage.objects.filter(id=original_image_id)
    if len(target_original_image) != 1:
        return JsonResponse({'isSuccessful': False, 'message': 'something wrong in data base'})
    if len(OriginalImage.objects.filter(image_path=target_original_image[0].image_path)) == 1:
        removeImageFromArray(target_original_image)
    target_original_image.delete()
    # 删除缓存操作
    """
    如果删除缓存的操作失败 该如何处理
    考虑引入 消息队列处理 操作失败的情况
    重试多次后仍失败考虑数据库的回滚
    """
    image_number = get_user_image_number(user_id)
    if image_page_number == -1:
        last_page = image_number // settings.DEFAULT_LINES_PER_PAGE
        if image_number % settings.DEFAULT_LINES_PER_PAGE != 0:
            last_page += 1
        delete_user_page(user_id, last_page)
    else:
        delete_all_page_after_than(user_id, image_page_number)
    image_number -= 1
    set_user_image_number(user_id, image_number)
    page_number = image_number // settings.DEFAULT_LINES_PER_PAGE
    if image_number % settings.DEFAULT_LINES_PER_PAGE:
        page_number += 1
    return JsonResponse({'isSuccessful': True, 'message': 'success', 'page_number': page_number})


@require_http_methods(['GET'])
@csrf_exempt
def download_image(_request, filename):
    file_path = os.path.join(nginx_image_dir, filename)
    if os.path.exists(file_path):
        with open(file_path, 'rb') as file:
            response = HttpResponse(file.read(), content_type='image/jpeg')
            response['Content-Disposition'] = f'attachment; filename={filename}'
            return response
    else:
        raise Http404('image not found')


@require_http_methods(['GET'])
@csrf_exempt
def get_images_by_page(request, page_number=1, lines_per_page=settings.DEFAULT_LINES_PER_PAGE):
    """
    :param request:
    :param page_number: 展示的页数
    :param lines_per_page: 每一页上有多少行的数据
    :return: JsonResponse--- {
                isSuccessful: 处理是否成功
                isCached: 是否是redis缓存中获取的数据
                original_id_list: 分割前图片的id数组
                original_images_list: 分割前的图片数组
                segmented_images_list: 分割后的图片数组
                message: 具体的描述信息
            }
    """
    if lines_per_page != settings.DEFAULT_LINES_PER_PAGE:
        return JsonResponse({'message': 'lines_per_page can only be 4'})
    user_id = json.loads(request.COOKIES.get('identification')).get('id')
    # TODO
    '''  
        应该使用 redis对数据进行一个缓存
        original_images_list:
        segmented_images_list:
        这个缓存应该是有限度的缓存 比如说 指定用户最多只能缓存指定的页数
    '''
    # 获取缓存的过程
    cached_str = get_cached_page(user_id, page_number)
    if cached_str is not None:
        page_data = json.loads(cached_str)
        image_number = get_user_image_number(user_id)
        page_length = image_number // settings.DEFAULT_LINES_PER_PAGE
        if image_number % settings.DEFAULT_LINES_PER_PAGE != 0:
            page_length += 1
        return JsonResponse(
            {
                'isSuccessful': True,
                'isCached': True,
                'original_id_list': page_data.get('original_id_list'),
                'original_images_list': page_data.get('original_images_list'),
                'segmented_images_list': page_data.get('segmented_images_list'),
                'message': 'success',
                'page_length': page_length,
            })
    else:
        target_original_results = OriginalImage.objects.filter(user_id=user_id).values(
            'image_path', 'id')
        all_image_number = len(target_original_results)
        target_original_results = target_original_results[
                                  (page_number - 1) * lines_per_page:page_number * lines_per_page]
        original_images_list = []
        original_id_list = []
        for result in target_original_results:
            original_images_list.append(result.get('image_path'))
            original_id_list.append(result.get('id'))
        if len(original_images_list) == 0:
            return JsonResponse({'isSuccessful': False, 'message': 'no data anymore'})
        target_segmented_images = SegmentedImage.objects.filter(user_id=user_id).values('image_path')[
                                  (page_number - 1) * lines_per_page:page_number * lines_per_page]
        segmented_images_list = []
        for image in target_segmented_images:
            segmented_images_list.append(image.get('image_path'))
        if len(segmented_images_list) == 0:
            return JsonResponse({'isSuccessful': False, 'message': 'something wrong in the database'})
        caching_dict = {
            'original_id_list': original_id_list,
            'original_images_list': original_images_list,
            'segmented_images_list': segmented_images_list,
        }
        cache_user_page(user_id, page_number, json.dumps(caching_dict), all_image_number)
        image_number = get_user_image_number(user_id)
        page_length = image_number // settings.DEFAULT_LINES_PER_PAGE
        if image_number % settings.DEFAULT_LINES_PER_PAGE != 0:
            page_length += 1
        return JsonResponse(
            {
                'isSuccessful': True,
                'isCached': False,
                'original_id_list': original_id_list,
                'original_images_list': original_images_list,
                'segmented_images_list': segmented_images_list,
                'message': 'success',
                'page_length': page_length,
            })


@require_http_methods(['POST'])
@csrf_exempt
def get_max_page_number(request):
    user_id = json.loads(request.COOKIES.get('identification')).get('id')
    image_number = get_user_image_number(user_id)
    page_number = image_number // settings.DEFAULT_LINES_PER_PAGE
    if image_number % settings.DEFAULT_LINES_PER_PAGE != 0:
        page_number += 1
    return JsonResponse({'isSuccessful': True, 'page_number': page_number})


@require_http_methods(["POST"])
@csrf_exempt
def get_images_by_token_and_page(request):
    """ 
    :param request:
    应该包含用户所提供的 token 用于模糊查找 也许同样需要 redis进行缓存？
    应该包含指定token的图片对的page页码数
    TODO: 如何分辨用户的查询页数指的是token查询还是普通的查询
        1.前端可以查看search框中是否有信息 也许我们的搜索框应该提供一个 删除按钮
        2.用户点击查询后搜索框失效直到用户点击删除按钮 期间的所有点击均可理解为用户通过token执行查询任务
    :return:
    """
    user_id = json.loads(request.COOKIES.get('identification')).get('id')
    search_info = json.loads(request.body)
    search_token = search_info.get('search_token')
    page_number = search_info.get('page_number')
    cached_str = get_cached_token_page(user_id, search_token, page_number)
    if cached_str is not None:
        cached_result = json.loads(cached_str)
        return JsonResponse({
            'isCached': True,
            'isSuccessful': True,
            'original_id_list': cached_result.get('original_id_list'),
            'original_images_list': cached_result.get('original_images_list'),
            'segmented_images_list': cached_result.get('segmented_images_list'),
            'message': 'success',
            'isEmpty': len(cached_result.get('original_id_list')) == 0,
            'page_number': cached_result.get('page_number'),
        })
    try:
        with transaction.atomic():
            target_images = OriginalImage.objects.filter(user_id=user_id, image_path__icontains=search_token).values(
                'image_path', 'id')
            page_length = len(target_images) // settings.DEFAULT_LINES_PER_PAGE
            if len(target_images) % settings.DEFAULT_LINES_PER_PAGE != 0:
                page_length += 1
            target_images = target_images[
                            (
                                    page_number - 1) * settings.DEFAULT_LINES_PER_PAGE:page_number * settings.DEFAULT_LINES_PER_PAGE]
            target_original_images = []
            target_original_ids = []
            for vale in target_images:
                target_original_images.append(vale.get('image_path'))
                target_original_ids.append(vale.get('id'))
            target_images = SegmentedImage.objects.filter(original_image_id__in=target_original_ids).values(
                'image_path')
            print(len(target_images) == len(target_original_images))
            target_segmented_images = []
            for vale in target_images:
                target_segmented_images.append(vale.get('image_path'))
            result = {
                'original_id_list': target_original_ids,
                'original_images_list': target_original_images,
                'segmented_images_list': target_segmented_images,
                'page_number': page_length,
            }
            cache_token_page(user_id, search_token, page_number, result)
        return JsonResponse({
            'isCached': False,
            'isSuccessful': True,
            'original_id_list': target_original_ids,
            'original_images_list': target_original_images,
            'segmented_images_list': target_segmented_images,
            'message': 'success',
            'isEmpty': len(target_original_ids) == 0,
            'page_number': page_length,
        })
    except Exception as e:
        return JsonResponse({
            'isCached': False,
            'isSuccessful': False,
            'message': str(e),
        })
