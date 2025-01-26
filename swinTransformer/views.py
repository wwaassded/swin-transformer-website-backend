import os
import uuid

from django.http import JsonResponse, HttpResponse, Http404
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db import transaction

from swinTransformer.tools.constant import nginx_image_dir, nginx_image_url_root
from swinTransformer.tools.utils import process_image
from swinTransformer.tools.cache import *

from .tasks import send_custom_email

from swinTransformer.models import User
from swinTransformer.models import OriginalImage
from swinTransformer.models import SegmentedImage


@require_http_methods(['POST'])
@csrf_exempt
def logup(request):
    """
    :param request:
    :return:
    用户注册过程的逻辑如下:
    将用户的注册信息存储在cache中 并设置合理的过期时间 (配合验证邮件的有效时间)
    用户通过向指定的url后从cache中获取用户的信息并存储到mysql中完成整个注册逻辑
    """
    new_user_info = json.loads(request.body)
    user_name = new_user_info.get('username')
    password = new_user_info.get('password')
    email = new_user_info.get('email')
    verification_token = str(uuid.uuid4())  # 每一个未注册的用户的唯一的验证令牌
    if not cache_unverified_user(verification_token, user_name, password, email):
        return JsonResponse({'isSuccessful': False, 'message': 'can not create user in data base'})
    else:
        subject = '欢迎注册swinTransformer'
        template_name = 'welcome.html'
        context = {'username': user_name, 'verify_url': f'http://localhost:8000/verify/{verification_token}'}
        recipient_list = [email]
        send_custom_email.delay(subject, template_name, context, recipient_list)
        return JsonResponse({'isSuccessful': True, 'message': 'now you need to varify your email'})


@require_http_methods(['POST'])
@csrf_exempt
def login(request):
    """
    :param request:
    :return:
    登陆逻辑介绍:
    登录逻辑比较简单
    但是需要注意的是用户可能刚刚注册但是并没有验证
    所以需要先查看cache中的信息如果未验证 需要基于用户一定的提示
    """
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
            """
            这里的所影响的缓存一定是 用户的最后一页缓存 所以需要获取到最后一页缓存的 key
            如果需要清除缓存 那么用户一定经历过 get_images_by_page 函数
            可以在 该函数内部操作数据库时 额外查询 COUNT(*)  获取我们需要的数据
            并且 存储在全局的dict中 从而判断用户是否需要经理缓存逻辑
            """

            """
            如果删除缓存的操作失败 该如何处理
            考虑引入 消息队列处理 操作失败的情况
            重试多次后仍失败考虑数据库的回滚
            """
            # 缓存更新逻辑
            total_image_number = get_user_image_number(user_id)
            # actually total_page_number can never be none
            if total_image_number is not None:
                page_number = total_image_number // settings.DEFAULT_LINES_PER_PAGE
                left_image_number = total_image_number % settings.DEFAULT_LINES_PER_PAGE
                if left_image_number != 0:
                    page_number += 1
                    delete_user_page(user_id, page_number)  # 如果没有缓存 nothing would happen
                else:
                    # 当最后一页的image是满的情况下应该是不需要删除缓存的
                    pass
                total_image_number += 1
                set_user_image_number(user_id, total_image_number)
            user: User = User.objects.filter(id=user_id).first()
            # TODO 后续考虑将生成的图片通过邮件对用户进行展示
            if user is not None:
                subject = '欢迎使用'
                template_name = 'work_done_info.html'
                context = {'username': user.username, 'user_id': user.id}
                recipient_list = [user.email]
                send_custom_email.delay(subject, template_name, context, recipient_list)
            return JsonResponse({
                'isSuccessful': True,
                'source_image_id': original_image.id,
                'source_image_url': source_image_url,
                'segmented_image_url': segmented_image_url,
                'message': 'success',
            })
    except Exception as e:
        return Http404('test', e)


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
        return JsonResponse(
            {
                'isSuccessful': True,
                'isCached': True,
                'original_id_list': page_data.get('original_id_list'),
                'original_images_list': page_data.get('original_images_list'),
                'segmented_images_list': page_data.get('segmented_images_list'),
                'message': 'success'
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
        return JsonResponse(
            {
                'isSuccessful': True,
                'isCached': False,
                'original_id_list': original_id_list,
                'original_images_list': original_images_list,
                'segmented_images_list': segmented_images_list,
                'message': 'success'
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


@require_http_methods(['POST'])
@csrf_exempt
def verify_user_emil(request, verification_token: str):
    result = verify_user(verification_token)
    if result is not None:
        user_detail_info = json.loads(result)
        user = User.objects.create(username=user_detail_info.get('username'),
                                   password=user_detail_info.get('password'),
                                   email=user_detail_info.get('email')
                                   )
        if user is not None:
            pass  # 成功
        else:
            pass  # 失败
    else:
        return render(request, 'expired.html', status=404)
