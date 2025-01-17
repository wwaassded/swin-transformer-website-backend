import json
import os
import time

from django.http import JsonResponse, HttpResponse, Http404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.core.cache import cache
from django.db import transaction

from swinTransformer.constant import nginx_image_dir, nginx_image_url_root, default_lines_per_page
from swinTransformer.utils import process_image

from swinTransformer.models import User
from swinTransformer.models import OriginalImage
from swinTransformer.models import SegmentedImage


@require_http_methods(['POST'])
@csrf_exempt
def logup(request):
    new_user_info = json.loads(request.body)
    user_name = new_user_info.get('username')
    password = new_user_info.get('password')
    new_user = User.objects.create(username=user_name, password=password)
    if new_user is not None:
        print(new_user)
        return JsonResponse({'isSuccessful': True, 'message': 'success'})
    else:
        return JsonResponse({'isSuccessful': False, 'message': 'can not create user in data base'})


@require_http_methods(['POST'])
@csrf_exempt
def login(request):
    user_data = json.loads(request.body)
    user_name = user_data.get('username')
    password = user_data.get('password')
    user = User.objects.filter(username=user_name, password=password).first()
    if user is not None:
        response = JsonResponse({'isSuccessful': True, 'message': 'Login successful'})
        user_info = {
            'id': user.id,
            'username': user.username
        }
        user_info_json = json.dumps(user_info)
        print(user_info_json)
        response.set_cookie('identification', user_info_json, samesite='None', secure=True)
        return response
    else:
        return JsonResponse({'isSuccessful': False, 'message': 'wrong userName or wrong password'})


@require_http_methods(['POST'])
@csrf_exempt
def logout(request):
    response = JsonResponse({'isSuccessful': True, 'message': 'Logout successful'})
    response.delete_cookie('identification', samesite='None')
    return response


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
    segmented_image_url = process_image(file.name)  # 分割后的照片的url地址
    try:
        with (transaction.atomic()):
            if segmented_image_url == '':
                return JsonResponse({'isSuccessful': False,
                                     'message': 'something wrong in swin Transformer model'
                                     })
            original_image = OriginalImage.objects.create(image_path=source_image_url,
                                                          user_id=user_id)
            if original_image is None:
                return JsonResponse({'isSuccessful': False,
                                     'message': 'something wrong in data base'
                                     })
            s = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
            segmented_image = SegmentedImage.objects.create(
                user_id=user_id,
                original_image_id=original_image.id,
                image_path=segmented_image_url,
                created_at=s
            )
            if segmented_image is None:
                return JsonResponse({'isSuccessful': False,
                                     'message': 'something wrong in data base'
                                     })
            # TODO 添加成功 应该对redis的缓存 进行一定的更新
            """
            这里的所影响的缓存一定是 用户的最后一页缓存 所以需要获取到最后一页缓存的 key
            如果需要清除缓存 那么用户一定经历过 get_images_by_page 函数
            可以在 该函数内部操作数据库时 额外查询 COUNT(*)  获取我们需要的数据
            并且 存储在全局的dict中 从而判断用户是否需要经理缓存逻辑
            """
            page_number = cache.get(f'{user_id}')
            if page_number is not None:
                key = f'{user_id}-{page_number}-{default_lines_per_page}'
                cached_data = json.loads(cache.get(key) or 'null')
                if cached_data is not None:
                    if len(cached_data.get('original_images_list')) != default_lines_per_page:
                        cache.delete_pattern(key)
                    else:
                        cache.set(f'{user_id}', page_number + 1)

            return JsonResponse({
                'isSuccessful': True,
                'source_image_id': original_image.id,
                'source_image_url': source_image_url,
                'segmented_image_url': segmented_image_url,
                'message': 'success'
            })
    except Exception:
        return Http404('test')


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
    original_image_id = data.get('original_image_id')
    if original_image_id <= 0:
        return JsonResponse({'isSuccessful': False, 'message': 'original_image_id can not be under 0'})
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
    return JsonResponse({'isSuccessful': True, 'message': 'success'})


@require_http_methods(['GET'])
@csrf_exempt
def download_image(request, filename):
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
def get_images_by_page(request, page_number=1, lines_per_page=default_lines_per_page):
    """
    :param request:
    :param page_number: 展示的页数
    :param lines_per_page: 每一页上有多少行的数据
    :return: JsonResponse--- {
                isSuccessful: 处理是否成功
                isCached: 是否是redis缓存中获取的数据
                original_images_list: 分割前的图片数组
                segmented_images_list: 分割后的图片数组
                message: 具体的描述信息
            }
    """
    if lines_per_page != default_lines_per_page:
        return JsonResponse({'message': 'lines_per_page can only be 4'})
    user_id = json.loads(request.COOKIES.get('identification')).get('id')
    # TODO
    '''  
        应该使用 redis对数据进行一个缓存
        original_images_list:
        segmented_images_list:
    '''
    cache_key = f'{user_id}-{page_number}-{lines_per_page}'  # 能够唯一确定一组数据的key
    cached_str = cache.get(cache_key)
    if cached_str is not None:
        page_data = json.loads(cached_str)
        return JsonResponse(
            {
                'isSuccessful': True,
                'isCached': True,
                'original_images_list': page_data.get('original_images_list'),
                'segmented_images_list': page_data.get('segmented_images_list'),
                'message': 'success'
            })
    else:
        target_original_results = OriginalImage.objects.filter(user_id=user_id).values(
            'image_path')
        cache.set(f'{user_id}', len(target_original_results) // lines_per_page + 1)
        target_original_results = target_original_results[
                                  (page_number - 1) * lines_per_page:page_number * lines_per_page]
        original_images_list = []
        for result in target_original_results:
            original_images_list.append(result.get('image_path'))
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
            'original_images_list': original_images_list,
            'segmented_images_list': segmented_images_list,
        }
        cache.set(cache_key, json.dumps(caching_dict), 1800)
        return JsonResponse(
            {
                'isSuccessful': True,
                'isCached': False,
                'original_images_list': original_images_list,
                'segmented_images_list': segmented_images_list,
                'message': 'success'
            })
