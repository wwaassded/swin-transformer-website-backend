import uuid

from django.http import JsonResponse
from django.shortcuts import render
from django.template.loader import render_to_string

from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from swinTransformer.tasks import send_custom_email
from swinTransformer.tools.cache import *
from swinTransformer.models import User


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
        store_user_verification(user_name, password, verification_token)
        subject = '欢迎注册swinTransformer'
        template_name = 'welcome.html'
        context = {'username': user_name, 'verify_url': f'{settings.DJANGO_ROOT}/verify/{verification_token}'}
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
    if get_user_verification(user_name, password) is not None:
        return JsonResponse({'isSuccessful': False, 'isVerification': False, 'message': 'un verification'})
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
def logout(_request):
    response = JsonResponse({'isSuccessful': True, 'message': 'Logout successful'})
    response.delete_cookie('identification', samesite='None')
    return response


@require_http_methods(['GET'])
@csrf_exempt
def verify_user_emil(request, verification_token: str):
    result = verify_user(verification_token)
    if result is not None:
        user_detail_info = json.loads(result)
        user = User.objects.create(
            username=user_detail_info.get('username'),
            password=user_detail_info.get('password'),
            email=user_detail_info.get('email')
        )
        if user is not None:
            clear_verification(user.username, user.password)
            return render(request, 'success.html', context={'target_url': settings.FRONTEND_ROOT}, status=200)
        else:
            # model 的 create 如何情况下会失败呢
            return render(request, 'expired.html', status=404)
    else:
        return render(request, 'expired.html', status=404)
